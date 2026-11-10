from __future__ import annotations
import logging
import os
import socket
import ipaddress
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from cryptography.fernet import Fernet, InvalidToken
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler
import httpx
from telegram import Update, ChatMemberAdministrator, ChatMemberOwner
from telegram.ext import ContextTypes, CommandHandler, ChatJoinRequestHandler
from ..branding import send_branded, keyboard_from_buttons

log = logging.getLogger(__name__)

def is_admin(update, context):
    u = update.effective_user
    return bool(u and (u.id == context.application.bot_data["owner_id"] or u.id in context.application.bot_data["admins"]))

async def reply(update, context, body, template_key: str | None = None):
    markup = None
    if template_key:
        rows = await context.application.bot_data["db"].get_buttons(context.application.bot_data["clone_id"], template_key)
        markup = keyboard_from_buttons(rows, small_caps=context.application.bot_data["small_caps"])
    await send_branded(context.bot, update.effective_chat.id, body,
        image_url=context.application.bot_data["image_url"], image_path=context.application.bot_data["image_path"],
        small_caps=context.application.bot_data["small_caps"], reply_markup=markup)



def _shortener_fernet():
    key = os.getenv("SHORTENER_ENCRYPTION_KEY", "").strip()
    if not key:
        raise RuntimeError("SHORTENER_ENCRYPTION_KEY is not configured.")
    try:
        return Fernet(key.encode("ascii"))
    except Exception as exc:
        raise RuntimeError("SHORTENER_ENCRYPTION_KEY is invalid; use a Fernet key.") from exc


def _validate_shortener_endpoint(endpoint: str):
    parsed = urlparse(endpoint)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Shortener endpoint must be a valid HTTPS URL without embedded credentials.")
    allowed = {host.strip().lower() for host in os.getenv("SHORTENER_ALLOWED_HOSTS", "").split(",") if host.strip()}
    hostname = parsed.hostname.lower()
    if not allowed or hostname not in allowed:
        raise ValueError("Endpoint host is not allowlisted. Configure SHORTENER_ALLOWED_HOSTS with its exact hostname.")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(hostname, parsed.port or 443, type=socket.SOCK_STREAM)}
        if not addresses:
            raise ValueError("Endpoint hostname did not resolve.")
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if not ip.is_global:
                raise ValueError("Endpoint resolves to a non-public IP address.")
    except socket.gaierror as exc:
        raise ValueError("Endpoint hostname could not be resolved.") from exc
    return parsed


def _public_slug(channel_id: int) -> str:
    return f"ch{abs(int(channel_id))}"


async def _missing_fsub(context, user_id: int):
    rows = await context.application.bot_data["db"].require().fetch(
        "SELECT channel_id,mode FROM link_fsub_channels WHERE clone_id=$1 ORDER BY channel_id",
        context.application.bot_data["clone_id"],
    )
    missing = []
    for row in rows:
        channel_id = int(row["channel_id"])
        try:
            member = await context.bot.get_chat_member(channel_id, user_id)
            status = getattr(member, "status", "")
            if status in {"left", "kicked"} or (status == "restricted" and not getattr(member, "is_member", False)):
                chat = await context.bot.get_chat(channel_id)
                if getattr(chat, "username", None):
                    join_url = f"https://t.me/{chat.username}"
                elif row["mode"] == "request":
                    invite = await context.bot.create_chat_invite_link(channel_id, creates_join_request=True)
                    join_url = invite.invite_link
                else:
                    join_url = await context.bot.export_chat_invite_link(channel_id)
                missing.append((channel_id, join_url))
        except Exception as exc:
            log.warning("FSub membership check failed for %s: %s", channel_id, type(exc).__name__)
            missing.append((channel_id, None))
    return missing


def _fsub_markup(missing, slug: str):
    rows = []
    for channel_id, join_url in missing:
        if join_url:
            rows.append([InlineKeyboardButton(f"· ᴊᴏɪɴ {channel_id} ·", url=join_url)])
    rows.append([InlineKeyboardButton("· ɪ'ᴠᴇ ᴊᴏɪɴᴇᴅ ·", callback_data=f"fsub:check:{slug}")])
    return InlineKeyboardMarkup(rows)


async def check_fsub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    slug = query.data.split(":", 2)[2]
    missing = await _missing_fsub(context, query.from_user.id)
    if missing:
        await query.answer("Please join every required channel first.", show_alert=True)
        await send_branded(context.bot, query.message.chat_id,
            "ᴘʟᴇᴀsᴇ ᴊᴏɪɴ ᴀʟʟ ʀᴇǫᴜɪʀᴇᴅ ᴄʜᴀɴɴᴇʟs, ᴛʜᴇɴ ᴛᴀᴘ ᴛʜᴇ ᴄʜᴇᴄᴋ ʙᴜᴛᴛᴏɴ.",
            image_url=context.application.bot_data["image_url"],
            image_path=context.application.bot_data["image_path"],
            small_caps=context.application.bot_data["small_caps"],
            reply_markup=_fsub_markup(missing, slug))
        return
    await query.answer("Membership verified.")
    from types import SimpleNamespace
    synthetic = SimpleNamespace(
        effective_chat=query.message.chat,
        effective_user=query.from_user,
    )
    await open_public_entry(synthetic, context, slug)


async def open_public_entry(update: Update, context, slug: str) -> bool:
    db = context.application.bot_data["db"]
    row = await db.require().fetchrow(
        "SELECT id,kind,channel_id,target_url,title,is_active FROM link_public_entries WHERE clone_id=$1 AND slug=$2",
        context.application.bot_data["clone_id"], slug,
    )
    if not row:
        return False
    if not row["is_active"]:
        await send_branded(context.bot, update.effective_chat.id,
            "ᴛʜɪs ᴘᴜʙʟɪᴄ ʟɪɴᴋ ʜᴀs ʙᴇᴇɴ ᴅɪsᴀʙʟᴇᴅ ʙʏ ɪᴛs ᴏᴡɴᴇʀ.",
            image_url=context.application.bot_data["image_url"],
            image_path=context.application.bot_data["image_path"],
            small_caps=context.application.bot_data["small_caps"])
        return True
    missing = await _missing_fsub(context, update.effective_user.id)
    if missing:
        await send_branded(context.bot, update.effective_chat.id,
            "ᴘʟᴇᴀsᴇ ᴊᴏɪɴ ᴛʜᴇ ғᴏʟʟᴏᴡɪɴɢ ʀᴇǫᴜɪʀᴇᴅ ᴄʜᴀɴɴᴇʟs ᴛᴏ ᴄᴏɴᴛɪɴᴜᴇ.",
            image_url=context.application.bot_data["image_url"],
            image_path=context.application.bot_data["image_path"],
            small_caps=context.application.bot_data["small_caps"],
            reply_markup=_fsub_markup(missing, slug))
        return True
    if row["kind"] == "channel":
        try:
            url, expires = await genlink_for_channel(context, int(row["channel_id"]), update.effective_user.id)
            seconds = max(0, int((expires - datetime.now(timezone.utc)).total_seconds()))
            body = f"Your invitation to {row['title']} is ready. This individual invite expires in approximately {seconds} seconds."
            markup = keyboard_from_buttons([[{"text": "· ᴊᴏɪɴ ᴄʜᴀɴɴᴇʟ ·", "url": url}]], small_caps=True)
        except Exception as exc:
            body = f"An invitation could not be generated: {type(exc).__name__}. Please contact the channel administrator."
            markup = None
    else:
        body = f"{row['title']}\\n\\nThis saved destination link does not have an automatic expiry. It remains available until its owner disables this entry or the destination itself becomes unavailable."
        markup = keyboard_from_buttons([[{"text": "· ᴏᴘᴇɴ ʟɪɴᴋ ·", "url": row["target_url"]}]], small_caps=True)
    await send_branded(context.bot, update.effective_chat.id, body,
        image_url=context.application.bot_data["image_url"], image_path=context.application.bot_data["image_path"],
        small_caps=context.application.bot_data["small_caps"], reply_markup=markup)
    return True

async def addch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update, context): return
    if len(context.args) != 1:
        body = "Usage: `/addch CHANNEL_ID`. The bot must be an administrator with invite-link permissions."
    else:
        try:
            channel_id = int(context.args[0]); chat = await context.bot.get_chat(channel_id)
            me = await context.bot.get_me(); member = await context.bot.get_chat_member(channel_id, me.id)
            can_invite = isinstance(member, ChatMemberOwner) or (
                isinstance(member, ChatMemberAdministrator) and bool(getattr(member, "can_invite_users", False))
            )
            if not can_invite:
                body = "The bot is not an administrator with can_invite_users permission in that channel."
            else:
                await context.application.bot_data["db"].require().execute(
                    "INSERT INTO link_channels(clone_id,channel_id,title,approval_enabled) VALUES($1,$2,$3,FALSE) ON CONFLICT(clone_id,channel_id) DO UPDATE SET title=EXCLUDED.title",
                    context.application.bot_data["clone_id"], channel_id, chat.title or str(channel_id))
                slug = _public_slug(channel_id)
                await context.application.bot_data["db"].require().execute(
                    """INSERT INTO link_public_entries(clone_id,slug,kind,channel_id,title,created_by,is_active)
                       VALUES($1,$2,'channel',$3,$4,$5,TRUE)
                       ON CONFLICT(clone_id,slug) DO UPDATE SET channel_id=EXCLUDED.channel_id,
                       title=EXCLUDED.title,is_active=TRUE""",
                    context.application.bot_data["clone_id"], slug, channel_id, chat.title or str(channel_id), update.effective_user.id)
                me = await context.bot.get_me()
                public_url = f"https://t.me/{me.username}?start={slug}"
                body = f"✅ Channel registered: {chat.title} (`{channel_id}`).\\n\\nPermanent public bot link (share this):\\n{public_url}\\n\\nEach /start through this link generates a fresh channel invite using this channel's configured TTL."
        except (ValueError, TypeError): body = "Channel ID must be numeric."
        except Exception as exc: body = f"Could not register channel: {type(exc).__name__}. Check bot membership and permissions."
    await reply(update, context, body)



async def newlink(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update, context): return
    if not context.args:
        body = "Usage: /newlink HTTPS_URL [optional label]"
    else:
        url = context.args[0].strip()
        parsed = urlparse(url)
        if parsed.scheme not in {"https", "http"} or not parsed.netloc or parsed.username or parsed.password:
            body = "Please provide a valid public HTTP(S) URL."
        else:
            import secrets
            slug = "url_" + secrets.token_urlsafe(9)
            title = " ".join(context.args[1:]).strip() or "Saved link"
            entry = await context.application.bot_data["db"].require().fetchrow(
                """INSERT INTO link_public_entries(clone_id,slug,kind,target_url,title,created_by,is_active)
                   VALUES($1,$2,'external',$3,$4,$5,TRUE) RETURNING id""",
                context.application.bot_data["clone_id"], slug, url, title, update.effective_user.id)
            me = await context.bot.get_me()
            public_url = f"https://t.me/{me.username}?start={slug}"
            body = f"Permanent bot link created · Entry ID: {entry['id']} · {title}:\\n{public_url}\\n\\nThe destination URL is stored unchanged and will not be auto-expired by this bot."
    await reply(update, context, body)




async def publiclinks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update, context): return
    rows = await context.application.bot_data["db"].require().fetch(
        """SELECT id,kind,title,slug,is_active,channel_id,target_url FROM link_public_entries
           WHERE clone_id=$1 ORDER BY id DESC LIMIT 50""", context.application.bot_data["clone_id"])
    if not rows:
        body = "No public bot-link entries have been created."
    else:
        me = await context.bot.get_me()
        lines = []
        for row in rows:
            state = "active" if row["is_active"] else "disabled"
            target = f"channel {row['channel_id']}" if row["kind"] == "channel" else "saved external URL"
            public_url = f"https://t.me/{me.username}?start={row['slug']}"
            lines.append(f"#{row['id']} · {row['title']} · {target} · {state}\\n{public_url}")
        body = "**ᴘᴜʙʟɪᴄ ʙᴏᴛ ʟɪɴᴋs**\\n\\n" + "\\n".join(lines)
    await reply(update, context, body)

async def deletelink(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update, context): return
    if len(context.args) != 1 or not context.args[0].isdigit():
        body = "Usage: /deletelink ENTRY_ID"
    else:
        result = await context.application.bot_data["db"].require().execute(
            """UPDATE link_public_entries SET is_active=FALSE WHERE clone_id=$1 AND id=$2 AND is_active=TRUE""",
            context.application.bot_data["clone_id"], int(context.args[0]))
        body = "Public bot-link entry disabled. Its original external URL was not modified." if result.endswith("1") else "Active entry not found."
    await reply(update, context, body)


async def setttl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update, context): return
    if len(context.args) != 2 or not all(x.lstrip("-").isdigit() for x in context.args):
        body = "Usage: /setttl CHANNEL_ID SECONDS (60–604800). Applies to future invitations only."
    else:
        cid, ttl = map(int, context.args)
        if ttl < 60 or ttl > 604800:
            body = "TTL must be between 60 and 604800 seconds."
        else:
            result = await context.application.bot_data["db"].require().execute(
                "UPDATE link_channels SET default_ttl_seconds=$1 WHERE clone_id=$2 AND channel_id=$3",
                ttl, context.application.bot_data["clone_id"], cid)
            body = f"Future invitation TTL for channel {cid} set to {ttl} seconds. Existing invites are unchanged." if result.endswith("1") else "Channel not found."
    await reply(update, context, body)

async def delch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update, context): return
    if len(context.args) != 1:
        body = "Usage: `/delch CHANNEL_ID`"
    else:
        try:
            cid = int(context.args[0])
            result = await context.application.bot_data["db"].require().execute(
                "DELETE FROM link_channels WHERE clone_id=$1 AND channel_id=$2",
                context.application.bot_data["clone_id"], cid)
            await context.application.bot_data["db"].require().execute(
                "UPDATE link_public_entries SET is_active=FALSE WHERE clone_id=$1 AND kind='channel' AND channel_id=$2",
                context.application.bot_data["clone_id"], cid)
            body = "Channel removed and its permanent public bot entry disabled. Previously issued Telegram invites are not automatically revoked." if result.endswith("1") else "Channel not found."
        except ValueError: body = "Channel ID must be numeric."
    await reply(update, context, body)

async def channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update, context): return
    rows = await context.application.bot_data["db"].require().fetch(
        "SELECT channel_id,title,default_ttl_seconds,approval_enabled FROM link_channels WHERE clone_id=$1 ORDER BY title LIMIT 80",
        context.application.bot_data["clone_id"])
    body = "**ʀᴇɢɪsᴛᴇʀᴇᴅ ᴄʜᴀɴɴᴇʟs**\n\n" + ("\n".join(f"{r['title']} · `{r['channel_id']}` · TTL {r['default_ttl_seconds']}s" for r in rows) if rows else "No channels registered.")
    await reply(update, context, body)

async def genlink_for_channel(context, channel_id: int, user_id: int, request_mode: bool = False, ttl: int | None = None):
    row = await context.application.bot_data["db"].require().fetchrow(
        "SELECT default_ttl_seconds,title FROM link_channels WHERE clone_id=$1 AND channel_id=$2",
        context.application.bot_data["clone_id"], channel_id)
    if not row: raise ValueError("Channel is not registered. Use /addch first.")
    seconds = ttl if ttl is not None else int(row["default_ttl_seconds"])
    if seconds < 60 or seconds > 604800: raise ValueError("TTL must be between 60 and 604800 seconds.")
    expires = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    invite = await context.bot.create_chat_invite_link(
        chat_id=channel_id, expire_date=expires, member_limit=None,
        creates_join_request=request_mode, name=f"clone-{context.application.bot_data['clone_id']}"[:32])
    await context.application.bot_data["db"].require().execute(
        "INSERT INTO link_invites(clone_id,channel_id,invite_link,request_link,expire_at,created_by) VALUES($1,$2,$3,$4,$5,$6)",
        context.application.bot_data["clone_id"], channel_id, invite.invite_link, request_mode, expires, user_id)
    return invite.invite_link, expires

async def genlink(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update, context): return
    if not context.args:
        body = "Usage: `/genlink CHANNEL_ID [request] [TTL_SECONDS]`"
    else:
        try:
            channel_id = int(context.args[0]); request_mode = "request" in [x.lower() for x in context.args[1:]]
            ttl = next((int(x) for x in context.args[1:] if x.isdigit()), None)
            url, expires = await genlink_for_channel(context, channel_id, update.effective_user.id, request_mode, ttl)
            body = f"✅ Invite link for `{channel_id}`:\n{url}\nExpires: {expires.isoformat()}\nMode: {'join request' if request_mode else 'normal join'}"
        except Exception as exc: body = f"Link creation failed: {type(exc).__name__}: {str(exc)[:180]}"
    await reply(update, context, body, "link.invite_created")

async def bulklink(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update, context): return
    ids=[]
    try: ids=[int(x) for x in context.args]
    except ValueError: pass
    if not ids or len(ids)>20:
        body = "Usage: `/bulklink CHANNEL_ID1 CHANNEL_ID2 ...` (up to 20 channels)."
    else:
        result=[]
        for cid in ids:
            try:
                url, exp = await genlink_for_channel(context, cid, update.effective_user.id)
                result.append(f"`{cid}` — {url}")
            except Exception as exc: result.append(f"`{cid}` — failed ({type(exc).__name__})")
        body = "**ʙᴜʟᴋ ɪɴᴠɪᴛᴇ ʀᴇsᴜʟᴛs**\n\n" + "\n".join(result)
    await reply(update, context, body)

async def links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update, context): return
    rows = await context.application.bot_data["db"].require().fetch(
        "SELECT id,channel_id,invite_link,request_link,expire_at,revoked FROM link_invites WHERE clone_id=$1 ORDER BY id DESC LIMIT 30",
        context.application.bot_data["clone_id"])
    body = "**ʀᴇᴄᴇɴᴛ ɪɴᴠɪᴛᴇ ʟɪɴᴋs**\n\n" + ("\n".join(f"#{r['id']} · `{r['channel_id']}` · {'request' if r['request_link'] else 'normal'} · {'revoked' if r['revoked'] else 'active'}\n{r['invite_link']}" for r in rows) if rows else "No generated links.")
    await reply(update, context, body)

async def revoke_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update, context): return
    if len(context.args)!=1:
        body = "Usage: `/revoke_links CHANNEL_ID`"
    else:
        try:
            cid=int(context.args[0]); rows=await context.application.bot_data["db"].require().fetch(
                "SELECT id,invite_link FROM link_invites WHERE clone_id=$1 AND channel_id=$2 AND revoked=FALSE",
                context.application.bot_data["clone_id"],cid)
            revoked=0
            for row in rows:
                try:
                    await context.bot.revoke_chat_invite_link(cid,row["invite_link"]); revoked+=1
                    await context.application.bot_data["db"].require().execute("UPDATE link_invites SET revoked=TRUE WHERE id=$1",row["id"])
                except Exception as exc: log.warning("Invite revoke failed: %s",type(exc).__name__)
            body=f"Revoked {revoked}/{len(rows)} tracked links for `{cid}`."
        except ValueError: body="Channel ID must be numeric."
    await reply(update, context, body)

async def bulkexpire(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update, context): return
    if len(context.args)!=2 or not all(x.lstrip('-').isdigit() for x in context.args):
        body="Usage: `/bulkexpire CHANNEL_ID TTL_SECONDS` (sets policy for future links; existing links are not retroactively changed)."
    else:
        cid,ttl=map(int,context.args)
        if ttl<60 or ttl>604800: body="TTL must be 60–604800 seconds."
        else:
            result=await context.application.bot_data["db"].require().execute(
                "UPDATE link_channels SET default_ttl_seconds=$1 WHERE clone_id=$2 AND channel_id=$3",ttl,context.application.bot_data["clone_id"],cid)
            body="Default invite expiry policy updated for future links." if result.endswith("1") else "Channel not found."
    await reply(update, context, body)

async def setapproval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update, context): return
    if len(context.args)!=3 or context.args[1].lower() not in {"auto","manual"} or not context.args[2].isdigit():
        body="Usage: `/setapproval CHANNEL_ID auto|manual DELAY_SECONDS`"
    else:
        cid=int(context.args[0]); enabled=context.args[1].lower()=="auto"; delay=int(context.args[2])
        if delay<0 or delay>3600: body="Delay must be 0–3600 seconds."
        else:
            result=await context.application.bot_data["db"].require().execute(
                "UPDATE link_channels SET approval_enabled=$1,approval_delay_seconds=$2 WHERE clone_id=$3 AND channel_id=$4",
                enabled,delay,context.application.bot_data["clone_id"],cid)
            body="Approval policy updated." if result.endswith("1") else "Channel not found."
    await reply(update, context, body)

async def add_fsub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update, context): return
    if len(context.args)!=2 or context.args[1].lower() not in {"normal","request"}:
        body="Usage: `/add_fsub CHANNEL_ID normal|request`"
    else:
        try:
            cid=int(context.args[0])
            await context.bot.get_chat(cid)
            me = await context.bot.get_me()
            member = await context.bot.get_chat_member(cid, me.id)
            if getattr(member, "status", "") not in {"administrator", "creator"}:
                raise PermissionError("Bot must be an administrator in each FSub channel to verify membership.")
            await context.application.bot_data["db"].require().execute(
                "INSERT INTO link_fsub_channels(clone_id,channel_id,mode) VALUES($1,$2,$3) ON CONFLICT(clone_id,channel_id) DO UPDATE SET mode=EXCLUDED.mode",
                context.application.bot_data["clone_id"],cid,context.args[1].lower())
            body="Force-sub channel added. Ensure the bot can verify membership."
        except Exception as exc: body=f"Could not add FSub channel: {type(exc).__name__}."
    await reply(update, context, body)

async def del_fsub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update, context): return
    if len(context.args)!=1: body="Usage: `/del_fsub CHANNEL_ID`"
    else:
        result=await context.application.bot_data["db"].require().execute(
            "DELETE FROM link_fsub_channels WHERE clone_id=$1 AND channel_id=$2",context.application.bot_data["clone_id"],int(context.args[0]))
        body="Force-sub channel removed." if result.endswith("1") else "Force-sub channel not found."
    await reply(update, context, body)

async def fsub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update, context): return
    rows=await context.application.bot_data["db"].require().fetch(
        "SELECT channel_id,mode FROM link_fsub_channels WHERE clone_id=$1 ORDER BY channel_id",context.application.bot_data["clone_id"])
    body="**ғᴏʀᴄᴇ sᴜʙsᴄʀɪᴘᴛɪᴏɴ**\n\n"+("\n".join(f"`{r['channel_id']}` · {r['mode']}" for r in rows) if rows else "No FSub channels.")
    await reply(update, context, body)

async def reqmode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update, context): return
    if not context.args or context.args[0].lower() not in {"on","off"}: body="Usage: `/reqmode on|off`"
    else:
        await context.application.bot_data["db"].require().execute(
            "INSERT INTO link_settings(clone_id,setting_key,setting_value) VALUES($1,'reqmode',$2) ON CONFLICT(clone_id,setting_key) DO UPDATE SET setting_value=EXCLUDED.setting_value,updated_at=NOW()",
            context.application.bot_data["clone_id"],context.args[0].lower())
        body=f"Automatic request approval {context.args[0].lower()}."
    await reply(update, context, body)

async def reqtime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update, context): return
    if not context.args or not context.args[0].isdigit(): body="Usage: `/reqtime SECONDS`"
    else:
        delay=int(context.args[0])
        if delay>3600: body="Delay must be at most 3600 seconds."
        else:
            await context.application.bot_data["db"].require().execute(
                "INSERT INTO link_settings(clone_id,setting_key,setting_value) VALUES($1,'reqtime',$2) ON CONFLICT(clone_id,setting_key) DO UPDATE SET setting_value=EXCLUDED.setting_value,updated_at=NOW()",
                context.application.bot_data["clone_id"],str(delay))
            body=f"Global request delay set to {delay} seconds."
    await reply(update, context, body)

async def _record_join_status(db, data, status):
    await db.require().execute(
        """INSERT INTO link_join_events(clone_id,channel_id,user_id,event_status) VALUES($1,$2,$3,$4)""",
        data["clone_id"], data["channel_id"], data["user_id"], status)
    await db.require().execute(
        """UPDATE link_pending_join_requests SET status=$1,updated_at=NOW()
           WHERE clone_id=$2 AND channel_id=$3 AND user_id=$4""",
        status, data["clone_id"], data["channel_id"], data["user_id"])


async def _approve_join_request(context, data):
    db = context.application.bot_data["db"]
    try:
        await context.bot.approve_chat_join_request(data["channel_id"], data["user_id"])
        status = "approved"
    except Exception as exc:
        log.warning("Join request approval failed: %s", type(exc).__name__)
        status = "failed"
    await _record_join_status(db, data, status)


async def _approve_join_request_job(context: ContextTypes.DEFAULT_TYPE):
    await _approve_join_request(context, context.job.data)


async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    req = update.chat_join_request
    clone_id = context.application.bot_data["clone_id"]
    db = context.application.bot_data["db"]
    data = {"clone_id": clone_id, "channel_id": req.chat.id, "user_id": req.from_user.id}
    await db.require().execute(
        """INSERT INTO link_pending_join_requests(clone_id,channel_id,user_id,status)
           VALUES($1,$2,$3,'pending')
           ON CONFLICT(clone_id,channel_id,user_id) DO UPDATE SET
           requested_at=NOW(),status='pending',updated_at=NOW()""",
        clone_id, req.chat.id, req.from_user.id)
    row = await db.require().fetchrow(
        "SELECT approval_enabled,approval_delay_seconds FROM link_channels WHERE clone_id=$1 AND channel_id=$2",
        clone_id, req.chat.id)
    if not row or not row["approval_enabled"]:
        return
    setting = await db.require().fetchrow(
        "SELECT setting_value FROM link_settings WHERE clone_id=$1 AND setting_key='reqmode'", clone_id)
    if setting and setting["setting_value"] == "off":
        return
    delay = int(row["approval_delay_seconds"])
    if not delay:
        global_delay = await db.require().fetchrow(
            "SELECT setting_value FROM link_settings WHERE clone_id=$1 AND setting_key='reqtime'", clone_id)
        delay = int(global_delay["setting_value"]) if global_delay else 0
    if delay:
        context.job_queue.run_once(_approve_join_request_job, when=delay, data=data,
                                   name=f"approve-{clone_id}-{req.chat.id}-{req.from_user.id}")
    else:
        await _approve_join_request(context, data)


async def joinrequests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update, context): return
    rows = await context.application.bot_data["db"].require().fetch(
        """SELECT channel_id,user_id,requested_at FROM link_pending_join_requests
           WHERE clone_id=$1 AND status='pending' ORDER BY requested_at LIMIT 40""",
        context.application.bot_data["clone_id"])
    body = "**ᴘᴇɴᴅɪɴɢ ᴊᴏɪɴ ʀᴇǫᴜᴇsᴛs**\\n\\n" + (
        "\\n".join(f"Channel {row['channel_id']} · User {row['user_id']} · {row['requested_at']}" for row in rows)
        if rows else "No pending requests.")
    await reply(update, context, body)


async def approve_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update, context): return
    if len(context.args) != 2 or not all(x.lstrip("-").isdigit() for x in context.args):
        body = "Usage: /approve USER_ID CHANNEL_ID"
    else:
        user_id, channel_id = int(context.args[0]), int(context.args[1])
        data = {"clone_id": context.application.bot_data["clone_id"], "channel_id": channel_id, "user_id": user_id}
        try:
            await context.bot.approve_chat_join_request(channel_id, user_id)
            await _record_join_status(context.application.bot_data["db"], data, "approved")
            body = f"Join request approved for user {user_id} in channel {channel_id}."
        except Exception as exc:
            body = f"Approval failed: {type(exc).__name__}. The request may no longer be pending."
    await reply(update, context, body)


async def decline_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update, context): return
    if len(context.args) != 2 or not all(x.lstrip("-").isdigit() for x in context.args):
        body = "Usage: /decline USER_ID CHANNEL_ID"
    else:
        user_id, channel_id = int(context.args[0]), int(context.args[1])
        data = {"clone_id": context.application.bot_data["clone_id"], "channel_id": channel_id, "user_id": user_id}
        try:
            await context.bot.decline_chat_join_request(channel_id, user_id)
            await _record_join_status(context.application.bot_data["db"], data, "declined")
            body = f"Join request declined for user {user_id} in channel {channel_id}."
        except Exception as exc:
            body = f"Decline failed: {type(exc).__name__}. The request may no longer be pending."
    await reply(update, context, body)

async def shorten(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update, context): return
    if not context.args:
        body="Usage: `/shorten https://example.com/long-url`"
    else:
        url=context.args[0]; parsed=urlparse(url)
        if parsed.scheme not in {"https","http"} or not parsed.netloc:
            body="Please provide a valid HTTP(S) URL."
        else:
            db=context.application.bot_data["db"]
            config=await db.require().fetchrow(
                "SELECT setting_value FROM link_settings WHERE clone_id=$1 AND setting_key='shortener_config'",
                context.application.bot_data["clone_id"])
            if not config:
                body="Shortener is not configured. An owner must use `/set_api HTTPS_ENDPOINT API_KEY`."
                await db.require().execute("INSERT INTO link_shortener_events(clone_id,original_url,status) VALUES($1,$2,'not_configured')",context.application.bot_data["clone_id"],url)
            else:
                import json
                try:
                    cfg=json.loads(config["setting_value"])
                    endpoint=cfg["endpoint"]
                    _validate_shortener_endpoint(endpoint)
                    api_key=_shortener_fernet().decrypt(cfg["api_key"].encode()).decode()
                except (ValueError, InvalidToken, RuntimeError, KeyError, TypeError) as exc:
                    body=f"Shortener security configuration error: {str(exc)[:160]}"
                else:
                    try:
                        async with httpx.AsyncClient(timeout=15,follow_redirects=False,trust_env=False) as client:
                            response=await client.get(endpoint,params={"api":api_key,"url":url})
                            response.raise_for_status(); data=response.json()
                        short=data.get("shortenedUrl") or data.get("short_url") or data.get("url")
                        if not short: raise ValueError("Provider response did not contain a shortened URL")
                        await db.require().execute("INSERT INTO link_shortener_events(clone_id,original_url,shortened_url,status,provider) VALUES($1,$2,$3,'success',$4)",context.application.bot_data["clone_id"],url,short,endpoint)
                        body=f"✅ ʏᴏᴜʀ sʜᴏʀᴛᴇɴᴇᴅ ʟɪɴᴋ:\n{short}"
                    except Exception as exc:
                        await db.require().execute("INSERT INTO link_shortener_events(clone_id,original_url,status,provider) VALUES($1,$2,'failed',$3)",context.application.bot_data["clone_id"],url,endpoint)
                        body=f"Shortener failed: {type(exc).__name__}. The original URL is unchanged."
    await reply(update, context, body)

async def set_api(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != context.application.bot_data["owner_id"]:
        return
    if len(context.args)!=2:
        body="Usage: /set_api HTTPS_ENDPOINT API_KEY. Owner only."
    else:
        endpoint,key=context.args
        try:
            _validate_shortener_endpoint(endpoint)
            encrypted_key=_shortener_fernet().encrypt(key.encode()).decode()
            import json
            await context.application.bot_data["db"].require().execute(
                "INSERT INTO link_settings(clone_id,setting_key,setting_value) VALUES($1,'shortener_config',$2) ON CONFLICT(clone_id,setting_key) DO UPDATE SET setting_value=EXCLUDED.setting_value,updated_at=NOW()",
                context.application.bot_data["clone_id"],json.dumps({"endpoint":endpoint,"api_key":encrypted_key}))
            body="Shortener configuration saved with encrypted API credentials."
        except Exception as exc:
            body=f"Shortener configuration rejected: {str(exc)[:180]}"
    await reply(update, context, body)

async def shortnerstatus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update, context): return
    row=await context.application.bot_data["db"].require().fetchrow(
        "SELECT setting_value FROM link_settings WHERE clone_id=$1 AND setting_key='shortener_config'",context.application.bot_data["clone_id"])
    body="Shortener configured." if row else "Shortener is not configured."
    await reply(update, context, body)

async def shortnerstats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update, context): return
    row=await context.application.bot_data["db"].require().fetchrow(
        "SELECT COUNT(*) total,COUNT(*) FILTER(WHERE status='success') successful,COUNT(*) FILTER(WHERE status='failed') failed FROM link_shortener_events WHERE clone_id=$1",context.application.bot_data["clone_id"])
    await reply(update, context,f"**sʜᴏʀᴛᴇɴᴇʀ sᴛᴀᴛs**\nTotal: {row['total']}\nSuccessful: {row['successful']}\nFailed: {row['failed']}")

async def linkhistory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update, context): return
    rows=await context.application.bot_data["db"].require().fetch(
        "SELECT original_url,shortened_url,status,created_at FROM link_shortener_events WHERE clone_id=$1 ORDER BY id DESC LIMIT 15",context.application.bot_data["clone_id"])
    body="**ʟɪɴᴋ ʜɪsᴛᴏʀʏ**\n\n"+("\n".join(f"{r['status']} · {r['original_url'][:90]}" for r in rows) if rows else "No history.")
    await reply(update, context, body)

async def channelstats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update,context): return
    if not context.args: body="Usage: `/channelstats CHANNEL_ID`"
    else:
        cid=int(context.args[0]); row=await context.application.bot_data["db"].require().fetchrow(
            "SELECT COUNT(*) total,COUNT(*) FILTER(WHERE event_status='approved') approved,COUNT(*) FILTER(WHERE event_status='failed') failed FROM link_join_events WHERE clone_id=$1 AND channel_id=$2",context.application.bot_data["clone_id"],cid)
        body=f"**ᴄʜᴀɴɴᴇʟ ᴊᴏɪɴ sᴛᴀᴛs**\nChannel: `{cid}`\nTotal: {row['total']}\nApproved: {row['approved']}\nFailed: {row['failed']}"
    await reply(update,context,body)

async def schedulelink(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update, context):
        return
    if len(context.args) < 2:
        body = "Usage: /schedulelink CHANNEL_ID YYYY-MM-DDTHH:MM:SS+05:30 [request]"
    else:
        try:
            channel_id = int(context.args[0])
            when = datetime.fromisoformat(context.args[1])
            if when.tzinfo is None:
                raise ValueError("Include a timezone offset, for example +05:30.")
            delay = (when - datetime.now(when.tzinfo)).total_seconds()
            if delay <= 0 or delay > 30 * 86400:
                raise ValueError("Choose a time within the next 30 days.")
            exists = await context.application.bot_data["db"].require().fetchval(
                "SELECT 1 FROM link_channels WHERE clone_id=$1 AND channel_id=$2",
                context.application.bot_data["clone_id"], channel_id)
            if not exists:
                raise ValueError("Register the channel with /addch first.")
            request_mode = "request" in [item.lower() for item in context.args[2:]]
            row = await context.application.bot_data["db"].require().fetchrow(
                """INSERT INTO link_scheduled_jobs
                   (clone_id,channel_id,user_id,request_mode,scheduled_at)
                   VALUES($1,$2,$3,$4,$5) RETURNING id""",
                context.application.bot_data["clone_id"], channel_id,
                update.effective_user.id, request_mode, when)
            body = f"Scheduled invitation job #{row['id']} for {when.isoformat()}. It is stored in PostgreSQL and survives bot restarts."
        except Exception as exc:
            body = f"Could not schedule invitation: {str(exc)[:180]}"
    await reply(update, context, body)


async def scheduled_link_worker(context: ContextTypes.DEFAULT_TYPE):
    db = context.application.bot_data["db"]
    clone_id = context.application.bot_data["clone_id"]
    while True:
        async with db.require().acquire() as conn:
            async with conn.transaction():
                job = await conn.fetchrow(
                    """SELECT id,channel_id,user_id,request_mode FROM link_scheduled_jobs
                       WHERE clone_id=$1 AND status='pending' AND scheduled_at<=NOW()
                       ORDER BY scheduled_at,id FOR UPDATE SKIP LOCKED LIMIT 1""",
                    clone_id)
                if not job:
                    return
                await conn.execute(
                    "UPDATE link_scheduled_jobs SET status='processing' WHERE id=$1", job["id"])
        try:
            url, expires = await genlink_for_channel(
                context, int(job["channel_id"]), int(job["user_id"]), bool(job["request_mode"]))
            await send_branded(
                context.bot, int(job["user_id"]),
                f"Your scheduled channel invitation is ready:\\n{url}\\nExpires: {expires.isoformat()}",
                image_url=context.application.bot_data["image_url"],
                image_path=context.application.bot_data["image_path"],
                small_caps=context.application.bot_data["small_caps"])
            await db.require().execute(
                """UPDATE link_scheduled_jobs SET status='completed',invite_url=$1,finished_at=NOW()
                   WHERE id=$2""", url, job["id"])
        except Exception as exc:
            log.exception("Scheduled invitation job %s failed", job["id"])
            await db.require().execute(
                """UPDATE link_scheduled_jobs SET status='failed',error_detail=$1,finished_at=NOW()
                   WHERE id=$2""", f"{type(exc).__name__}: {str(exc)[:300]}", job["id"])

async def scheduledlinks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update, context): return
    rows = await context.application.bot_data["db"].require().fetch(
        """SELECT id,channel_id,scheduled_at,status,error_detail FROM link_scheduled_jobs
           WHERE clone_id=$1 ORDER BY id DESC LIMIT 30""",
        context.application.bot_data["clone_id"])
    body = "**sᴄʜᴇᴅᴜʟᴇᴅ ɪɴᴠɪᴛᴀᴛɪᴏɴs**\\n\\n" + (
        "\\n".join(f"#{row['id']} · {row['channel_id']} · {row['scheduled_at']} · {row['status']}" for row in rows)
        if rows else "No scheduled invitations.")
    await reply(update, context, body)


async def cancelschedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update, context): return
    if len(context.args) != 1 or not context.args[0].isdigit():
        body = "Usage: /cancelschedule JOB_ID"
    else:
        result = await context.application.bot_data["db"].require().execute(
            """UPDATE link_scheduled_jobs SET status='cancelled',finished_at=NOW()
               WHERE clone_id=$1 AND id=$2 AND status='pending'""",
            context.application.bot_data["clone_id"], int(context.args[0]))
        body = "Scheduled invitation cancelled." if result.endswith("1") else "Pending job not found; it may already be processing or finished."
    await reply(update, context, body)


async def apiusage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await shortnerstats(update, context)


async def requeststats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update, context): return
    rows = await context.application.bot_data["db"].require().fetch(
        """SELECT status,COUNT(*) AS total FROM link_pending_join_requests
           WHERE clone_id=$1 GROUP BY status ORDER BY status""", context.application.bot_data["clone_id"])
    body = "**ᴊᴏɪɴ ʀᴇǫᴜᴇsᴛ ᴀɴᴀʟʏᴛɪᴄs**\\n\\n" + (
        "\\n".join(f"{row['status']}: {row['total']}" for row in rows) if rows else "No request history.")
    await reply(update, context, body)


async def requesthistory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update, context): return
    rows = await context.application.bot_data["db"].require().fetch(
        """SELECT channel_id,user_id,status,requested_at,updated_at FROM link_pending_join_requests
           WHERE clone_id=$1 ORDER BY requested_at DESC LIMIT 30""", context.application.bot_data["clone_id"])
    body = "**ᴊᴏɪɴ ʀᴇǫᴜᴇsᴛ ʜɪsᴛᴏʀʏ**\\n\\n" + (
        "\\n".join(f"{r['status']} · channel {r['channel_id']} · user {r['user_id']} · {r['requested_at']}" for r in rows)
        if rows else "No request history.")
    await reply(update, context, body)


async def linkstats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update, context): return
    row = await context.application.bot_data["db"].require().fetchrow(
        """SELECT (SELECT COUNT(*) FROM link_public_entries WHERE clone_id=$1 AND is_active=TRUE) AS public_entries,
           (SELECT COUNT(*) FROM link_invites WHERE clone_id=$1) AS invites,
           (SELECT COUNT(*) FROM link_invites WHERE clone_id=$1 AND revoked=FALSE AND expire_at>NOW()) AS unexpired_invites,
           (SELECT COUNT(*) FROM link_channels WHERE clone_id=$1) AS channels""",
        context.application.bot_data["clone_id"])
    await reply(update, context,
        f"**ʟɪɴᴋ ᴅᴀsʜʙᴏᴀʀᴅ**\\nChannels: {row['channels']}\\nPublic entries: {row['public_entries']}\\nTotal invites: {row['invites']}\\nCurrently unexpired invites: {row['unexpired_invites']}")


async def users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update, context): return
    db = context.application.bot_data["db"].require()
    clone_id = context.application.bot_data["clone_id"]
    total = await db.fetchval("SELECT COUNT(*) FROM bot_users WHERE clone_id=$1", clone_id)
    rows = await db.fetch("SELECT user_id,is_banned,last_seen FROM bot_users WHERE clone_id=$1 ORDER BY last_seen DESC LIMIT 25", clone_id)
    body = f"**ᴜsᴇʀ ᴅᴀsʜʙᴏᴀʀᴅ** · Total: {total}\\n\\n" + (
        "\\n".join(f"{r['user_id']} · {'blocked' if r['is_banned'] else 'active'} · {r['last_seen']}" for r in rows)
        if rows else "No registered users.")
    await reply(update, context, body)


async def userinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update, context): return
    if len(context.args) != 1 or not context.args[0].isdigit():
        body = "Usage: /userinfo USER_ID"
    else:
        row = await context.application.bot_data["db"].require().fetchrow(
            "SELECT user_id,first_seen,last_seen,is_banned FROM bot_users WHERE clone_id=$1 AND user_id=$2",
            context.application.bot_data["clone_id"], int(context.args[0]))
        body = f"User: {row['user_id']}\\nFirst seen: {row['first_seen']}\\nLast seen: {row['last_seen']}\\nBlocked: {row['is_banned']}" if row else "User not found."
    await reply(update, context, body)


async def blockuser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update, context): return
    if len(context.args) != 1 or not context.args[0].isdigit():
        body = "Usage: /blockuser USER_ID"
    else:
        result = await context.application.bot_data["db"].require().execute(
            "UPDATE bot_users SET is_banned=TRUE WHERE clone_id=$1 AND user_id=$2",
            context.application.bot_data["clone_id"], int(context.args[0]))
        body = "User blocked." if result.endswith("1") else "User not found."
    await reply(update, context, body)


async def unblockuser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update, context): return
    if len(context.args) != 1 or not context.args[0].isdigit():
        body = "Usage: /unblockuser USER_ID"
    else:
        result = await context.application.bot_data["db"].require().execute(
            "UPDATE bot_users SET is_banned=FALSE WHERE clone_id=$1 AND user_id=$2",
            context.application.bot_data["clone_id"], int(context.args[0]))
        body = "User unblocked." if result.endswith("1") else "User not found."
    await reply(update, context, body)


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update, context): return
    row = await context.application.bot_data["db"].require().fetchrow(
        """SELECT (SELECT COUNT(*) FROM bot_users WHERE clone_id=$1) AS users,
           (SELECT COUNT(*) FROM link_channels WHERE clone_id=$1) AS channels,
           (SELECT COUNT(*) FROM link_public_entries WHERE clone_id=$1 AND is_active=TRUE) AS public_links,
           (SELECT COUNT(*) FROM link_join_events WHERE clone_id=$1) AS join_events""",
        context.application.bot_data["clone_id"])
    await reply(update, context,
        f"**sʏsᴛᴇᴍ sᴛᴀᴛs**\\nUsers: {row['users']}\\nChannels: {row['channels']}\\nPublic links: {row['public_links']}\\nJoin events: {row['join_events']}")


async def logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update, context): return
    rows = await context.application.bot_data["db"].require().fetch(
        """SELECT channel_id,user_id,event_status,created_at FROM link_join_events
           WHERE clone_id=$1 ORDER BY id DESC LIMIT 25""", context.application.bot_data["clone_id"])
    body = "**ʀᴇᴄᴇɴᴛ ᴊᴏɪɴ ʟᴏɢs**\\n\\n" + (
        "\\n".join(f"{r['event_status']} · channel {r['channel_id']} · user {r['user_id']} · {r['created_at']}" for r in rows)
        if rows else "No join events.")
    await reply(update, context, body)


async def security(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update, context): return
    hosts = sorted(host.strip() for host in os.getenv("SHORTENER_ALLOWED_HOSTS", "").split(",") if host.strip())
    encrypted_key = bool(os.getenv("SHORTENER_ENCRYPTION_KEY", "").strip())
    fsub_count = await context.application.bot_data["db"].require().fetchval(
        "SELECT COUNT(*) FROM link_fsub_channels WHERE clone_id=$1", context.application.bot_data["clone_id"])
    await reply(update, context,
        f"**sᴇᴄᴜʀɪᴛʏ ᴄʜᴇᴄᴋ**\\nShortener encryption key configured: {encrypted_key}\\nAllowed shortener hosts: {', '.join(hosts) if hosts else 'none'}\\nFSub channels: {fsub_count}")


async def database_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update, context): return
    try:
        value = await context.application.bot_data["db"].require().fetchval("SELECT 1")
        body = "PostgreSQL connection: healthy." if value == 1 else "PostgreSQL returned an unexpected response."
    except Exception as exc:
        body = f"Database check failed: {type(exc).__name__}."
    await reply(update, context, body)


async def diagnostics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update, context): return
    try:
        me = await context.bot.get_me()
        db = await context.application.bot_data["db"].require().fetchval("SELECT 1")
        queue = "available" if context.job_queue else "unavailable"
        body = f"Bot: @{me.username}\\nTelegram API: reachable\\nPostgreSQL: {'healthy' if db == 1 else 'unknown'}\\nJobQueue: {queue}"
    except Exception as exc:
        body = f"Diagnostics failed: {type(exc).__name__}: {str(exc)[:120]}"
    await reply(update, context, body)


async def channelpanel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await channels(update,context)

def add_link_handlers(app):
    app.add_handler(CommandHandler("addch",addch)); app.add_handler(CommandHandler("addchat",addch))
    app.add_handler(CommandHandler("newlink",newlink)); app.add_handler(CommandHandler("deletelink",deletelink)); app.add_handler(CommandHandler("setttl",setttl)); app.add_handler(CommandHandler("publiclinks",publiclinks))
    app.add_handler(CommandHandler("delch",delch)); app.add_handler(CommandHandler("delchat",delch))
    app.add_handler(CommandHandler("channels",channels)); app.add_handler(CommandHandler("channelpanel",channelpanel))
    app.add_handler(CommandHandler("genlink",genlink)); app.add_handler(CommandHandler("bulklink",bulklink)); app.add_handler(CommandHandler("links",links))
    app.add_handler(CommandHandler("revoke_links",revoke_links)); app.add_handler(CommandHandler("bulkexpire",bulkexpire))
    app.add_handler(CommandHandler("setapproval",setapproval)); app.add_handler(CommandHandler("reqmode",reqmode)); app.add_handler(CommandHandler("reqtime",reqtime))
    app.add_handler(CommandHandler("add_fsub",add_fsub)); app.add_handler(CommandHandler("del_fsub",del_fsub)); app.add_handler(CommandHandler("fsub",fsub))
    app.add_handler(CommandHandler("shorten",shorten)); app.add_handler(CommandHandler("set_api",set_api)); app.add_handler(CommandHandler("shortnerstatus",shortnerstatus)); app.add_handler(CommandHandler("shortnerstats",shortnerstats)); app.add_handler(CommandHandler("linkhistory",linkhistory))
    app.add_handler(CommandHandler("channelstats",channelstats)); app.add_handler(CommandHandler("schedulelink",schedulelink)); app.add_handler(CommandHandler("scheduledlinks",scheduledlinks)); app.add_handler(CommandHandler("cancelschedule",cancelschedule))
    app.add_handler(CommandHandler("apiusage",apiusage)); app.add_handler(CommandHandler("requeststats",requeststats)); app.add_handler(CommandHandler("requesthistory",requesthistory)); app.add_handler(CommandHandler("linkstats",linkstats))
    app.add_handler(CommandHandler("users",users)); app.add_handler(CommandHandler("userinfo",userinfo)); app.add_handler(CommandHandler("blockuser",blockuser)); app.add_handler(CommandHandler("unblockuser",unblockuser)); app.add_handler(CommandHandler("stats",stats)); app.add_handler(CommandHandler("logs",logs))
    app.add_handler(CommandHandler("security",security)); app.add_handler(CommandHandler("database",database_status)); app.add_handler(CommandHandler("diagnostics",diagnostics))
    app.add_handler(CallbackQueryHandler(check_fsub_callback, pattern=r"^fsub:check:"))
    app.add_handler(CommandHandler("joinrequests",joinrequests)); app.add_handler(CommandHandler("approve",approve_request)); app.add_handler(CommandHandler("decline",decline_request))
    app.add_handler(ChatJoinRequestHandler(handle_join_request))

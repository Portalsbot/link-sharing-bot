from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
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



def _public_slug(channel_id: int) -> str:
    return f"ch{abs(int(channel_id))}"

async def open_public_entry(update: Update, context, slug: str) -> bool:
    db = context.application.bot_data["db"]
    row = await db.require().fetchrow(
        "SELECT id,kind,channel_id,target_url,title FROM link_public_entries WHERE clone_id=$1 AND slug=$2 AND is_active=TRUE",
        context.application.bot_data["clone_id"], slug,
    )
    if not row:
        return False
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
        lines = []
        for row in rows:
            state = "active" if row["is_active"] else "disabled"
            target = f"channel {row['channel_id']}" if row["kind"] == "channel" else "saved external URL"
            lines.append(f"#{row['id']} · {row['title']} · {target} · {state}")
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
    if len(context.args) != 2 or not all(x.isdigit() for x in context.args):
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
            cid=int(context.args[0]); await context.bot.get_chat(cid)
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

async def _approve_join_request(context, data):
    db = context.application.bot_data["db"]
    try:
        await context.bot.approve_chat_join_request(data["channel_id"], data["user_id"])
        status = "approved"
    except Exception as exc:
        log.warning("Join request approval failed: %s", type(exc).__name__)
        status = "failed"
    await db.require().execute(
        "INSERT INTO link_join_events(clone_id,channel_id,user_id,event_status) VALUES($1,$2,$3,$4)",
        data["clone_id"], data["channel_id"], data["user_id"], status)


async def _approve_join_request_job(context: ContextTypes.DEFAULT_TYPE):
    await _approve_join_request(context, context.job.data)


async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    req = update.chat_join_request
    clone_id = context.application.bot_data["clone_id"]
    row = await context.application.bot_data["db"].require().fetchrow(
        "SELECT approval_enabled,approval_delay_seconds FROM link_channels WHERE clone_id=$1 AND channel_id=$2",
        clone_id, req.chat.id)
    if not row or not row["approval_enabled"]:
        return
    setting = await context.application.bot_data["db"].require().fetchrow(
        "SELECT setting_value FROM link_settings WHERE clone_id=$1 AND setting_key='reqmode'", clone_id)
    if setting and setting["setting_value"] == "off":
        return
    data = {"clone_id": clone_id, "channel_id": req.chat.id, "user_id": req.from_user.id}
    delay = int(row["approval_delay_seconds"])
    if delay:
        context.job_queue.run_once(_approve_join_request_job, when=delay, data=data,
                                   name=f"approve-{clone_id}-{req.chat.id}-{req.from_user.id}")
    else:
        await _approve_join_request(context, data)

async def shorten(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
                cfg=json.loads(config["setting_value"]); endpoint=cfg["endpoint"]
                if not endpoint.startswith("https://"):
                    body="Shortener endpoint must use HTTPS."
                else:
                    try:
                        async with httpx.AsyncClient(timeout=15,follow_redirects=False) as client:
                            response=await client.get(endpoint,params={"api":cfg["api_key"],"url":url})
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
    if not is_admin(update, context): return
    if len(context.args)!=2:
        body="Usage: `/set_api HTTPS_ENDPOINT API_KEY` (owner/admin only; endpoint must be trusted)."
    else:
        endpoint,key=context.args
        parsed=urlparse(endpoint)
        if parsed.scheme!="https" or not parsed.netloc or parsed.username or parsed.password:
            body="Use a valid HTTPS endpoint without embedded credentials."
        else:
            import json
            await context.application.bot_data["db"].require().execute(
                "INSERT INTO link_settings(clone_id,setting_key,setting_value) VALUES($1,'shortener_config',$2) ON CONFLICT(clone_id,setting_key) DO UPDATE SET setting_value=EXCLUDED.setting_value,updated_at=NOW()",
                context.application.bot_data["clone_id"],json.dumps({"endpoint":endpoint,"api_key":key}))
            body="Shortener configuration saved. Test it using /shorten."
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
    if not is_admin(update,context): return
    if len(context.args)<2: body="Usage: `/schedulelink CHANNEL_ID YYYY-MM-DDTHH:MM[:SS] [request]`"
    else:
        try:
            cid=int(context.args[0]); when=datetime.fromisoformat(context.args[1])
            if when.tzinfo is None: raise ValueError("Provide an ISO timestamp with timezone offset, e.g. +05:30")
            delay=(when-datetime.now(when.tzinfo)).total_seconds()
            if delay<=0 or delay>60*60*24*30: raise ValueError("Schedule must be in the next 30 days")
            request_mode="request" in [x.lower() for x in context.args[2:]]
            context.job_queue.run_once(_scheduled_link_job,when=delay,data={"channel_id":cid,"user_id":update.effective_user.id,"request":request_mode},name=f"invite-{context.application.bot_data['clone_id']}-{cid}-{int(when.timestamp())}")
            body=f"Invite generation scheduled for {when.isoformat()}. This in-memory schedule is lost if the bot restarts; durable scheduling is still a production integration task."
        except Exception as exc: body=f"Invalid schedule: {str(exc)[:150]}"
    await reply(update,context,body)

async def _scheduled_link_job(context: ContextTypes.DEFAULT_TYPE):
    data=context.job.data
    try:
        url,expires=await genlink_for_channel(context,data["channel_id"],data["user_id"],data["request"])
        await send_branded(context.bot,data["user_id"],f"Scheduled invitation link:\n{url}",
            image_url=context.application.bot_data["image_url"],image_path=context.application.bot_data["image_path"],
            small_caps=context.application.bot_data["small_caps"])
    except Exception as exc: log.warning("Scheduled invite failed: %s",type(exc).__name__)

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
    app.add_handler(CommandHandler("channelstats",channelstats)); app.add_handler(CommandHandler("schedulelink",schedulelink))
    app.add_handler(ChatJoinRequestHandler(handle_join_request))

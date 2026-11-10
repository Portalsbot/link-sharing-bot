"""Unified Owner/Admin force-subscription panel and user membership gate."""
from __future__ import annotations

from types import SimpleNamespace
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler,
    ApplicationHandlerStop, filters,
)
from telegram.error import TelegramError
from .branding import send_branded

DEFAULT_MESSAGE = (
    "ᴘʟᴇᴀsᴇ ᴊᴏɪɴ ᴀʟʟ ʀᴇǫᴜɪʀᴇᴅ ᴄʜᴀɴɴᴇʟs ʙᴇʟᴏᴡ, ᴛʜᴇɴ ᴛᴀᴘ "
    "· ɪ'ᴠᴇ ᴊᴏɪɴᴇᴅ · ᴛᴏ ᴄᴏɴᴛɪɴᴜᴇ."
)
KIND = "link"


def _is_admin(user_id: int, context) -> bool:
    data = context.application.bot_data
    return user_id == data["owner_id"] or user_id in data.get("admins", set())


def _close_row():
    return [InlineKeyboardButton("· ᴄʟᴏsᴇ ·", callback_data="branding:close")]


def _panel_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("· ᴀᴅᴅ ·", callback_data="fsubs:add"),
         InlineKeyboardButton("· ʀᴇᴍᴏᴠᴇ ·", callback_data="fsubs:remove")],
        [InlineKeyboardButton("· ᴇᴅɪᴛ ᴍᴇssᴀɢᴇ ·", callback_data="fsubs:edit")],
        [InlineKeyboardButton("· ʙᴀᴄᴋ ·", callback_data="fsubs:back"),
         InlineKeyboardButton("· ᴄʟᴏsᴇ ·", callback_data="fsubs:close")],
    ])


async def _send(context, chat_id: int, body: str, markup=None):
    data = context.application.bot_data
    if markup is None:
        markup = InlineKeyboardMarkup([_close_row()])
    return await send_branded(
        context.bot, chat_id, body,
        image_url=data.get("image_url"), image_path=data.get("image_path"),
        small_caps=data.get("small_caps", True), reply_markup=markup,
    )


async def _fetch_channels(context):
    db = context.application.bot_data["db"].require()
    data = context.application.bot_data
    return await db.fetch("SELECT channel_id,COALESCE(title,channel_id::text) AS title,join_url,mode FROM link_fsub_channels WHERE clone_id=$1 ORDER BY COALESCE(title,channel_id::text),channel_id", data["clone_id"])


async def _get_message(context):
    row = await context.application.bot_data["db"].require().fetchrow(
        "SELECT setting_value FROM link_settings WHERE clone_id=$1 AND setting_key='fsubs_message'",
        context.application.bot_data["clone_id"])
    return str(row["setting_value"]) if row else DEFAULT_MESSAGE


async def _set_message(context, body: str):
    await context.application.bot_data["db"].require().execute(
        """INSERT INTO link_settings(clone_id,setting_key,setting_value)
           VALUES($1,'fsubs_message',$2)
           ON CONFLICT(clone_id,setting_key) DO UPDATE SET setting_value=EXCLUDED.setting_value,updated_at=NOW()""",
        context.application.bot_data["clone_id"], body)


async def _missing_channels(context, user_id: int):
    missing = []
    for row in await _fetch_channels(context):
        channel_id = int(row["channel_id"])
        try:
            member = await context.bot.get_chat_member(channel_id, user_id)
            status = getattr(member, "status", "")
            is_member = status in {"creator", "administrator", "member"} or (
                status == "restricted" and bool(getattr(member, "is_member", False))
            )
        except TelegramError:
            is_member = False
        if is_member:
            continue
        join_url = row.get("join_url") if hasattr(row, "get") else row["join_url"]
        if not join_url:
            try:
                chat = await context.bot.get_chat(channel_id)
                if getattr(chat, "username", None):
                    join_url = f"https://t.me/{chat.username}"
                else:
                    invite = await context.bot.create_chat_invite_link(channel_id)
                    join_url = invite.invite_link
            except TelegramError:
                join_url = None
        missing.append((channel_id, str(row["title"]), join_url))
    return missing


def _gate_markup(missing):
    rows = []
    for channel_id, title, join_url in missing:
        if join_url:
            rows.append([InlineKeyboardButton(f"· ᴊᴏɪɴ {title[:35]} ·", url=join_url)])
    rows.append([InlineKeyboardButton("· ɪ'ᴠᴇ ᴊᴏɪɴᴇᴅ ·", callback_data="fsubs:check")])
    rows.append(_close_row())
    return InlineKeyboardMarkup(rows)


async def _send_gate(context, chat_id: int, missing):
    body = await _get_message(context)
    await _send(context, chat_id, body, _gate_markup(missing))


async def fsubs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id, context):
        return
    rows = await _fetch_channels(context)
    body = (
        "ғᴏʀᴄᴇ sᴜʙsᴄʀɪᴘᴛɪᴏɴ ᴍᴀɴᴀɢᴇʀ\n\n"
        f"Active FSub channels: {len(rows)}\n"
        "Add channels, remove existing channels, or edit the message shown only to users who have not joined."
    )
    await _send(context, update.effective_chat.id, body, _panel_markup())


async def _show_remove_list(context, chat_id: int):
    rows = await _fetch_channels(context)
    keyboard = [
        [InlineKeyboardButton(f"· {str(row['title'])[:25]} · {int(row['channel_id'])}", callback_data=f"fsubs:del:{int(row['channel_id'])}")]
        for row in rows[:50]
    ]
    keyboard.append([InlineKeyboardButton("· ʙᴀᴄᴋ ·", callback_data="fsubs:panel"),
                     InlineKeyboardButton("· ᴄʟᴏsᴇ ·", callback_data="fsubs:close")])
    body = "Select an active FSub channel to remove:" if rows else "No FSub channels are currently active."
    await _send(context, chat_id, body, InlineKeyboardMarkup(keyboard))


async def _back_to_settings(query, context):
    from .settings import start
    synthetic = SimpleNamespace(effective_chat=query.message.chat, effective_user=query.from_user)
    await start(synthetic, context)


async def fsubs_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    if not _is_admin(query.from_user.id, context) and query.data != "fsubs:check":
        await query.answer("Owner / Admin only.", show_alert=True)
        return
    action = query.data
    if action == "fsubs:check":
        missing = await _missing_channels(context, query.from_user.id)
        if missing:
            await query.answer("Join every required channel first.", show_alert=True)
            await _send_gate(context, query.message.chat_id, missing)
            return
        await query.answer("Membership verified.")
        pending = context.user_data.pop("fsubs_pending_payload", None)
        synthetic = SimpleNamespace(effective_chat=query.message.chat, effective_user=query.from_user)
        if pending:
            from .handlers.links import open_public_entry
            await open_public_entry(synthetic, context, pending)
        else:
            from .settings import start
            await start(synthetic, context)
        return
    await query.answer()
    if action in {"fsubs:panel", "fsubs:back"}:
        if action == "fsubs:panel":
            await fsubs_command(SimpleNamespace(effective_user=query.from_user, effective_chat=query.message.chat), context)
        else:
            await _back_to_settings(query, context)
    elif action == "fsubs:add":
        context.user_data["fsubs_input_action"] = "add"
        await _send(context, query.message.chat_id,
            "Send the numeric Telegram channel ID. The bot must be an administrator in that channel.")
    elif action == "fsubs:remove":
        await _show_remove_list(context, query.message.chat_id)
    elif action == "fsubs:edit":
        context.user_data["fsubs_input_action"] = "edit"
        current = await _get_message(context)
        await _send(context, query.message.chat_id,
            "Send the replacement message. It is displayed only to users who have not joined the required channels.\n\n"
            f"Current message:\n{current}")
    elif action == "fsubs:close":
        try:
            await query.message.delete()
        except TelegramError:
            pass
    elif action.startswith("fsubs:del:"):
        try:
            channel_id = int(action.rsplit(":", 1)[1])
            db = context.application.bot_data["db"].require()
            await db.execute("DELETE FROM link_fsub_channels WHERE clone_id=$1 AND channel_id=$2", context.application.bot_data["clone_id"], channel_id)
            await _show_remove_list(context, query.message.chat_id)
        except (ValueError, TelegramError) as exc:
            await _send(context, query.message.chat_id, f"Could not remove that channel: {type(exc).__name__}.")
    else:
        await _send(context, query.message.chat_id, "FSub panel action not recognized.", _panel_markup())


async def fsubs_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    action = context.user_data.get("fsubs_input_action")
    if not action:
        return
    if not update.effective_user or not _is_admin(update.effective_user.id, context):
        context.user_data.pop("fsubs_input_action", None)
        return
    message = update.effective_message
    text = (message.text or "").strip() if message else ""
    if not text:
        await _send(context, update.effective_chat.id, "Please send text or a numeric channel ID.")
        raise ApplicationHandlerStop
    if action == "edit":
        if len(text) > 3500:
            await _send(context, update.effective_chat.id, "The FSub message must be 3,500 characters or fewer. Send it again.")
            raise ApplicationHandlerStop
        await _set_message(context, text)
        context.user_data.pop("fsubs_input_action", None)
        await _send(context, update.effective_chat.id, "FSub message updated.", _panel_markup())
        raise ApplicationHandlerStop
    try:
        channel_id = int(text)
    except ValueError:
        await _send(context, update.effective_chat.id, "Invalid channel ID. Send the numeric Telegram channel ID.")
        raise ApplicationHandlerStop
    try:
        chat = await context.bot.get_chat(channel_id)
        me = await context.bot.get_me()
        admin = await context.bot.get_chat_member(channel_id, me.id)
        status = getattr(admin, "status", "")
        if status not in {"administrator", "creator"}:
            raise PermissionError("The bot must be an administrator in that channel.")
        if getattr(chat, "username", None):
            join_url = f"https://t.me/{chat.username}"
        else:
            if status != "creator" and not getattr(admin, "can_invite_users", False):
                raise PermissionError("The bot needs invite-user permission in private channels.")
            join_url = (await context.bot.create_chat_invite_link(channel_id)).invite_link
        await context.application.bot_data["db"].require().execute(
                """INSERT INTO link_fsub_channels(clone_id,channel_id,mode,title,join_url)
                   VALUES($1,$2,'normal',$3,$4) ON CONFLICT(clone_id,channel_id) DO UPDATE SET
                   title=EXCLUDED.title,join_url=EXCLUDED.join_url""",
                context.application.bot_data["clone_id"], channel_id, chat.title or str(channel_id), join_url)
        context.user_data.pop("fsubs_input_action", None)
        await _send(context, update.effective_chat.id,
            f"FSub channel added: {chat.title or channel_id} ({channel_id}).", _panel_markup())
    except Exception as exc:
        await _send(context, update.effective_chat.id,
            f"Could not add this FSub channel: {type(exc).__name__}: {str(exc)[:160]}\nCheck the channel ID and bot administrator permissions.")
    raise ApplicationHandlerStop


async def message_fsubs_gate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.effective_message
    if not user or not message or _is_admin(user.id, context):
        return
    text = message.text or ""
    if text and text.split()[0].split("@",1)[0].lower() == "/start":
        parts = text.split(maxsplit=1)
        context.user_data["fsubs_pending_payload"] = parts[1].strip() if len(parts) > 1 else None
    missing = await _missing_channels(context, user.id)
    if not missing:
        return
    await _send_gate(context, update.effective_chat.id, missing)
    raise ApplicationHandlerStop


async def callback_fsubs_gate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or query.data in {"branding:close", "fsubs:check"} or _is_admin(query.from_user.id, context):
        return
    missing = await _missing_channels(context, query.from_user.id)
    if not missing:
        return
    await query.answer("Join the required channels first.", show_alert=True)
    await _send_gate(context, query.message.chat_id, missing)
    raise ApplicationHandlerStop


def add_fsubs_handlers(app):
    app.add_handler(CommandHandler("fsubs", fsubs_command))
    app.add_handler(CallbackQueryHandler(fsubs_callback, pattern=r"^fsubs:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fsubs_input), group=-6)

"""Persistent text/media broadcast queue for the bot's registered users."""
from __future__ import annotations
import asyncio
import json
import logging
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import RetryAfter
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, ApplicationHandlerStop, filters
from .branding import send_branded, close_keyboard, keyboard_from_buttons
from .formatting import render_text

log = logging.getLogger(__name__)
PRODUCT = "link"
MEDIA_METHODS = {
    "photo": ("send_photo", "photo"),
    "video": ("send_video", "video"),
    "document": ("send_document", "document"),
    "audio": ("send_audio", "audio"),
    "animation": ("send_animation", "animation"),
    "voice": ("send_voice", "voice"),
}


def _is_admin(user_id, context):
    data = context.application.bot_data
    return user_id == data["owner_id"] or user_id in data.get("admins", set())


async def _send(context, chat_id, body, markup=None):
    data = context.application.bot_data
    return await send_branded(context.bot, chat_id, body,
        image_url=data["image_url"], image_path=data.get("image_path"),
        small_caps=data.get("small_caps", True), reply_markup=markup)


def _payload(message, small_caps=True):
    buttons = []
    if message.reply_markup and getattr(message.reply_markup, "inline_keyboard", None):
        for row in message.reply_markup.inline_keyboard:
            safe_row = []
            for button in row:
                if button.url and button.url.startswith(("https://", "http://")):
                    safe_row.append({"text": button.text, "url": button.url})
            if safe_row:
                buttons.append(safe_row)
    def extract_buttons(value):
        kept = []
        parsed = []
        for line in (value or "").splitlines():
            marker = line.strip()
            if marker.lower().startswith("[button]"):
                spec = marker[len("[button]"):].strip()
                if "|" not in spec:
                    raise ValueError("Button syntax: [button] LABEL | https://URL")
                label, url = [part.strip() for part in spec.split("|", 1)]
                if not label or len(label) > 64 or not url.startswith(("https://", "http://")):
                    raise ValueError("Broadcast buttons need a label (max 64 characters) and an HTTP(S) URL.")
                parsed.append({"text": label, "url": url})
            else:
                kept.append(line)
        if parsed:
            buttons.extend([[item] for item in parsed])
        return "\n".join(kept).strip()
    if message.text:
        text = extract_buttons(message.text)
        if not text:
            raise ValueError("Broadcast text cannot be empty after removing button definitions.")
        return {"kind": "text", "text": text, "buttons": buttons}
    for media_type, (method, argument) in MEDIA_METHODS.items():
        media = getattr(message, media_type, None)
        if media:
            if media_type == "photo":
                media = media[-1]
            caption = extract_buttons(message.caption or "")
            return {"kind": "media", "media_type": media_type, "file_id": media.file_id,
                    "caption": caption, "buttons": buttons}
    raise ValueError("Send text, photo, video, document, audio or animation.")


async def _deliver_one(context, chat_id, payload):
    data = context.application.bot_data
    markup = keyboard_from_buttons(payload.get("buttons", []), small_caps=data.get("small_caps", True))
    if payload["kind"] == "text":
        await _send(context, chat_id, payload["text"], markup)
        return
    await _send(context, chat_id, "ᴍᴇᴅɪᴀ ʙʀᴏᴀᴅᴄᴀsᴛ")
    media_type = payload["media_type"]
    method, argument = MEDIA_METHODS[media_type]
    buttons = list(markup.inline_keyboard) if markup else []
    buttons.append([InlineKeyboardButton("· ᴄʟᴏsᴇ ·", callback_data="branding:close")])
    args = {"chat_id": chat_id, argument: payload["file_id"], "reply_markup": InlineKeyboardMarkup(buttons)}
    caption = payload.get("caption", "")
    if caption:
        args["caption"] = render_text(caption, data.get("small_caps", True))
        args["parse_mode"] = "HTML"
    await getattr(context.bot, method)(**args)


async def _deliver(context, broadcast_id, payload, actor_id):
    db = context.application.bot_data["db"].require()
    clone_id = context.application.bot_data["clone_id"]
    rows = await db.fetch(
        "SELECT user_id FROM bot_users WHERE clone_id=$1 AND is_banned=FALSE ORDER BY user_id",
        clone_id)
    sent = failed = 0
    for row in rows:
        user_id = int(row["user_id"])
        try:
            await _deliver_one(context, user_id, payload)
            sent += 1
        except RetryAfter as exc:
            delay = exc.retry_after.total_seconds() if hasattr(exc.retry_after, "total_seconds") else float(exc.retry_after)
            await asyncio.sleep(delay + 0.25)
            try:
                await _deliver_one(context, user_id, payload)
                sent += 1
            except Exception:
                failed += 1
        except Exception as exc:
            failed += 1
            log.info("Broadcast %s delivery failed for %s: %s", broadcast_id, user_id, type(exc).__name__)
        await asyncio.sleep(0.05)
    await db.execute(
        """UPDATE bot_broadcasts SET status='completed',sent_count=$1,failed_count=$2,finished_at=NOW()
           WHERE clone_id=$3 AND id=$4""", sent, failed, clone_id, broadcast_id)
    await _send(context, actor_id, f"Broadcast #{broadcast_id} completed. Sent: {sent} · Failed: {failed}.")


async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id, context): return
    context.user_data["broadcast_capture"] = True
    context.user_data.pop("broadcast_schedule_id", None)
    await _send(context, update.effective_chat.id,
        "Send the text or media you want to broadcast. You can include URL buttons by forwarding a message with an inline URL keyboard.")


async def capture_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.effective_message
    if not user or not message or not _is_admin(user.id, context):
        return
    if context.user_data.get("broadcast_schedule_id"):
        try:
            when = datetime.fromisoformat((message.text or "").strip())
            if when.tzinfo is None or when <= datetime.now(when.tzinfo):
                raise ValueError("Use a future ISO timestamp with timezone, e.g. 2026-12-01T19:30:00+05:30.")
            job_id = int(context.user_data.pop("broadcast_schedule_id"))
            await context.application.bot_data["db"].require().execute(
                """UPDATE bot_broadcasts SET status='pending',scheduled_at=$1
                   WHERE clone_id=$2 AND id=$3 AND status='draft'""",
                when, context.application.bot_data["clone_id"], job_id)
            context.user_data["suppress_upload_once"] = True
            await _send(context, update.effective_chat.id, f"Broadcast #{job_id} scheduled for {when.isoformat()}.")
        except Exception as exc:
            await _send(context, update.effective_chat.id, f"Invalid schedule: {str(exc)[:140]}")
        raise ApplicationHandlerStop
    if not context.user_data.pop("broadcast_capture", False):
        return
    context.user_data["suppress_upload_once"] = True
    try:
        payload = _payload(message)
        row = await context.application.bot_data["db"].require().fetchrow(
            """INSERT INTO bot_broadcasts(clone_id,created_by,payload,status)
               VALUES($1,$2,$3::jsonb,'draft') RETURNING id""",
            context.application.bot_data["clone_id"], user.id, json.dumps(payload, ensure_ascii=False))
        job_id = int(row["id"])
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("· sᴇɴᴅ ɴᴏᴡ ·", callback_data=f"bcast:now:{job_id}")],
            [InlineKeyboardButton("· sᴄʜᴇᴅᴜʟᴇ ·", callback_data=f"bcast:schedule:{job_id}")],
            [InlineKeyboardButton("· ᴄᴀɴᴄᴇʟ ·", callback_data=f"bcast:cancel:{job_id}")],
        ])
        await _send(context, update.effective_chat.id, f"Broadcast draft #{job_id} is ready. Choose delivery.", markup)
    except Exception as exc:
        await _send(context, update.effective_chat.id, f"Broadcast draft failed: {str(exc)[:160]}")
    raise ApplicationHandlerStop


async def broadcast_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query: return
    if not _is_admin(query.from_user.id, context):
        await query.answer("Owner / Admin only.", show_alert=True)
        return
    await query.answer()
    _, action, raw_id = query.data.split(":")
    if not raw_id.isdigit(): return
    job_id = int(raw_id)
    db = context.application.bot_data["db"].require()
    clone_id = context.application.bot_data["clone_id"]
    row = await db.fetchrow(
        "SELECT payload,created_by,status FROM bot_broadcasts WHERE clone_id=$1 AND id=$2",
        clone_id, job_id)
    if not row or int(row["created_by"]) != query.from_user.id or row["status"] != "draft":
        await _send(context, query.message.chat_id, "Draft not found or no longer available.")
        return
    if action == "cancel":
        await db.execute("UPDATE bot_broadcasts SET status='cancelled',finished_at=NOW() WHERE clone_id=$1 AND id=$2",
                         clone_id, job_id)
        await _send(context, query.message.chat_id, f"Broadcast #{job_id} cancelled.")
    elif action == "schedule":
        context.user_data["broadcast_schedule_id"] = job_id
        await _send(context, query.message.chat_id, "Send a future ISO timestamp with timezone, e.g. 2026-12-01T19:30:00+05:30.")
    elif action == "now":
        await db.execute("UPDATE bot_broadcasts SET status='processing' WHERE clone_id=$1 AND id=$2 AND status='draft'",
                         clone_id, job_id)
        payload = row["payload"] if isinstance(row["payload"], dict) else json.loads(row["payload"])
        await _deliver(context, job_id, payload, int(row["created_by"]))


async def broadcast_worker(context: ContextTypes.DEFAULT_TYPE):
    db = context.application.bot_data["db"].require()
    clone_id = context.application.bot_data["clone_id"]
    async with db.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """SELECT id,payload,created_by FROM bot_broadcasts
                   WHERE clone_id=$1 AND status='pending' AND scheduled_at<=NOW()
                   ORDER BY scheduled_at,id FOR UPDATE SKIP LOCKED LIMIT 1""", clone_id)
            if not row: return
            await conn.execute("UPDATE bot_broadcasts SET status='processing' WHERE id=$1", row["id"])
    payload = row["payload"] if isinstance(row["payload"], dict) else json.loads(row["payload"])
    try:
        await _deliver(context, int(row["id"]), payload, int(row["created_by"]))
    except Exception as exc:
        await db.execute(
            """UPDATE bot_broadcasts SET status='failed',error_detail=$1,finished_at=NOW()
               WHERE clone_id=$2 AND id=$3""", f"{type(exc).__name__}: {str(exc)[:250]}", clone_id, row["id"])
        log.exception("Scheduled broadcast failed: %s", row["id"])


async def broadcasts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id, context): return
    rows = await context.application.bot_data["db"].require().fetch(
        """SELECT id,status,scheduled_at,sent_count,failed_count FROM bot_broadcasts
           WHERE clone_id=$1 ORDER BY id DESC LIMIT 30""", context.application.bot_data["clone_id"])
    body = "**ʙʀᴏᴀᴅᴄᴀsᴛ ʜɪsᴛᴏʀʏ**\n\n" + (
        "\n".join(f"#{r['id']} · {r['status']} · {r['scheduled_at'] or 'immediate'} · sent {r['sent_count']} · failed {r['failed_count']}" for r in rows)
        if rows else "No broadcasts.")
    await _send(context, update.effective_chat.id, body)


async def cancelbroadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id, context): return
    if len(context.args) != 1 or not context.args[0].isdigit():
        await _send(context, update.effective_chat.id, "Usage: /cancelbroadcast BROADCAST_ID")
        return
    result = await context.application.bot_data["db"].require().execute(
        """UPDATE bot_broadcasts SET status='cancelled',finished_at=NOW()
           WHERE clone_id=$1 AND id=$2 AND status IN ('draft','pending')""",
        context.application.bot_data["clone_id"], int(context.args[0]))
    await _send(context, update.effective_chat.id,
        "Broadcast cancelled." if result.endswith("1") else "Pending broadcast not found or already processing.")


def add_broadcast_handlers(app):
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("broadcasts", broadcasts))
    app.add_handler(CommandHandler("cancelbroadcast", cancelbroadcast))
    app.add_handler(CallbackQueryHandler(broadcast_callback, pattern=r"^bcast:"))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, capture_broadcast), group=1)

"""Database export, Telegram-channel backup, and guarded restore commands."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from io import BytesIO
from telegram import Update, InputFile
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters
from .branding import send_branded, close_keyboard


TABLES = ["bot_message_templates","bot_message_buttons","bot_users","link_channels","link_invites","link_join_events","link_fsub_channels","link_settings","link_shortener_events","link_public_entries","link_scheduled_jobs","link_pending_join_requests","bot_broadcasts"]
SERIAL_TABLES = ["link_invites","link_join_events","link_shortener_events","link_scheduled_jobs","bot_broadcasts"]
PRODUCT = "link"
SETTING_TABLE = "link_settings"
BACKUP_SETTING = "backup_channel_id"


def _is_admin(update, context):
    user = update.effective_user
    return bool(user and (user.id == context.application.bot_data["owner_id"] or user.id in context.application.bot_data["admins"]))


def _is_owner(update, context):
    return bool(update.effective_user and update.effective_user.id == context.application.bot_data["owner_id"])


async def _send(context, chat_id, body):
    data = context.application.bot_data
    return await send_branded(context.bot, chat_id, body,
        image_url=data["image_url"], image_path=data.get("image_path"),
        small_caps=data.get("small_caps", True))


async def _get_backup_channel(context):
    row = await context.application.bot_data["db"].require().fetchrow(
        f"SELECT setting_value FROM {SETTING_TABLE} WHERE clone_id=$1 AND setting_key=$2",
        context.application.bot_data["clone_id"], BACKUP_SETTING)
    return int(row["setting_value"]) if row else None


async def _export_payload(context):
    db = context.application.bot_data["db"].require()
    clone_id = context.application.bot_data["clone_id"]
    tables = {}
    for table in TABLES:
        rows = await db.fetch(f"SELECT * FROM {table} WHERE clone_id=$1", clone_id)
        tables[table] = [dict(row) for row in rows]
    return {"schema_version": 1, "product": PRODUCT, "clone_id": clone_id,
            "created_at": datetime.now(timezone.utc).isoformat(), "tables": tables}


async def _restore_payload(context, payload):
    clone_id = context.application.bot_data["clone_id"]
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("Unsupported backup schema.")
    if payload.get("product") != PRODUCT or payload.get("clone_id") != clone_id:
        raise ValueError("Backup belongs to a different bot product or clone.")
    tables = payload.get("tables")
    if not isinstance(tables, dict) or not set(tables).issubset(set(TABLES)):
        raise ValueError("Backup contains unknown tables.")
    pool = context.application.bot_data["db"].require()
    async with pool.acquire() as conn:
        async with conn.transaction():
            for table, rows in tables.items():
                if not isinstance(rows, list):
                    raise ValueError(f"Invalid rows for {table}.")
                await conn.execute(f"DELETE FROM {table} WHERE clone_id=$1", clone_id)
                for row in rows:
                    if not isinstance(row, dict) or row.get("clone_id") != clone_id:
                        raise ValueError(f"Invalid clone ownership in {table}.")
                    columns = list(row)
                    if not columns or any(not column.replace("_", "").isalnum() for column in columns):
                        raise ValueError(f"Invalid columns in {table}.")
                    placeholders = ",".join(f"\u0024{index}" for index in range(1, len(columns) + 1))
                    column_sql = ",".join(f'"{column}"' for column in columns)
                    values = [row[column] for column in columns]
                    await conn.execute(
                        f'INSERT INTO "{table}" ({column_sql}) VALUES ({placeholders})', *values)
            for table in SERIAL_TABLES:
                if table in tables:
                    await conn.execute(
                        f"SELECT setval(pg_get_serial_sequence('{table}','id'), "
                        f"COALESCE((SELECT MAX(id) FROM {table}),1), "
                        f"EXISTS(SELECT 1 FROM {table}))")


async def setbackupchannel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_owner(update, context): return
    if len(context.args) != 1 or not context.args[0].lstrip("-").isdigit():
        await _send(context, update.effective_chat.id, "Usage: /setbackupchannel CHANNEL_ID")
        return
    channel_id = int(context.args[0])
    try:
        chat = await context.bot.get_chat(channel_id)
        me = await context.bot.get_me()
        member = await context.bot.get_chat_member(channel_id, me.id)
        if getattr(member, "status", "") not in {"administrator", "creator"}:
            raise PermissionError("The bot must be an administrator in the backup channel.")
        if getattr(member, "can_post_messages", True) is False:
            raise PermissionError("The bot needs permission to post documents.")
        await context.application.bot_data["db"].require().execute(
            f"""INSERT INTO {SETTING_TABLE}(clone_id,setting_key,setting_value)
                VALUES($1,$2,$3) ON CONFLICT(clone_id,setting_key)
                DO UPDATE SET setting_value=EXCLUDED.setting_value,updated_at=NOW()""",
            context.application.bot_data["clone_id"], BACKUP_SETTING, str(channel_id))
        body = f"Backup channel configured: {chat.title or channel_id} ({channel_id})."
    except Exception as exc:
        body = f"Backup channel configuration failed: {type(exc).__name__}: {str(exc)[:120]}"
    await _send(context, update.effective_chat.id, body)


async def _send_export(context, chat_id: int, *, register: bool, actor_id: int):
    payload = await _export_payload(context)
    content = json.dumps(payload, ensure_ascii=False, default=str, separators=(",", ":")).encode("utf-8")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"{PRODUCT}_backup_{stamp}.json"
    channel_id = await _get_backup_channel(context) if register else None
    destination = channel_id or chat_id
    await _send(context, destination, f"ᴅᴀᴛᴀʙᴀsᴇ ʙᴀᴄᴋᴜᴘ · {PRODUCT} · {len(payload['tables'])} tables.")
    document = await context.bot.send_document(
        chat_id=destination, document=InputFile(BytesIO(content), filename=filename),
        caption=f"Database backup · {PRODUCT} · {payload['created_at']}",
        reply_markup=close_keyboard())
    if register:
        await context.application.bot_data["db"].require().execute(
            """INSERT INTO bot_backups(clone_id,created_by,backup_channel_id,telegram_message_id,telegram_file_id,file_name)
               VALUES($1,$2,$3,$4,$5,$6)""",
            context.application.bot_data["clone_id"], actor_id, channel_id,
            document.message_id, document.document.file_id, filename)
    return filename, destination


async def backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update, context): return
    try:
        filename, destination = await _send_export(
            context, update.effective_chat.id, register=True, actor_id=update.effective_user.id)
        await _send(context, update.effective_chat.id, f"Backup completed: {filename}\\nStored in {destination}.")
    except Exception as exc:
        await _send(context, update.effective_chat.id, f"Backup failed: {type(exc).__name__}: {str(exc)[:180]}")


async def exportdata(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update, context): return
    try:
        filename, _ = await _send_export(
            context, update.effective_chat.id, register=False, actor_id=update.effective_user.id)
        await _send(context, update.effective_chat.id, f"Export completed: {filename}.")
    except Exception as exc:
        await _send(context, update.effective_chat.id, f"Export failed: {type(exc).__name__}: {str(exc)[:180]}")


async def backups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update, context): return
    rows = await context.application.bot_data["db"].require().fetch(
        """SELECT id,file_name,created_at,backup_channel_id FROM bot_backups
           WHERE clone_id=$1 ORDER BY id DESC LIMIT 30""",
        context.application.bot_data["clone_id"])
    body = "**ʙᴀᴄᴋᴜᴘ ʜɪsᴛᴏʀʏ**\\n\\n" + (
        "\\n".join(f"#{row['id']} · {row['file_name']} · {row['created_at']} · {row['backup_channel_id'] or 'private'}" for row in rows)
        if rows else "No registered backups.")
    await _send(context, update.effective_chat.id, body)


async def _import_bytes(context, raw):
    payload = json.loads(raw.decode("utf-8"))
    await _restore_payload(context, payload)


async def restore(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_owner(update, context): return
    if len(context.args) != 2 or not context.args[0].isdigit() or context.args[1].upper() != "CONFIRM":
        await _send(context, update.effective_chat.id, "Usage: /restore BACKUP_ID CONFIRM\\nThis replaces the matching clone's records with that backup.")
        return
    row = await context.application.bot_data["db"].require().fetchrow(
        "SELECT telegram_file_id FROM bot_backups WHERE clone_id=$1 AND id=$2",
        context.application.bot_data["clone_id"], int(context.args[0]))
    if not row:
        await _send(context, update.effective_chat.id, "Backup record not found.")
        return
    try:
        file = await context.bot.get_file(row["telegram_file_id"])
        raw = await file.download_as_bytearray()
        await _import_bytes(context, bytes(raw))
        await _send(context, update.effective_chat.id, "Restore completed. The bot's current records were replaced by the selected backup.")
    except Exception as exc:
        await _send(context, update.effective_chat.id, f"Restore failed: {type(exc).__name__}: {str(exc)[:180]}")


async def importdata(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_owner(update, context): return
    context.user_data["awaiting_backup_import"] = True
    await _send(context, update.effective_chat.id, "Send the JSON backup document. It must belong to this exact bot product and clone. Existing records will be replaced.")


async def import_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_owner(update, context) or not context.user_data.pop("awaiting_backup_import", False):
        return
    context.user_data["suppress_upload_once"] = True
    document = update.effective_message.document if update.effective_message else None
    if not document or not (document.file_name or "").lower().endswith(".json"):
        await _send(context, update.effective_chat.id, "Please upload a .json backup file.")
        return
    try:
        file = await context.bot.get_file(document.file_id)
        raw = await file.download_as_bytearray()
        await _import_bytes(context, bytes(raw))
        await _send(context, update.effective_chat.id, "Import completed successfully.")
    except Exception as exc:
        await _send(context, update.effective_chat.id, f"Import failed: {type(exc).__name__}: {str(exc)[:180]}")


def add_backup_handlers(app):
    app.add_handler(CommandHandler("setbackupchannel", setbackupchannel))
    app.add_handler(CommandHandler("backup", backup))
    app.add_handler(CommandHandler("backups", backups))
    app.add_handler(CommandHandler("restore", restore))
    app.add_handler(CommandHandler("exportdata", exportdata))
    app.add_handler(CommandHandler("importdata", importdata))
    app.add_handler(MessageHandler(filters.Document.ALL, import_document), group=1)

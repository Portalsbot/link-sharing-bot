import logging
from telegram import Update
from telegram.ext import ContextTypes
from .branding import send_branded

logger = logging.getLogger(__name__)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    # Do not log bot tokens, update payloads or arbitrary user-provided secrets.
    logger.error("Unhandled update error: %s", type(context.error).__name__ if context.error else "unknown")
    if isinstance(update, Update) and update.effective_chat:
        try:
            await send_branded(context.bot, update.effective_chat.id,
                "ᴡᴇ ᴄᴏᴜʟᴅ ɴᴏᴛ ᴄᴏᴍᴘʟᴇᴛᴇ ᴛʜᴀᴛ ᴀᴄᴛɪᴏɴ. ᴘʟᴇᴀsᴇ ᴛʀʏ ᴀɢᴀɪɴ.",
                image_url=context.application.bot_data["image_url"],
                image_path=context.application.bot_data["image_path"],
                small_caps=context.application.bot_data["small_caps"])
        except Exception:
            logger.exception("Unable to send branded error notice")

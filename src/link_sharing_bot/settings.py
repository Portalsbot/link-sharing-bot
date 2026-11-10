"""Shared settings and branded command registration."""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler
from .branding import send_branded, keyboard_from_buttons


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = "file.start" if context.application.bot_data["product"] == "file" else "link.start"
    user_row = await context.application.bot_data["db"].require().fetchrow(
        """INSERT INTO bot_users(clone_id,user_id) VALUES($1,$2)
           ON CONFLICT(clone_id,user_id) DO UPDATE SET last_seen=NOW()
           RETURNING is_banned""",
        context.application.bot_data["clone_id"], update.effective_user.id,
    )
    if user_row and user_row["is_banned"]:
        await send_branded(context.bot, update.effective_chat.id, "ᴛʜɪs ʙᴏᴛ ᴀᴄᴄᴇss ɪs ᴅɪsᴀʙʟᴇᴅ ғᴏʀ ʏᴏᴜ. ᴄᴏɴᴛᴀᴄᴛ ᴛʜᴇ ᴀᴅᴍɪɴ.",
            image_url=context.application.bot_data["image_url"],
            image_path=context.application.bot_data["image_path"],
            small_caps=context.application.bot_data["small_caps"])
        return

    # A public bot deep link is permanent. Only the fresh channel invite
    # generated after this /start receives the configured Telegram expiry.
    if context.application.bot_data["product"] == "link" and context.args:
        from .handlers.links import open_public_entry
        if await open_public_entry(update, context, context.args[0]):
            return

    body = await context.application.bot_data["db"].get_text(
        context.application.bot_data["clone_id"], key,
        context.application.bot_data["defaults"].get(key, "ᴡᴇʟᴄᴏᴍᴇ!"),
    )
    rows = await context.application.bot_data["db"].get_buttons(context.application.bot_data["clone_id"], key)
    markup = keyboard_from_buttons(rows, small_caps=context.application.bot_data["small_caps"])
    await send_branded(context.bot, update.effective_chat.id, body,
                       image_url=context.application.bot_data["image_url"],
                       image_path=context.application.bot_data["image_path"],
                       small_caps=context.application.bot_data["small_caps"], reply_markup=markup)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = "file.help" if context.application.bot_data["product"] == "file" else "link.help"
    body = await context.application.bot_data["db"].get_text(
        context.application.bot_data["clone_id"], key,
        context.application.bot_data["defaults"].get(key, "Use /start to begin and /texts to customise messages."),
    )
    rows = await context.application.bot_data["db"].get_buttons(context.application.bot_data["clone_id"], key)
    markup = keyboard_from_buttons(rows, small_caps=context.application.bot_data["small_caps"])
    await send_branded(context.bot, update.effective_chat.id, body,
                       image_url=context.application.bot_data["image_url"],
                       image_path=context.application.bot_data["image_path"],
                       small_caps=context.application.bot_data["small_caps"], reply_markup=markup)


async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = "file.about" if context.application.bot_data["product"] == "file" else "link.about"
    body = await context.application.bot_data["db"].get_text(
        context.application.bot_data["clone_id"], key,
        context.application.bot_data["defaults"].get(key, "Official bot information."),
    )
    rows = await context.application.bot_data["db"].get_buttons(context.application.bot_data["clone_id"], key)
    markup = keyboard_from_buttons(rows, small_caps=context.application.bot_data["small_caps"])
    await send_branded(context.bot, update.effective_chat.id, body,
                       image_url=context.application.bot_data["image_url"],
                       image_path=context.application.bot_data["image_path"],
                       small_caps=context.application.bot_data["small_caps"], reply_markup=markup)


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_branded(context.bot, update.effective_chat.id, "ᴘᴏɴɢ · ʙᴏᴛ ɪs ʀᴇsᴘᴏɴᴅɪɴɢ.",
                       image_url=context.application.bot_data["image_url"],
                       image_path=context.application.bot_data["image_path"],
                       small_caps=context.application.bot_data["small_caps"])


async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    body = ("**sᴇᴛᴛɪɴɢs**\\n\\n"
            "/texts — edit messages\\n/buttons TEMPLATE_KEY — manage inline buttons\\n"
            "/dlt_time SECONDS — set delivery auto-delete (File Sharing)\\n"
            "/help — command guide")
    await send_branded(context.bot, update.effective_chat.id, body,
                       image_url=context.application.bot_data["image_url"],
                       image_path=context.application.bot_data["image_path"],
                       small_caps=context.application.bot_data["small_caps"])


def add_common_handlers(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("about", about))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("settings", settings))

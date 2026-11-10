"""Shared settings screens with functional About, Help, Channel and Back navigation."""
from telegram import Update, BotCommand, BotCommandScopeChat, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from .branding import send_branded, keyboard_from_buttons


def _default_markup(context, screen):
    channel_url = context.application.bot_data.get("channel_url") or ""
    channel = [InlineKeyboardButton("· ᴄʜᴀɴɴᴇʟ ·", url=channel_url)] if channel_url.startswith(("https://", "http://")) else []
    if screen == "start":
        rows = [
            [InlineKeyboardButton("· ᴀʙᴏᴜᴛ ·", callback_data="nav:about")],
            [InlineKeyboardButton("· ʜᴇʟᴘ ·", callback_data="nav:help")],
        ]
        if channel:
            rows[0].append(channel[0])
        return InlineKeyboardMarkup(rows)
    rows = []
    if channel:
        rows.append(channel)
    rows.append([InlineKeyboardButton("· ʙᴀᴄᴋ ·", callback_data="nav:start")])
    return InlineKeyboardMarkup(rows)


async def _show_screen(update: Update, context: ContextTypes.DEFAULT_TYPE, screen: str):
    product = context.application.bot_data["product"]
    key = f"{product}.{screen}"
    defaults = context.application.bot_data["defaults"]
    body = await context.application.bot_data["db"].get_text(
        context.application.bot_data["clone_id"], key, defaults.get(key, "ᴡᴇʟᴄᴏᴍᴇ!")
    )
    saved = await context.application.bot_data["db"].get_buttons(
        context.application.bot_data["clone_id"], key
    )
    markup = keyboard_from_buttons(saved, small_caps=context.application.bot_data["small_caps"]) if saved else None
    if markup is None:
        markup = _default_markup(context, screen)
    elif screen in {"about", "help"}:
        rows = list(markup.inline_keyboard)
        rows.append([InlineKeyboardButton("· ʙᴀᴄᴋ ·", callback_data="nav:start")])
        markup = InlineKeyboardMarkup(rows)
    await send_branded(
        context.bot, update.effective_chat.id, body,
        image_url=context.application.bot_data["image_url"],
        image_path=context.application.bot_data["image_path"],
        small_caps=context.application.bot_data["small_caps"],
        reply_markup=markup,
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    product = context.application.bot_data["product"]
    user_row = await context.application.bot_data["db"].require().fetchrow(
        """INSERT INTO bot_users(clone_id,user_id) VALUES($1,$2)
           ON CONFLICT(clone_id,user_id) DO UPDATE SET last_seen=NOW()
           RETURNING is_banned""",
        context.application.bot_data["clone_id"], update.effective_user.id,
    )
    if user_row and user_row["is_banned"]:
        await send_branded(
            context.bot, update.effective_chat.id, "ᴀᴄᴄᴇss ᴛᴏ ᴛʜɪs ʙᴏᴛ ɪs ᴅɪsᴀʙʟᴇᴅ. ᴄᴏɴᴛᴀᴄᴛ ᴛʜᴇ ᴀᴅᴍɪɴ.",
            image_url=context.application.bot_data["image_url"],
            image_path=context.application.bot_data["image_path"],
            small_caps=context.application.bot_data["small_caps"],
        )
        return
    if product == "link" and context.args:
        from .handlers.links import open_public_entry
        if await open_public_entry(update, context, context.args[0]):
            return
    await _show_screen(update, context, "start")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _show_screen(update, context, "help")


async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _show_screen(update, context, "about")


async def navigation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    screen = query.data.split(":", 1)[1]
    if screen not in {"start", "about", "help"}:
        return
    await _show_screen(update, context, screen)


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_branded(
        context.bot, update.effective_chat.id, "ᴘᴏɴɢ · ʙᴏᴛ ɪs ʀᴇsᴘᴏɴᴅɪɴɢ.",
        image_url=context.application.bot_data["image_url"],
        image_path=context.application.bot_data["image_path"],
        small_caps=context.application.bot_data["small_caps"],
    )


async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    body = ("**sᴇᴛᴛɪɴɢs**\n\n"
            "/texts — edit messages\n/buttons TEMPLATE_KEY — manage inline buttons\n"
            "/dlt_time SECONDS — set delivery auto-delete (File Sharing)\n"
            "/help — command guide")
    await send_branded(
        context.bot, update.effective_chat.id, body,
        image_url=context.application.bot_data["image_url"],
        image_path=context.application.bot_data["image_path"],
        small_caps=context.application.bot_data["small_caps"],
    )


def add_common_handlers(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("about", about))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("settings", settings))
    app.add_handler(CallbackQueryHandler(navigation_callback, pattern=r"^nav:(start|about|help)$"))


async def configure_command_menu(app):
    public_commands = [
        BotCommand("start", "Open the welcome screen"),
        BotCommand("about", "About this bot"),
        BotCommand("help", "How to use this bot"),
        BotCommand("ping", "Check bot response"),
    ]
    admin_commands = [
        BotCommand("addch", "Register a target channel"),
        BotCommand("newlink", "Create a permanent external bot link"),
        BotCommand("publiclinks", "List public bot links"),
        BotCommand("deletelink", "Disable a public bot link"),
        BotCommand("setttl", "Set expiry for future channel invites"),
        BotCommand("delch", "Remove a registered channel"),
        BotCommand("channels", "List registered channels"),
        BotCommand("genlink", "Create a temporary invite"),
        BotCommand("bulklink", "Create invites for multiple channels"),
        BotCommand("links", "View generated invitations"),
        BotCommand("revoke_links", "Revoke channel invitations"),
        BotCommand("bulkexpire", "Set future invite expiry"),
        BotCommand("setapproval", "Configure join-request approval"),
        BotCommand("reqmode", "Toggle automatic request approval"),
        BotCommand("reqtime", "Set request approval delay"),
        BotCommand("add_fsub", "Add a force-subscription channel"),
        BotCommand("del_fsub", "Remove a force-subscription channel"),
        BotCommand("fsub", "List force-subscription channels"),
        BotCommand("shorten", "Shorten a URL"),
        BotCommand("set_api", "Configure shortener API"),
        BotCommand("shortnerstatus", "Check shortener configuration"),
        BotCommand("shortnerstats", "View shortener usage"),
        BotCommand("linkhistory", "View shortener history"),
        BotCommand("channelstats", "View channel statistics"),
        BotCommand("schedulelink", "Schedule a channel invitation"),
        BotCommand("scheduledlinks", "List scheduled invitations"),
        BotCommand("cancelschedule", "Cancel a scheduled invitation"),
        BotCommand("joinrequests", "View pending join requests"),
        BotCommand("approve", "Approve a join request"),
        BotCommand("decline", "Decline a join request"),
        BotCommand("apiusage", "View shortener API usage"),
        BotCommand("requeststats", "View join-request analytics"),
        BotCommand("requesthistory", "View join-request history"),
        BotCommand("linkstats", "View link dashboard"),
        BotCommand("users", "View registered users"),
        BotCommand("userinfo", "View user details"),
        BotCommand("blockuser", "Block a user"),
        BotCommand("unblockuser", "Unblock a user"),
        BotCommand("stats", "View bot statistics"),
        BotCommand("logs", "View activity logs"),
        BotCommand("security", "View security configuration"),
        BotCommand("database", "Check database connection"),
        BotCommand("diagnostics", "Run bot diagnostics"),
        BotCommand("broadcast", "Create a broadcast"),
        BotCommand("broadcasts", "View broadcasts"),
        BotCommand("cancelbroadcast", "Cancel a pending broadcast"),
        BotCommand("setbackupchannel", "Set backup channel"),
        BotCommand("backup", "Create a database backup"),
        BotCommand("backups", "List backups"),
        BotCommand("restore", "Restore a backup"),
        BotCommand("exportdata", "Export bot data"),
        BotCommand("importdata", "Import a backup file"),
        BotCommand("texts", "Edit bot messages"),
        BotCommand("settings", "Open bot settings")
    ]
    await app.bot.set_my_commands(public_commands)
    scope_ids = {app.bot_data["owner_id"], *app.bot_data.get("admins", set())}
    for user_id in scope_ids:
        await app.bot.set_my_commands(public_commands + admin_commands,
            scope=BotCommandScopeChat(chat_id=user_id))

"""Branded Telegram photo responses with persistent inline controls and a fixed close action."""
from __future__ import annotations

from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError

from .formatting import caption_chunks, SMALL_CAPS as SMALL_CAPS_MAP
from .branding_config import FOOTER_MESSAGE, IMAGE_PATH


CLOSE_BUTTON_TEXT = "ᴄʟᴏsᴇ"
CLOSE_CALLBACK_DATA = "branding:close"


def _small_caps_markup(markup):
    if not markup:
        return None
    rows = []
    for row in markup.inline_keyboard:
        converted = []
        for button in row:
            data = button.to_dict()
            data["text"] = str(data.get("text", "")).translate(SMALL_CAPS_MAP)
            converted.append(InlineKeyboardButton(**data))
        if converted:
            rows.append(converted)
    return rows


async def send_branded(
    bot,
    chat_id: int,
    text: str,
    *,
    image_url: str,
    image_path: str | None = None,
    small_caps: bool = True,
    reply_markup=None,
    reply_to_message_id=None,
    disable_notification: bool = False,
):
    body = str(text or "")
    if FOOTER_MESSAGE:
        body = f"{body}\\n\\n{FOOTER_MESSAGE}" if body else FOOTER_MESSAGE

    requested_path = Path(image_path) if image_path else IMAGE_PATH
    local_photo = requested_path if requested_path.is_file() else None
    chunks = caption_chunks(body, small_caps=small_caps, limit=700)
    command_rows = _small_caps_markup(reply_markup) if small_caps else (
        list(reply_markup.inline_keyboard) if reply_markup else []
    )

    sent = []
    for index, caption in enumerate(chunks):
        rows = command_rows if index == len(chunks) - 1 else []
        rows = list(rows or [])
        close_label = CLOSE_BUTTON_TEXT.translate(SMALL_CAPS_MAP) if small_caps else CLOSE_BUTTON_TEXT
        rows.append([InlineKeyboardButton(close_label, callback_data=CLOSE_CALLBACK_DATA)])
        markup = InlineKeyboardMarkup(rows)

        kwargs = {
            "chat_id": chat_id,
            "caption": caption,
            "parse_mode": "HTML",
            "reply_markup": markup,
            "disable_notification": disable_notification,
        }
        if reply_to_message_id and index == 0:
            kwargs["reply_to_message_id"] = reply_to_message_id

        if local_photo:
            with local_photo.open("rb") as photo_file:
                message = await bot.send_photo(photo=photo_file, **kwargs)
        else:
            message = await bot.send_photo(photo=image_url, **kwargs)
        sent.append(message)

    return sent[-1] if sent else None


async def close_branded_message(update, context):
    query = update.callback_query
    if query is None:
        return
    message = query.message
    try:
        if message is None:
            raise TelegramError("Callback message is unavailable")
        await message.delete()
        await query.answer("ᴄʟᴏsᴇᴅ.")
    except TelegramError:
        await query.answer("ᴄᴏᴜʟᴅ ɴᴏᴛ ᴄʟᴏsᴇ ᴛʜɪs ᴍᴇssᴀɢᴇ.", show_alert=True)


def keyboard_from_buttons(rows: list, small_caps: bool = True) -> InlineKeyboardMarkup | None:
    if not rows:
        return None
    keyboard = []
    for row in rows:
        buttons = []
        for item in row:
            label = str(item.get("text", "Button"))[:64]
            if small_caps:
                label = label.translate(SMALL_CAPS_MAP)
            url = item.get("url")
            callback = item.get("callback_data")
            if url:
                buttons.append(InlineKeyboardButton(label, url=str(url)))
            elif callback:
                buttons.append(InlineKeyboardButton(label, callback_data=str(callback)[:64]))
        if buttons:
            keyboard.append(buttons)
    return InlineKeyboardMarkup(keyboard) if keyboard else None

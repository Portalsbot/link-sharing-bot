"""All bot-authored text replies are sent as branded photo captions."""
from __future__ import annotations
from pathlib import Path
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from .formatting import caption_chunks, SMALL_CAPS

async def send_branded(bot, chat_id: int, text: str, *, image_url: str, image_path: str | None = None,
                       small_caps: bool = True, reply_markup=None, reply_to_message_id=None,
                       disable_notification: bool = False):
    """Send text as one or more branded photo captions (Telegram caption max 1024 chars).

    File/video/audio deliveries are media payloads and remain separate Telegram media messages;
    Telegram does not allow attaching an independent branding photo to those same messages.
    """
    photo = str(Path(image_path)) if image_path and Path(image_path).is_file() else image_url
    chunks = caption_chunks(text, small_caps=small_caps, limit=850)
    sent = []
    for index, caption in enumerate(chunks):
        markup = reply_markup if index == len(chunks) - 1 else None
        kwargs = {"chat_id": chat_id, "photo": photo, "caption": caption, "parse_mode": "HTML",
                  "reply_markup": markup, "disable_notification": disable_notification}
        if reply_to_message_id and index == 0:
            kwargs["reply_to_message_id"] = reply_to_message_id
        sent.append(await bot.send_photo(**kwargs))
    return sent[-1] if sent else None


def keyboard_from_buttons(rows: list, small_caps: bool = True) -> InlineKeyboardMarkup | None:
    if not rows:
        return None
    keyboard = []
    for row in rows:
        buttons = []
        for item in row:
            label = str(item.get("text", "Button"))[:64]
            if small_caps:
                label = label.translate(SMALL_CAPS)
            url = item.get("url")
            callback = item.get("callback_data")
            if url:
                buttons.append(InlineKeyboardButton(label, url=str(url)))
            elif callback:
                buttons.append(InlineKeyboardButton(label, callback_data=str(callback)[:64]))
        if buttons:
            keyboard.append(buttons)
    return InlineKeyboardMarkup(keyboard) if keyboard else None

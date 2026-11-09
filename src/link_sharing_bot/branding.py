"""Branded text sender. All text replies share the editable image and footer."""
from __future__ import annotations
from pathlib import Path
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from .formatting import caption_chunks, SMALL_CAPS as SMALL_CAPS_MAP
from .branding_config import FOOTER_MESSAGE

async def send_branded(bot, chat_id: int, text: str, *, image_url: str, image_path: str | None = None,
                       small_caps: bool = True, reply_markup=None, reply_to_message_id=None,
                       disable_notification: bool = False):
    """Send text as photo captions; fall back to plain text if the image URL is unavailable.

    Telegram file/video/audio payloads are separate media messages and cannot carry a second
    independent branding photo in the same message.
    """
    body = str(text or "")
    if FOOTER_MESSAGE:
        body = f"{body}\n\n{FOOTER_MESSAGE}" if body else FOOTER_MESSAGE
    photo = str(Path(image_path)) if image_path and Path(image_path).is_file() else image_url
    chunks = caption_chunks(body, small_caps=small_caps, limit=850)
    sent = []
    for index, caption in enumerate(chunks):
        markup = reply_markup if index == len(chunks) - 1 else None
        kwargs = {"chat_id": chat_id, "photo": photo, "caption": caption, "parse_mode": "HTML",
                  "reply_markup": markup, "disable_notification": disable_notification}
        if reply_to_message_id and index == 0:
            kwargs["reply_to_message_id"] = reply_to_message_id
        try:
            message = await bot.send_photo(**kwargs)
        except Exception:
            # A bad/unreachable placeholder image must never prevent the bot from replying.
            text_kwargs = {"chat_id": chat_id, "text": caption, "parse_mode": "HTML",
                           "reply_markup": markup, "disable_notification": disable_notification}
            if reply_to_message_id and index == 0:
                text_kwargs["reply_to_message_id"] = reply_to_message_id
            message = await bot.send_message(**text_kwargs)
        sent.append(message)
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

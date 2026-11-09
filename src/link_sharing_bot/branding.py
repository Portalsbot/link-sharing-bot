"""Branded sender: each text response is a local photo + its own text + inline button."""
from __future__ import annotations
from pathlib import Path
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from .formatting import caption_chunks, SMALL_CAPS as SMALL_CAPS_MAP
from .branding_config import FOOTER_MESSAGE, DUMMY_BUTTON_TEXT, DUMMY_BUTTON_URL, IMAGE_PATH

async def send_branded(bot, chat_id: int, text: str, *, image_url: str, image_path: str | None = None,
                       small_caps: bool = True, reply_markup=None, reply_to_message_id=None,
                       disable_notification: bool = False):
    body = str(text or "")
    if FOOTER_MESSAGE:
        body = f"{body}\n\n{FOOTER_MESSAGE}" if body else FOOTER_MESSAGE
    requested_path = Path(image_path) if image_path else IMAGE_PATH
    local_photo = requested_path if requested_path.is_file() else None
    chunks = caption_chunks(body, small_caps=small_caps, limit=700)
    rows = list(reply_markup.inline_keyboard) if reply_markup else []
    rows.append([InlineKeyboardButton(DUMMY_BUTTON_TEXT.translate(SMALL_CAPS_MAP) if small_caps else DUMMY_BUTTON_TEXT,
                                      url=DUMMY_BUTTON_URL)])
    markup = InlineKeyboardMarkup(rows)
    sent = []
    for index, caption in enumerate(chunks):
        current_markup = markup if index == len(chunks) - 1 else None
        kwargs = {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML",
                  "reply_markup": current_markup, "disable_notification": disable_notification}
        if reply_to_message_id and index == 0:
            kwargs["reply_to_message_id"] = reply_to_message_id
        if local_photo:
            with local_photo.open("rb") as photo_file:
                message = await bot.send_photo(photo=photo_file, **kwargs)
        else:
            message = await bot.send_photo(photo=image_url, **kwargs)
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

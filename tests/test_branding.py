import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from link_sharing_bot. import branding


def test_branded_sender_always_adds_dummy_and_close_buttons(monkeypatch, tmp_path):
    photo = tmp_path / "branding.jpg"
    photo.write_bytes(b"fake-image")
    monkeypatch.setattr(branding, "IMAGE_PATH", photo)
    bot = SimpleNamespace(send_photo=AsyncMock(return_value=SimpleNamespace(message_id=1)))
    custom = InlineKeyboardMarkup([[InlineKeyboardButton("ABOUT", callback_data="page:about")]])

    asyncio.run(
        branding.send_branded(
            bot,
            123,
            "Hello",
            image_url="https://example.com/image.jpg",
            reply_markup=custom,
            small_caps=True,
        )
    )

    markup = bot.send_photo.await_args.kwargs["reply_markup"]
    buttons = [button for row in markup.inline_keyboard for button in row]
    assert any(button.url == branding.DUMMY_BUTTON_URL for button in buttons)
    close = [button for button in buttons if button.callback_data == branding.CLOSE_CALLBACK_DATA]
    assert len(close) == 1
    assert close[0].text == "ᴄʟᴏsᴇ"
    assert any(button.callback_data == "page:about" for button in buttons)

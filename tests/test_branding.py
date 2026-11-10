import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from link_sharing_bot import branding

def test_branded_sender_adds_close_without_dummy_button(tmp_path):
    photo = tmp_path / "branding.jpg"
    photo.write_bytes(b"fake-image")
    bot = SimpleNamespace(send_photo=AsyncMock(return_value=SimpleNamespace(message_id=1)))
    custom = InlineKeyboardMarkup([[InlineKeyboardButton("ABOUT", callback_data="page:about")]])
    asyncio.run(branding.send_branded(
        bot, 123, "Hello", image_url="https://example.com/image.jpg",
        reply_markup=custom, small_caps=True, image_path=str(photo),
    ))
    markup = bot.send_photo.await_args.kwargs["reply_markup"]
    buttons = [button for row in markup.inline_keyboard for button in row]
    close = [button for button in buttons if button.callback_data == branding.CLOSE_CALLBACK_DATA]
    assert len(close) == 1
    assert close[0].text == branding.CLOSE_BUTTON_TEXT
    assert any(button.callback_data == "page:about" for button in buttons)
    assert not any(button.url == "https://t.me/" for button in buttons)

def test_default_uses_configured_remote_branding_url():
    image_url = "https://i.ibb.co/PGpMYwYY/Gemini-Generated-Image-a7tjlia7tjlia7tj.png"
    bot = SimpleNamespace(send_photo=AsyncMock(return_value=SimpleNamespace(message_id=2)))
    asyncio.run(branding.send_branded(bot, 123, "Hello", image_url=image_url))
    assert bot.send_photo.await_args.kwargs["photo"] == image_url

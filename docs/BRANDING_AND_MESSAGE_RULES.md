# Branding and Message Rules

- Default image: `https://raw.githubusercontent.com/Portalsbot/image/main/photo_2026-11-01_20-42-48.jpg`
- Original image page: `https://github.com/Portalsbot/image/blob/main/photo_2026-11-01_20-42-48.jpg`
- All bot-authored text messages must use `send_branded(...)` in `branding.py`.
- `send_branded` sends an image with a caption, HTML formatting, and optional inline keyboard.
- Caption text is chunked because Telegram photo captions allow a maximum of 1024 characters after entity parsing.
- Do not send raw text replies from handlers; use the branded sender.
- Actual media delivery (documents/audio/video) is a separate Telegram media message. Telegram does not permit a separate photo to be attached to that same media message.
- The custom formatting parser supports B, I, U, S, CODE, PRE, Q, SPOILER and HTTP(S) LINK blocks.
- Small-caps conversion is applied to ordinary readable text, not URLs/attributes or code blocks.

If Telegram rejects the remote image URL, set `BRANDING_IMAGE_PATH` to a local JPEG mounted into the container, or use a bot-specific Telegram `file_id` implementation. A GitHub blob webpage is not a direct photo URL.

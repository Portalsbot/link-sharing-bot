# Branding and Message Rules

- Default image: `https://i.ibb.co/PGpMYwYY/Gemini-Generated-Image-a7tjlia7tjlia7tj.png`
- Original image page: `https://github.com/Portalsbot/image/blob/main/photo_2026-11-01_20-42-48.jpg`
- All bot-authored text messages must use `send_branded(...)` in `branding.py`.
- `send_branded` sends an image with a caption, HTML formatting, and optional inline keyboard.
- Caption text is chunked because Telegram photo captions allow a maximum of 1024 characters after entity parsing.
- Do not send raw text replies from handlers; use the branded sender.
- Actual media delivery (documents/audio/video) is a separate Telegram media message. Telegram does not permit a separate photo to be attached to that same media message.
- The custom formatting parser supports B, I, U, S, CODE, PRE, Q, SPOILER and HTTP(S) LINK blocks.
- Small-caps conversion is applied to ordinary readable text, not URLs/attributes or code blocks.

The i.ibb.co URL above is the repository default. An explicitly configured `BRANDING_IMAGE_PATH` may override it with an intentional local image. A deployment-level `BRANDING_IMAGE_URL` value overrides the repository default.

"""Shared, editable branding defaults loaded from config/messages.json."""
from __future__ import annotations
import json
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MESSAGES_FILE = _REPO_ROOT / "config" / "messages.json"
_DEFAULTS = {
    "image_url": "https://placehold.co/1280x720.jpg",
    "message": "ᴛʜɪs ɪs ᴀ ᴅᴜᴍᴍʏ ᴍᴇssᴀɢᴇ. ᴇᴅɪᴛ config/messages.json ᴛᴏ ᴄʜᴀɴɢᴇ ᴛʜɪs ᴛᴇxᴛ.",
    "small_caps": True,
}
if _MESSAGES_FILE.is_file():
    try:
        _loaded = json.loads(_MESSAGES_FILE.read_text(encoding="utf-8"))
        if not isinstance(_loaded, dict):
            raise ValueError("config/messages.json must contain a JSON object")
        _DEFAULTS.update({k: v for k, v in _loaded.items() if k in _DEFAULTS})
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError(f"Invalid branding config at {_MESSAGES_FILE}: {exc}") from exc

IMAGE_URL = str(_DEFAULTS["image_url"]).strip()
FOOTER_MESSAGE = str(_DEFAULTS["message"])
SMALL_CAPS = bool(_DEFAULTS["small_caps"])
if not IMAGE_URL.startswith(("https://", "http://")):
    raise RuntimeError("config/messages.json image_url must be an HTTP(S) URL")

"""Command-wise editable response and remote branding image defaults."""
from __future__ import annotations
import json
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RESPONSE_FILE = _REPO_ROOT / "config" / "command_responses.json"
IMAGE_PATH = _REPO_ROOT / "assets" / "branding.jpg"

if not _RESPONSE_FILE.is_file():
    raise RuntimeError(f"Required command response config missing: {_RESPONSE_FILE}")
try:
    _CONFIG = json.loads(_RESPONSE_FILE.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError) as exc:
    raise RuntimeError(f"Invalid command response config: {exc}") from exc
if not isinstance(_CONFIG, dict) or not isinstance(_CONFIG.get("commands"), dict):
    raise RuntimeError("command_responses.json must contain a commands object")
_BRANDING = _CONFIG.get("branding", {})
if not isinstance(_BRANDING, dict):
    raise RuntimeError("branding must be a JSON object")
IMAGE_URL = str(_BRANDING.get("image_url", "")).strip()
FOOTER_MESSAGE = str(_BRANDING.get("footer_text", ""))
SMALL_CAPS = bool(_BRANDING.get("small_caps", True))
COMMAND_RESPONSES = _CONFIG["commands"]
if not IMAGE_URL.startswith(("https://", "http://")):
    raise RuntimeError("branding.image_url must be a direct HTTP(S) image URL.")

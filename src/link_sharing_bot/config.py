"""Environment and mounted-secret configuration."""
from __future__ import annotations
import json
import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv
from .branding_config import IMAGE_URL as BRANDING_IMAGE_DEFAULT, SMALL_CAPS as BRANDING_SMALL_CAPS

load_dotenv()

BRANDING_IMAGE_SOURCE = BRANDING_IMAGE_DEFAULT

def _load_config_file() -> dict:
    path = os.getenv("CONFIG_FILE")
    if not path:
        return {}
    p = Path(path)
    if not p.is_file():
        raise RuntimeError(f"CONFIG_FILE does not exist: {path}")
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("CONFIG_FILE must contain a JSON object.")
    return data

_FILE_CONFIG = _load_config_file()

def value(name: str, default=None):
    return os.getenv(name, _FILE_CONFIG.get(name, default))

@dataclass(frozen=True)
class Settings:
    bot_token: str
    database_url: str
    owner_id: int
    clone_id: str
    branding_image_url: str
    branding_image_path: str | None
    small_caps: bool
    storage_channel_id: int | None = None
    storage_api_url: str | None = None
    storage_api_key: str | None = None
    default_auto_delete: int = 0
    max_files_per_user: int = 50

    @classmethod
    def from_env(cls) -> "Settings":
        token = value("BOT_TOKEN")
        dsn = value("DATABASE_URL")
        owner = value("OWNER_ID", "0")
        if not token:
            raise RuntimeError("BOT_TOKEN is required (or provide CONFIG_FILE).")
        if not dsn:
            raise RuntimeError("DATABASE_URL is required.")
        try:
            owner_id = int(owner)
        except (TypeError, ValueError) as exc:
            raise RuntimeError("OWNER_ID must be a numeric Telegram user ID.") from exc
        storage_channel = value("STORAGE_CHANNEL_ID")
        return cls(
            bot_token=str(token),
            database_url=str(dsn),
            owner_id=owner_id,
            clone_id=str(value("CLONE_ID", "official")),
            branding_image_url=str(value("BRANDING_IMAGE_URL", BRANDING_IMAGE_DEFAULT)),
            branding_image_path=value("BRANDING_IMAGE_PATH"),
            small_caps=str(value("SMALL_CAPS", str(BRANDING_SMALL_CAPS))).lower() in {"1", "true", "yes", "on"},
            storage_channel_id=int(storage_channel) if storage_channel else None,
            storage_api_url=value("STORAGE_API_URL"),
            storage_api_key=value("STORAGE_API_KEY"),
            default_auto_delete=int(value("DEFAULT_AUTO_DELETE", "0")),
            max_files_per_user=int(value("MAX_FILES_PER_USER", "50")),
        )

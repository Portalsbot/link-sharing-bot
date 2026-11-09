from __future__ import annotations
import asyncio
import logging
from telegram.ext import Application
from .config import Settings
from .database import Database
from .branding import send_branded
from .errors import error_handler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

async def connect_database(app: Application, settings: Settings, schema: str):
    db = Database(settings.database_url)
    await db.connect()
    await db.init_schema(schema)
    app.bot_data["db"] = db
    return db

async def shutdown_database(app: Application):
    db = app.bot_data.get("db")
    if db:
        await db.close()

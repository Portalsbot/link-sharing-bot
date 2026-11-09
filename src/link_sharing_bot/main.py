from __future__ import annotations
import os
from pathlib import Path
from telegram.ext import ApplicationBuilder
from .config import Settings
from .database import Database
from .defaults import DEFAULT_MESSAGES
from .settings import add_common_handlers
from .message_editor.handlers import add_editor_handlers
from .handlers.links import add_link_handlers
from .errors import error_handler

async def post_init(app):
    s=app.bot_data["settings"]
    db=Database(s.database_url); await db.connect()
    await db.init_schema(Path("migrations/001_initial.sql").read_text(encoding="utf-8"))
    app.bot_data["db"]=db

async def post_shutdown(app):
    db=app.bot_data.get("db")
    if db: await db.close()

def main():
    settings=Settings.from_env()
    admins={int(x) for x in os.getenv("ADMINS","").replace(","," ").split() if x.isdigit()}
    app=(ApplicationBuilder().token(settings.bot_token).post_init(post_init).post_shutdown(post_shutdown).build())
    app.bot_data.update({"settings":settings,"owner_id":settings.owner_id,"admins":admins,"clone_id":settings.clone_id,
        "image_url":settings.branding_image_url,"image_path":settings.branding_image_path,"small_caps":settings.small_caps,
        "defaults":DEFAULT_MESSAGES,"product":"link"})
    add_common_handlers(app); add_editor_handlers(app); add_link_handlers(app); app.add_error_handler(error_handler)
    app.run_polling(allowed_updates=["message","callback_query","chat_join_request"])

if __name__=="__main__": main()

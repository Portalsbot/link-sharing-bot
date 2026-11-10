from __future__ import annotations
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, MessageHandler, filters
from .config import Settings
from .database import Database
from .defaults import DEFAULT_MESSAGES
from .settings import add_common_handlers, configure_command_menu
from .message_editor.handlers import add_editor_handlers
from .handlers.links import add_link_handlers
from .errors import error_handler
from .branding import close_branded_message
from .backup import add_backup_handlers
from .broadcast import add_broadcast_handlers
from .fsubs import add_fsubs_handlers, message_fsubs_gate, callback_fsubs_gate

async def post_init(app):
    s=app.bot_data["settings"]
    db=Database(s.database_url); await db.connect()
    migrations_dir = Path(__file__).resolve().parents[2] / "migrations"
    migration_files = sorted(migrations_dir.glob("*.sql"))
    if not migration_files:
        raise RuntimeError(f"No database migrations found in {migrations_dir}")
    for migration_file in migration_files:
        await db.init_schema(migration_file.read_text(encoding="utf-8"))
    app.bot_data["db"]=db
    await configure_command_menu(app)
    # Never replay a job whose external Telegram action may already have happened before a crash.
    await db.require().execute(
        """UPDATE link_scheduled_jobs SET status='failed',
           error_detail=COALESCE(error_detail,'Worker restarted while job was processing; outcome requires review.'),
           finished_at=NOW() WHERE clone_id=$1 AND status='processing'""",
        s.clone_id)
    await db.require().execute(
        """UPDATE bot_broadcasts SET status='failed',
           error_detail=COALESCE(error_detail,'Worker restarted during delivery; recipient outcome is unknown.'),
           finished_at=NOW() WHERE clone_id=$1 AND status='processing'""",
        s.clone_id)
    if app.job_queue is None:
        raise RuntimeError("PTB JobQueue is required for durable scheduled links and broadcasts.")
    from .handlers.links import scheduled_link_worker
    app.job_queue.run_repeating(scheduled_link_worker, interval=5, first=2, name="durable-scheduled-links")
    from .broadcast import broadcast_worker
    app.job_queue.run_repeating(broadcast_worker, interval=10, first=4, name="scheduled-broadcasts")

async def post_shutdown(app):
    db=app.bot_data.get("db")
    if db: await db.close()


def _start_health_server():
    raw_port = os.getenv("PORT", "").strip()
    if not raw_port:
        return None
    try:
        port = int(raw_port)
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError as exc:
        raise RuntimeError("PORT must be a valid TCP port.") from exc

    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path not in {"/", "/health"}:
                self.send_response(404)
                self.end_headers()
                return
            body = b'{"status":"ok","service":"link-sharing-bot"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(("0.0.0.0", port), HealthHandler)
    threading.Thread(target=server.serve_forever, name="http-health", daemon=True).start()
    return server

def main():
    settings=Settings.from_env()
    admins={int(x) for x in os.getenv("ADMINS","").replace(","," ").split() if x.isdigit()}
    app=(ApplicationBuilder().token(settings.bot_token).post_init(post_init).post_shutdown(post_shutdown).build())
    app.bot_data.update({"settings":settings,"owner_id":settings.owner_id,"admins":admins,"clone_id":settings.clone_id,
        "image_url":settings.branding_image_url,"image_path":settings.branding_image_path,"small_caps":settings.small_caps,"channel_url":os.getenv("CHANNEL_URL","").strip(),
        "defaults":DEFAULT_MESSAGES,"product":"link"})
    app.add_handler(MessageHandler(filters.ALL, message_fsubs_gate), group=-10)
    app.add_handler(CallbackQueryHandler(callback_fsubs_gate), group=-2)
    app.add_handler(CallbackQueryHandler(close_branded_message, pattern=r"^branding:close$"), group=-1)
    add_common_handlers(app); add_editor_handlers(app); add_link_handlers(app); add_backup_handlers(app); add_broadcast_handlers(app); add_fsubs_handlers(app); app.add_error_handler(error_handler)
    app.bot_data["health_server"] = _start_health_server()
    app.run_polling(allowed_updates=["message","callback_query","chat_join_request"])

if __name__=="__main__": main()

from link_sharing_bot.main import main
from link_sharing_bot.handlers.links import (
    open_public_entry, schedulelink, scheduled_link_worker, check_fsub_callback,
    checkduplicate, editlink, requeststats, diagnostics,
)
from link_sharing_bot.backup import add_backup_handlers
from link_sharing_bot.broadcast import add_broadcast_handlers
from link_sharing_bot.branding_config import IMAGE_URL


def test_runtime_imports_and_branding():
    assert callable(main)
    assert all(callable(fn) for fn in (
        open_public_entry, schedulelink, scheduled_link_worker, check_fsub_callback,
        checkduplicate, editlink, requeststats, diagnostics,
    ))
    assert callable(add_backup_handlers) and callable(add_broadcast_handlers)
    assert IMAGE_URL == "https://i.ibb.co/PGpMYwYY/Gemini-Generated-Image-a7tjlia7tjlia7tj.png"

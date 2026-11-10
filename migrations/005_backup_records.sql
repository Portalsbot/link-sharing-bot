CREATE TABLE IF NOT EXISTS bot_backups (
    id BIGSERIAL PRIMARY KEY,
    clone_id TEXT NOT NULL,
    created_by BIGINT NOT NULL,
    backup_channel_id BIGINT,
    telegram_message_id BIGINT,
    telegram_file_id TEXT NOT NULL,
    file_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS bot_backups_clone_idx ON bot_backups(clone_id,id DESC);

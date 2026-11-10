CREATE TABLE IF NOT EXISTS bot_broadcasts (
    id BIGSERIAL PRIMARY KEY,
    clone_id TEXT NOT NULL,
    created_by BIGINT NOT NULL,
    payload JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft','pending','processing','completed','failed','cancelled')),
    scheduled_at TIMESTAMPTZ,
    sent_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    error_detail TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS bot_broadcasts_due_idx
    ON bot_broadcasts(clone_id,status,scheduled_at);

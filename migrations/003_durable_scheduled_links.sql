CREATE TABLE IF NOT EXISTS link_scheduled_jobs (
    id BIGSERIAL PRIMARY KEY,
    clone_id TEXT NOT NULL,
    channel_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    request_mode BOOLEAN NOT NULL DEFAULT FALSE,
    scheduled_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','processing','completed','failed','cancelled')),
    invite_url TEXT,
    error_detail TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS link_scheduled_jobs_due_idx
    ON link_scheduled_jobs(status, scheduled_at);

CREATE TABLE IF NOT EXISTS link_pending_join_requests (
    clone_id TEXT NOT NULL,
    channel_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','approved','declined','failed')),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (clone_id, channel_id, user_id)
);
CREATE INDEX IF NOT EXISTS link_pending_join_requests_idx
    ON link_pending_join_requests(clone_id,status,requested_at DESC);

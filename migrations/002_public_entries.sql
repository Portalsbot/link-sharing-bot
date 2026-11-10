CREATE TABLE IF NOT EXISTS link_public_entries (
    id BIGSERIAL PRIMARY KEY,
    clone_id TEXT NOT NULL,
    slug TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('channel','external')),
    channel_id BIGINT,
    target_url TEXT,
    title TEXT NOT NULL,
    created_by BIGINT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (clone_id, slug),
    CHECK (
        (kind='channel' AND channel_id IS NOT NULL AND target_url IS NULL)
        OR
        (kind='external' AND channel_id IS NULL AND target_url IS NOT NULL)
    )
);
CREATE INDEX IF NOT EXISTS link_public_entries_active_idx
    ON link_public_entries(clone_id, is_active);

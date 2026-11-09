CREATE TABLE IF NOT EXISTS bot_message_templates (
    clone_id TEXT NOT NULL,
    template_key TEXT NOT NULL,
    body TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (clone_id, template_key)
);
CREATE TABLE IF NOT EXISTS bot_message_buttons (
    clone_id TEXT NOT NULL,
    template_key TEXT NOT NULL,
    buttons JSONB NOT NULL DEFAULT '[]'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (clone_id, template_key)
);
CREATE TABLE IF NOT EXISTS bot_users (
    clone_id TEXT NOT NULL,
    user_id BIGINT NOT NULL,
    first_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_banned BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (clone_id, user_id)
);

CREATE TABLE IF NOT EXISTS link_channels (
    clone_id TEXT NOT NULL,
    channel_id BIGINT NOT NULL,
    title TEXT NOT NULL,
    approval_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    approval_delay_seconds INTEGER NOT NULL DEFAULT 0,
    default_ttl_seconds INTEGER NOT NULL DEFAULT 300,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY(clone_id, channel_id)
);
CREATE TABLE IF NOT EXISTS link_invites (
    id BIGSERIAL PRIMARY KEY,
    clone_id TEXT NOT NULL,
    channel_id BIGINT NOT NULL,
    invite_link TEXT NOT NULL,
    request_link BOOLEAN NOT NULL DEFAULT FALSE,
    expire_at TIMESTAMPTZ,
    revoked BOOLEAN NOT NULL DEFAULT FALSE,
    created_by BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS link_join_events (
    id BIGSERIAL PRIMARY KEY,
    clone_id TEXT NOT NULL,
    channel_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    event_status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS link_fsub_channels (
    clone_id TEXT NOT NULL,
    channel_id BIGINT NOT NULL,
    mode TEXT NOT NULL CHECK(mode IN ('normal','request')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY(clone_id,channel_id)
);
CREATE TABLE IF NOT EXISTS link_settings (
    clone_id TEXT NOT NULL,
    setting_key TEXT NOT NULL,
    setting_value TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY(clone_id,setting_key)
);
CREATE TABLE IF NOT EXISTS link_shortener_events (
    id BIGSERIAL PRIMARY KEY,
    clone_id TEXT NOT NULL,
    original_url TEXT NOT NULL,
    shortened_url TEXT,
    status TEXT NOT NULL,
    provider TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

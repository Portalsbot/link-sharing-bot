ALTER TABLE link_fsub_channels
    ADD COLUMN IF NOT EXISTS title TEXT,
    ADD COLUMN IF NOT EXISTS join_url TEXT;

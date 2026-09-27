CREATE TABLE IF NOT EXISTS social_sources (
    id BIGSERIAL PRIMARY KEY,
    source_type VARCHAR(16) NOT NULL,
    source_key VARCHAR(256) NOT NULL,
    display_name VARCHAR(256),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT social_sources_type_check CHECK (source_type IN ('x', 'telegram')),
    CONSTRAINT social_sources_key_unique UNIQUE (source_type, source_key)
);

CREATE TABLE IF NOT EXISTS social_posts (
    id BIGSERIAL PRIMARY KEY,
    source_id BIGINT NOT NULL REFERENCES social_sources(id) ON DELETE CASCADE,
    external_id VARCHAR(256) NOT NULL,
    author_key VARCHAR(256),
    published_at TIMESTAMPTZ NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    text_content TEXT NOT NULL,
    token_mints TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT social_posts_external_unique UNIQUE (source_id, external_id)
);

CREATE INDEX IF NOT EXISTS idx_social_posts_source_time
    ON social_posts (source_id, published_at DESC);

CREATE INDEX IF NOT EXISTS idx_social_posts_token_time
    ON social_posts USING GIN (token_mints);

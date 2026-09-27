ALTER TABLE token_buy_events
    ADD COLUMN IF NOT EXISTS confidence_level VARCHAR(32) NOT NULL DEFAULT 'BASE';

ALTER TABLE token_buy_events
    ADD COLUMN IF NOT EXISTS social_confirmed BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE token_buy_events
    ADD COLUMN IF NOT EXISTS social_confirmed_at TIMESTAMPTZ;

ALTER TABLE token_buy_events
    ADD COLUMN IF NOT EXISTS social_post_id BIGINT;

ALTER TABLE token_buy_events
    ADD CONSTRAINT token_buy_events_confidence_check
    CHECK (confidence_level IN ('BASE', 'SOCIAL_CONFIRMED'));

CREATE INDEX IF NOT EXISTS idx_token_buy_events_social_confirmed
    ON token_buy_events (social_confirmed, observed_at)
    WHERE social_confirmed = TRUE;

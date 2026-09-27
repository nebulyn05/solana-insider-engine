-- Durable live-stream recovery and deduplication.
CREATE TABLE IF NOT EXISTS stream_checkpoints (
    stream_name VARCHAR(64) PRIMARY KEY,
    last_slot BIGINT,
    last_signature VARCHAR(128),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS observed_transactions (
    signature VARCHAR(128) PRIMARY KEY,
    slot BIGINT,
    block_time TIMESTAMPTZ,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status VARCHAR(16) NOT NULL DEFAULT 'OBSERVED',
    decoder_version VARCHAR(32) NOT NULL DEFAULT 'v1',
    dex_program VARCHAR(64),
    wallet_address VARCHAR(44),
    raw JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_observed_transactions_slot
    ON observed_transactions (slot DESC);

CREATE INDEX IF NOT EXISTS idx_observed_transactions_wallet_time
    ON observed_transactions (wallet_address, observed_at DESC);

CREATE TABLE IF NOT EXISTS dex_trade_observations (
    id BIGSERIAL PRIMARY KEY,
    transaction_signature VARCHAR(128) NOT NULL REFERENCES observed_transactions(signature) ON DELETE CASCADE,
    wallet_address VARCHAR(44) NOT NULL,
    dex_name VARCHAR(64) NOT NULL,
    program_id VARCHAR(64),
    side VARCHAR(8) NOT NULL,
    input_mint VARCHAR(44),
    output_mint VARCHAR(44),
    input_amount NUMERIC(38,18),
    output_amount NUMERIC(38,18),
    price_sol NUMERIC(38,18),
    confidence NUMERIC(6,5) NOT NULL DEFAULT 0,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(transaction_signature, wallet_address, dex_name, output_mint)
);

CREATE INDEX IF NOT EXISTS idx_dex_trade_observations_wallet_time
    ON dex_trade_observations(wallet_address, observed_at DESC);

CREATE INDEX IF NOT EXISTS idx_dex_trade_observations_output_time
    ON dex_trade_observations(output_mint, observed_at DESC);

ALTER TABLE token_buy_events
    ADD COLUMN IF NOT EXISTS dex_name VARCHAR(64),
    ADD COLUMN IF NOT EXISTS dex_program_id VARCHAR(64),
    ADD COLUMN IF NOT EXISTS detection_confidence NUMERIC(6,5) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS detection_evidence JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_token_buy_events_dex
    ON token_buy_events(dex_name, observed_at DESC);

ALTER TABLE simulated_trades
    ADD COLUMN IF NOT EXISTS outcome VARCHAR(24),
    ADD COLUMN IF NOT EXISTS exit_reason VARCHAR(64),
    ADD COLUMN IF NOT EXISTS signal_created_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS detected_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS entry_latency_ms NUMERIC(20,3),
    ADD COLUMN IF NOT EXISTS decision_latency_ms NUMERIC(20,3),
    ADD COLUMN IF NOT EXISTS execution_latency_ms NUMERIC(20,3),
    ADD COLUMN IF NOT EXISTS total_latency_ms NUMERIC(20,3),
    ADD COLUMN IF NOT EXISTS max_favorable_return_bps NUMERIC(20,4),
    ADD COLUMN IF NOT EXISTS max_adverse_return_bps NUMERIC(20,4);

ALTER TABLE simulated_trades
    DROP CONSTRAINT IF EXISTS simulated_trades_outcome_check;
ALTER TABLE simulated_trades
    ADD CONSTRAINT simulated_trades_outcome_check
    CHECK (outcome IS NULL OR outcome IN (
        'WIN','LOSS','FALSE_POSITIVE','EXPIRED','NO_LIQUIDITY','CANCELLED'
    ));

CREATE INDEX IF NOT EXISTS idx_simulated_trades_detector_entry
    ON simulated_trades ((metadata->>'detector'), entry_at DESC);
CREATE INDEX IF NOT EXISTS idx_simulated_trades_outcome
    ON simulated_trades (outcome)
    WHERE outcome IS NOT NULL;

CREATE TABLE IF NOT EXISTS wallet_features (
    wallet_address VARCHAR(44) PRIMARY KEY,
    network VARCHAR(16) NOT NULL DEFAULT 'devnet',
    observed_buy_count BIGINT NOT NULL DEFAULT 0,
    distinct_token_count BIGINT NOT NULL DEFAULT 0,
    first_seen_at TIMESTAMPTZ,
    last_seen_at TIMESTAMPTZ,
    avg_inter_buy_seconds NUMERIC(20,4),
    shared_funder_count BIGINT NOT NULL DEFAULT 0,
    deployer_lineage_hits BIGINT NOT NULL DEFAULT 0,
    social_confirmation_count BIGINT NOT NULL DEFAULT 0,
    successful_signal_count BIGINT NOT NULL DEFAULT 0,
    failed_signal_count BIGINT NOT NULL DEFAULT 0,
    win_rate NUMERIC(12,8),
    reputation_score NUMERIC(12,8) NOT NULL DEFAULT 0,
    feature_version INTEGER NOT NULL DEFAULT 1,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT wallet_features_network_check CHECK (network IN ('devnet','mainnet-beta')),
    CONSTRAINT wallet_features_score_check CHECK (reputation_score BETWEEN 0 AND 1)
);

CREATE TABLE IF NOT EXISTS signal_scores (
    id BIGSERIAL PRIMARY KEY,
    signal_id VARCHAR(128) NOT NULL UNIQUE,
    token_mint VARCHAR(44) NOT NULL,
    score NUMERIC(8,4) NOT NULL,
    components JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT signal_scores_score_check CHECK (score BETWEEN 0 AND 100)
);

CREATE INDEX IF NOT EXISTS idx_signal_scores_token_time
    ON signal_scores (token_mint, created_at DESC);

CREATE TABLE IF NOT EXISTS execution_events (
    id BIGSERIAL PRIMARY KEY,
    signal_id VARCHAR(128),
    trade_id UUID,
    event_type VARCHAR(32) NOT NULL,
    event_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_execution_events_signal_time
    ON execution_events (signal_id, event_at);
CREATE INDEX IF NOT EXISTS idx_execution_events_trade_time
    ON execution_events (trade_id, event_at);

CREATE TABLE IF NOT EXISTS replay_events (
    id BIGSERIAL PRIMARY KEY,
    replay_run_id UUID NOT NULL,
    sequence_no BIGINT NOT NULL,
    event_type VARCHAR(32) NOT NULL,
    event_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (replay_run_id, sequence_no)
);

CREATE INDEX IF NOT EXISTS idx_replay_events_run_time
    ON replay_events (replay_run_id, event_at);

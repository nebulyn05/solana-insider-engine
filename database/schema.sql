CREATE TABLE IF NOT EXISTS tracked_wallets (
    id BIGSERIAL PRIMARY KEY,
    wallet_address VARCHAR(44) NOT NULL UNIQUE,
    network VARCHAR(16) NOT NULL DEFAULT 'mainnet-beta',
    label VARCHAR(128),
    cex_label VARCHAR(128),
    multi_hop_label VARCHAR(128),
    is_cex BOOLEAN NOT NULL DEFAULT FALSE,
    is_tracked BOOLEAN NOT NULL DEFAULT TRUE,
    is_warm BOOLEAN NOT NULL DEFAULT FALSE,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT tracked_wallets_network_check CHECK (network IN ('devnet', 'mainnet-beta'))
);

CREATE INDEX IF NOT EXISTS idx_tracked_wallets_cex_label
    ON tracked_wallets (cex_label) WHERE cex_label IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tracked_wallets_multi_hop_label
    ON tracked_wallets (multi_hop_label) WHERE multi_hop_label IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tracked_wallets_tracked
    ON tracked_wallets (is_tracked);
CREATE INDEX IF NOT EXISTS idx_tracked_wallets_warm
    ON tracked_wallets (is_warm) WHERE is_warm = TRUE;

CREATE TABLE IF NOT EXISTS funding_ledger (
    id BIGSERIAL PRIMARY KEY,
    transaction_signature VARCHAR(128) NOT NULL UNIQUE,
    slot BIGINT NOT NULL,
    block_time TIMESTAMPTZ,
    source_wallet_id BIGINT REFERENCES tracked_wallets(id) ON DELETE SET NULL,
    destination_wallet_id BIGINT NOT NULL REFERENCES tracked_wallets(id) ON DELETE CASCADE,
    token_mint VARCHAR(44),
    amount NUMERIC(38, 18) NOT NULL,
    hop_depth INTEGER NOT NULL DEFAULT 0,
    lineage_id UUID NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT funding_ledger_amount_check CHECK (amount >= 0),
    CONSTRAINT funding_ledger_hop_depth_check CHECK (hop_depth >= 0)
);
CREATE INDEX IF NOT EXISTS idx_funding_ledger_destination ON funding_ledger(destination_wallet_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_funding_ledger_source ON funding_ledger(source_wallet_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_funding_ledger_lineage ON funding_ledger(lineage_id, hop_depth);

CREATE TABLE IF NOT EXISTS token_buy_events (
    id BIGSERIAL PRIMARY KEY,
    wallet_address VARCHAR(44) NOT NULL,
    token_mint VARCHAR(44) NOT NULL,
    transaction_signature VARCHAR(128) NOT NULL UNIQUE,
    observed_at TIMESTAMPTZ NOT NULL,
    executed_price NUMERIC(38, 18) NOT NULL,
    confidence_level VARCHAR(32) NOT NULL DEFAULT 'BASE',
    social_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
    social_confirmed_at TIMESTAMPTZ,
    social_post_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT token_buy_events_price_check CHECK (executed_price >= 0),
    CONSTRAINT token_buy_events_confidence_check CHECK (confidence_level IN ('BASE', 'SOCIAL_CONFIRMED'))
);
CREATE INDEX IF NOT EXISTS idx_token_buy_events_token_time ON token_buy_events(token_mint, observed_at);
CREATE INDEX IF NOT EXISTS idx_token_buy_events_wallet_time ON token_buy_events(wallet_address, observed_at);

CREATE TABLE IF NOT EXISTS token_metadata (
    mint_address VARCHAR(44) PRIMARY KEY,
    network VARCHAR(16) NOT NULL DEFAULT 'mainnet-beta',
    name VARCHAR(256),
    symbol VARCHAR(64),
    decimals SMALLINT NOT NULL DEFAULT 0,
    metadata_uri TEXT,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT token_metadata_network_check CHECK (network IN ('devnet', 'mainnet-beta')),
    CONSTRAINT token_metadata_decimals_check CHECK (decimals BETWEEN 0 AND 18)
);
CREATE INDEX IF NOT EXISTS idx_token_metadata_symbol ON token_metadata(symbol) WHERE symbol IS NOT NULL;

CREATE TABLE IF NOT EXISTS simulated_trades (
    id BIGSERIAL PRIMARY KEY,
    trade_id UUID NOT NULL UNIQUE,
    wallet_id BIGINT REFERENCES tracked_wallets(id) ON DELETE SET NULL,
    token_mint VARCHAR(44) NOT NULL REFERENCES token_metadata(mint_address) ON DELETE RESTRICT,
    side VARCHAR(8) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'OPEN',
    quantity NUMERIC(38, 18) NOT NULL,
    requested_price NUMERIC(38, 18) NOT NULL,
    executed_price NUMERIC(38, 18),
    exit_price NUMERIC(38, 18),
    requested_notional NUMERIC(38, 18),
    executed_notional NUMERIC(38, 18),
    slippage_bps NUMERIC(12, 4) NOT NULL DEFAULT 0,
    slippage_amount NUMERIC(38, 18) NOT NULL DEFAULT 0,
    fees NUMERIC(38, 18) NOT NULL DEFAULT 0,
    realized_pnl NUMERIC(38, 18),
    signal_id VARCHAR(128) UNIQUE,
    entry_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    exit_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT simulated_trades_side_check CHECK (side IN ('BUY', 'SELL')),
    CONSTRAINT simulated_trades_status_check CHECK (status IN ('OPEN', 'CLOSED', 'CANCELLED')),
    CONSTRAINT simulated_trades_quantity_check CHECK (quantity > 0),
    CONSTRAINT simulated_trades_requested_price_check CHECK (requested_price >= 0),
    CONSTRAINT simulated_trades_slippage_check CHECK (slippage_bps >= 0),
    CONSTRAINT simulated_trades_fees_check CHECK (fees >= 0)
);
CREATE INDEX IF NOT EXISTS idx_simulated_trades_wallet ON simulated_trades(wallet_id, entry_at DESC);
CREATE INDEX IF NOT EXISTS idx_simulated_trades_token ON simulated_trades(token_mint, entry_at DESC);
CREATE INDEX IF NOT EXISTS idx_simulated_trades_status ON simulated_trades(status);
CREATE INDEX IF NOT EXISTS idx_simulated_trades_signal ON simulated_trades(signal_id) WHERE signal_id IS NOT NULL;

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
    CONSTRAINT social_posts_external_unique UNIQUE(source_id, external_id)
);
CREATE INDEX IF NOT EXISTS idx_social_posts_source_time ON social_posts(source_id, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_social_posts_token_time ON social_posts USING GIN(token_mints);

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

CREATE TABLE IF NOT EXISTS wallet_features (
    wallet_address VARCHAR(44) PRIMARY KEY,
    network VARCHAR(16) NOT NULL DEFAULT 'mainnet-beta',
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
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS signal_scores (
    id BIGSERIAL PRIMARY KEY,
    signal_id VARCHAR(128) NOT NULL UNIQUE,
    token_mint VARCHAR(44) NOT NULL,
    score NUMERIC(8,4) NOT NULL,
    components JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS execution_events (
    id BIGSERIAL PRIMARY KEY,
    signal_id VARCHAR(128),
    trade_id UUID,
    event_type VARCHAR(32) NOT NULL,
    event_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS replay_events (
    id BIGSERIAL PRIMARY KEY,
    replay_run_id UUID NOT NULL,
    sequence_no BIGINT NOT NULL,
    event_type VARCHAR(32) NOT NULL,
    event_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE(replay_run_id, sequence_no)
);

-- Live engine hardening.
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
CREATE INDEX IF NOT EXISTS idx_observed_transactions_slot ON observed_transactions(slot DESC);
CREATE INDEX IF NOT EXISTS idx_observed_transactions_wallet_time ON observed_transactions(wallet_address, observed_at DESC);

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
CREATE INDEX IF NOT EXISTS idx_dex_trade_observations_wallet_time ON dex_trade_observations(wallet_address, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_dex_trade_observations_output_time ON dex_trade_observations(output_mint, observed_at DESC);

ALTER TABLE token_buy_events
    ADD COLUMN IF NOT EXISTS dex_name VARCHAR(64),
    ADD COLUMN IF NOT EXISTS dex_program_id VARCHAR(64),
    ADD COLUMN IF NOT EXISTS detection_confidence NUMERIC(6,5) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS detection_evidence JSONB NOT NULL DEFAULT '{}'::jsonb;
CREATE INDEX IF NOT EXISTS idx_token_buy_events_dex ON token_buy_events(dex_name, observed_at DESC);

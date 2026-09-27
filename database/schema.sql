CREATE TABLE IF NOT EXISTS tracked_wallets (
    id BIGSERIAL PRIMARY KEY,
    wallet_address VARCHAR(44) NOT NULL UNIQUE,
    network VARCHAR(16) NOT NULL DEFAULT 'devnet',
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
    ON tracked_wallets (cex_label)
    WHERE cex_label IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_tracked_wallets_multi_hop_label
    ON tracked_wallets (multi_hop_label)
    WHERE multi_hop_label IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_tracked_wallets_tracked
    ON tracked_wallets (is_tracked);

CREATE INDEX IF NOT EXISTS idx_tracked_wallets_warm
    ON tracked_wallets (is_warm)
    WHERE is_warm = TRUE;


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

CREATE INDEX IF NOT EXISTS idx_funding_ledger_destination
    ON funding_ledger (destination_wallet_id, observed_at DESC);

CREATE INDEX IF NOT EXISTS idx_funding_ledger_source
    ON funding_ledger (source_wallet_id, observed_at DESC);

CREATE INDEX IF NOT EXISTS idx_funding_ledger_lineage
    ON funding_ledger (lineage_id, hop_depth);


CREATE TABLE IF NOT EXISTS token_buy_events (
    id BIGSERIAL PRIMARY KEY,
    wallet_address VARCHAR(44) NOT NULL,
    token_mint VARCHAR(44) NOT NULL,
    transaction_signature VARCHAR(128) NOT NULL UNIQUE,
    observed_at TIMESTAMPTZ NOT NULL,
    executed_price NUMERIC(38, 18) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT token_buy_events_price_check CHECK (executed_price >= 0)
);

CREATE INDEX IF NOT EXISTS idx_token_buy_events_token_time
    ON token_buy_events (token_mint, observed_at);

CREATE INDEX IF NOT EXISTS idx_token_buy_events_wallet_time
    ON token_buy_events (wallet_address, observed_at);

CREATE TABLE IF NOT EXISTS token_metadata (
    mint_address VARCHAR(44) PRIMARY KEY,
    network VARCHAR(16) NOT NULL DEFAULT 'devnet',
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

CREATE INDEX IF NOT EXISTS idx_token_metadata_symbol
    ON token_metadata (symbol)
    WHERE symbol IS NOT NULL;


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

CREATE INDEX IF NOT EXISTS idx_simulated_trades_wallet
    ON simulated_trades (wallet_id, entry_at DESC);

CREATE INDEX IF NOT EXISTS idx_simulated_trades_token
    ON simulated_trades (token_mint, entry_at DESC);

CREATE INDEX IF NOT EXISTS idx_simulated_trades_status
    ON simulated_trades (status);

CREATE INDEX IF NOT EXISTS idx_simulated_trades_signal
    ON simulated_trades (signal_id)
    WHERE signal_id IS NOT NULL;


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

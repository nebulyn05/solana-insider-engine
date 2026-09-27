ALTER TABLE tracked_wallets
    ADD COLUMN IF NOT EXISTS is_warm BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_tracked_wallets_warm
    ON tracked_wallets (is_warm)
    WHERE is_warm = TRUE;

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


CREATE UNIQUE INDEX IF NOT EXISTS uq_simulated_trades_signal_id
    ON simulated_trades (signal_id)
    WHERE signal_id IS NOT NULL;

-- Mainnet observation cutover. Existing historical devnet rows are retained.
-- New/default engine records are mainnet-beta.

ALTER TABLE tracked_wallets ALTER COLUMN network SET DEFAULT 'mainnet-beta';
ALTER TABLE token_metadata ALTER COLUMN network SET DEFAULT 'mainnet-beta';
ALTER TABLE wallet_features ALTER COLUMN network SET DEFAULT 'mainnet-beta';

CREATE INDEX IF NOT EXISTS idx_tracked_wallets_mainnet_tracked
    ON tracked_wallets (wallet_address, last_seen_at DESC)
    WHERE network='mainnet-beta' AND is_tracked=TRUE;

CREATE INDEX IF NOT EXISTS idx_token_buy_events_wallet_observed
    ON token_buy_events (wallet_address, observed_at DESC);

CREATE INDEX IF NOT EXISTS idx_token_buy_events_token_observed
    ON token_buy_events (token_mint, observed_at DESC);

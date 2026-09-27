# Solana Insider Tracking & Proactive Execution System

Mainnet-first Solana observation and paper-trading backend.

## Runtime boundary

- **Network:** Solana mainnet-beta.
- **Data:** live mainnet observations.
- **Execution:** paper trading only.
- **Signing/broadcast:** disabled. No private key or transaction submission path is enabled.
- **Simulation:** simulated entries/exits are written to PostgreSQL using observed mainnet prices and configurable execution/slippage models.

## Mainnet live stream

Run `python scripts/run_mainnet_stream.py`.

The wallet stream uses Solana mainnet WebSocket `logsSubscribe` notifications for configured tracked wallets and then fetches confirmed transaction details through mainnet JSON-RPC. It identifies candidate token acquisitions where the tracked wallet spends SOL and receives an SPL/Token-2022 balance increase. These are observations/heuristics, not proof of economic intent.

Configure tracked wallets in PostgreSQL with `network = 'mainnet-beta'`, `is_tracked = TRUE`, and `is_warm = TRUE` for wallets eligible for warm-wallet clustering.

## Paper simulation

Run `python scripts/run_48h_simulation.py --hours 48`.

The simulation verifies the mainnet genesis hash before processing observations and never signs or broadcasts a transaction.

## Environment

Copy `.env.example` and provide `DATABASE_URL`. `PAPER_TRADING=true` and `LIVE_EXECUTION=false` are mandatory safety settings.

Historical Devnet rows are retained where they already exist; new/default records use `mainnet-beta`.

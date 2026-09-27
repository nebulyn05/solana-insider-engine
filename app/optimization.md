# Engine Optimization Layer

This layer hardens the simulation engine without enabling live execution.

## Implemented

- Event-driven in-process bus for normalized ingestion-to-signal handoff.
- True sliding-window warm-wallet clustering.
- Explicit signal scoring with persisted component breakdown.
- Wallet feature/reputation materialization.
- Paper trade lifecycle with atomic close/cancel and explicit outcomes.
- Dynamic simulation slippage from liquidity participation, volatility and latency.
- End-to-end latency sample model.
- Replay engine for JSONL event streams and strategy comparison helpers.
- Monte Carlo resampling for paper-return distributions.
- Position manager with take-profit, stop-loss and time-expiry simulation.
- Performance reporting that distinguishes incomplete outcome data from measured outcomes.

## Safety boundary

No component in this layer signs or broadcasts a Solana transaction. Solana Devnet remains the test environment, and on-chain transaction simulation continues to use the RPC simulation path rather than live execution.
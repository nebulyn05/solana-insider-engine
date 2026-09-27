# Solana Insider Tracking & Proactive Execution System

A **mainnet-first Solana wallet-intelligence, market-observation, signal-scoring, and paper-trading engine** designed to detect coordinated wallet activity, enrich it with on-chain and social intelligence, and evaluate actionable signals without risking real funds.

> **Important:** This repository is deliberately **paper-trading only**. It observes Solana mainnet data, but it does not contain an enabled private-key signing path and does not broadcast real transactions.

---

## Table of Contents

- [What this system does](#what-this-system-does)
- [Runtime safety boundary](#runtime-safety-boundary)
- [Architecture](#architecture)
- [Signal lifecycle](#signal-lifecycle)
- [Intelligence layers](#intelligence-layers)
- [Mainnet ingestion](#mainnet-ingestion)
- [DEX detection](#dex-detection)
- [Social intelligence](#social-intelligence)
- [Paper execution and position management](#paper-execution-and-position-management)
- [Replay, backtesting, and Monte Carlo](#replay-backtesting-and-monte-carlo)
- [Database](#database)
- [Project structure](#project-structure)
- [Requirements](#requirements)
- [Local setup](#local-setup)
- [Environment configuration](#environment-configuration)
- [Adding wallets to track](#adding-wallets-to-track)
- [Running the live paper engine](#running-the-live-paper-engine)
- [Running individual components](#running-individual-components)
- [Testing](#testing)
- [Operational considerations](#operational-considerations)
- [Known limitations](#known-limitations)
- [Development principles](#development-principles)

---

## What this system does

The engine is intended to answer a practical question:

> **When a group of historically interesting Solana wallets begins accumulating the same asset, is there enough independent evidence to treat the activity as a high-quality paper-trading signal?**

It combines several evidence sources rather than relying on a single wallet or transaction heuristic.

### Core capabilities

- Live Solana **mainnet-beta** wallet observation.
- Per-wallet transaction monitoring.
- Transaction recovery after WebSocket reconnects.
- Durable stream checkpoints and transaction deduplication.
- DEX/router-aware transaction decoding.
- Helius Parsed Events integration when configured.
- Local RPC-based DEX decoding fallback.
- Warm-wallet and spatiotemporal clustering.
- Wallet funding and multi-hop ancestry analysis.
- Shared first-funder analysis.
- Wallet feature extraction and reputation-oriented features.
- Social post ingestion and token-mint extraction.
- Time-bounded social co-occurrence confirmation.
- Signal scoring with persisted component breakdowns.
- Paper-only execution lifecycle.
- Dynamic paper slippage modelling.
- Take-profit, stop-loss, and maximum-hold position management.
- Read-only market marking through Jupiter quotes.
- Local and on-chain shadow simulation.
- Replay engine and Monte Carlo analysis.
- Phase-5 reporting and performance analysis.
- Latency instrumentation.
- PostgreSQL persistence throughout the observation/simulation pipeline.

The system is deliberately separated into **observation**, **intelligence**, **decision**, and **simulation** layers so that changing the data source does not automatically create a path to real execution.

---

# Runtime safety boundary

This is the most important architectural property of the project.

| Capability | Status |
|---|---|
| Solana mainnet observation | Enabled |
| Mainnet transaction inspection | Enabled |
| DEX/swap detection | Enabled |
| Market quote retrieval | Read-only |
| Signal generation | Enabled |
| Paper entries | Enabled |
| Paper exits | Enabled |
| Historical replay | Enabled |
| Private-key management | Not part of the runtime |
| Transaction signing | Disabled |
| Transaction broadcast | Disabled |
| Real-money execution | **Not supported** |

The runtime safety guard requires:

```text
SOLANA_NETWORK=mainnet-beta
PAPER_TRADING=true
LIVE_EXECUTION=false
```

The safety layer also rejects common private-key environment variable names.

**Do not remove these protections in order to make the system trade real funds.** Real execution would require a separate, explicitly designed execution service with independent key custody, authorization, risk limits, auditing, and operational controls.

---

# Architecture

At a high level:

```text
                         SOLANA MAINNET
                              |
                    +---------+---------+
                    |                   |
             WebSocket logs       RPC transaction data
                    |                   |
                    +---------+---------+
                              |
                     Transaction Recovery
                              |
                    +---------v---------+
                    | Transaction / DEX |
                    |     Decoder       |
                    +---------+---------+
                              |
                 +------------+-------------+
                 |                          |
          BUY observations            Other observations
                 |                          |
                 v                          v
        Token Buy Events             Observed Transactions
                 |
        +--------+---------+
        |                  |
        v                  v
 Wallet Features       Social Confirmation
        |                  |
        +--------+---------+
                 |
                 v
       Sliding Wallet Cluster
                 |
                 v
          Signal Scoring
                 |
                 v
        Paper Entry Model
                 |
                 v
        Simulated Position
                 |
       +---------+---------+
       |         |         |
       v         v         v
      TP        SL      Time Expiry
       |         |         |
       +---------+---------+
                 |
                 v
          Realized Paper P&L
                 |
                 v
        Reporting / Replay /
        Strategy Evaluation
```

---

# Signal lifecycle

A typical signal moves through these conceptual stages:

1. **Observe**  
   A tracked wallet produces a relevant mainnet transaction.

2. **Recover**  
   The transaction is retrieved through RPC and normalized.

3. **Decode**  
   The engine determines whether the transaction contains sufficiently strong DEX/swap evidence.

4. **Normalize**  
   A normalized buy observation is persisted with token, wallet, price, DEX, confidence, and evidence.

5. **Cluster**  
   Recent buys for the same token are evaluated inside a sliding time window.

6. **Enrich**  
   Wallet features, funding relationships, social confirmation, and other available evidence are incorporated.

7. **Score**  
   The scoring engine calculates a signal score and persists the individual components.

8. **Paper entry**  
   If the score clears the configured threshold, a simulated position is created.

9. **Mark**  
   The position manager obtains a read-only market quote when available.

10. **Exit**  
    The position is closed by take-profit, stop-loss, or maximum holding time.

11. **Evaluate**  
    P&L, latency, slippage, outcome, and other metrics can be reported or replayed.

No stage signs or broadcasts a Solana transaction.

---

# Intelligence layers

## 1. Wallet observation

The live mainnet stream watches the wallets stored in `tracked_wallets`.

The stream maintains durable processing information so a temporary WebSocket failure does not automatically mean that all observations after the disconnect are lost.

Important persistence:

- `stream_checkpoints`
- `observed_transactions`
- `dex_trade_observations`

On reconnect, recent wallet signatures are recovered and duplicate transactions are ignored.

---

## 2. Warm-wallet clustering

The clustering layer looks for multiple relevant wallets interacting with the same token inside a configurable time window.

Important settings:

```text
MIN_WARM_WALLETS=3
CLUSTER_WINDOW_SECONDS=30
```

The sliding-window implementation is intended to distinguish concentrated activity from isolated wallet purchases.

---

## 3. Funding and ancestry intelligence

The project contains:

- first-funder analysis;
- multi-hop funding ancestry;
- funding-ledger persistence;
- deployer-lineage-related features;
- shared funding relationships.

This allows a group of apparently independent wallets to be examined for common upstream funding relationships.

---

## 4. Wallet features

Wallet-level features include concepts such as:

- observed buy count;
- distinct tokens;
- first/last activity;
- average inter-buy timing;
- shared-funder counts;
- deployer-lineage hits;
- social confirmations;
- successful/failed signal counts;
- win rate;
- reputation score.

These features can feed later signal scoring and research workflows.

---

## 5. Social intelligence

The social subsystem supports source records and observed posts.

Posts can contain extracted Solana mint addresses. The social co-occurrence layer checks whether a relevant social event appears in the configured time relationship to an on-chain wallet buy.

The goal is **confirmation**, not blind reliance on social sentiment.

The current implementation includes social models, repository handling, Solana mint extraction, WebSocket ingestion, and co-occurrence evaluation.

---

## 6. Signal scoring

The scoring layer persists:

- signal identifier;
- token mint;
- final score;
- component values;
- creation time.

The scoring architecture is intentionally decomposed so individual evidence dimensions can be changed without rewriting the ingestion layer.

---

# Mainnet ingestion

The primary live entry point is:

```text
scripts/run_live_engine.py
```

which starts:

```text
app.runtime.service.main()
```

The supervisor coordinates:

- mainnet wallet stream;
- paper position monitoring;
- social confirmation monitoring;
- wallet feature refresh;
- intelligence refresh tasks already wired into the runtime.

The lower-level stream is also available through:

```text
scripts/run_mainnet_stream.py
```

---

# DEX detection

The engine does not treat every SOL decrease/token increase as a confirmed DEX trade.

The current decoder considers:

- invoked program IDs;
- configured DEX/router programs;
- transaction account information;
- swap-like log evidence;
- SOL/token balance changes;
- transaction success/failure;
- configured venue names.

### Helius-assisted decoding

When `HELIUS_API_KEY` is available, the engine can use the Helius Parsed Events endpoint first.

If the parsed decoder is unavailable or does not provide a usable classification, the local RPC decoder is used.

### Local decoder configuration

Use:

```text
DEX_PROGRAMS=PROGRAM_ID=NAME,PROGRAM_ID=NAME
```

For example:

```text
DEX_PROGRAMS=PROGRAM_ID_1=ORCA,PROGRAM_ID_2=ROUTER
```

Use the **actual mainnet program IDs** you intend to monitor.

The repository has Orca-related shadow tooling, but venue-specific production decoding should always be verified against the exact program/instruction format being observed.

### Current scope

The local decoder is intentionally conservative and focuses on strong SOL-input buy evidence. Token-to-token routing and richer venue-specific instruction decoding are areas where additional adapters can be added.

---

# Social intelligence

The social pipeline is separated from the on-chain pipeline.

Relevant components:

```text
app/social/models.py
app/social/repository.py
app/social/solana_mints.py
app/social/websocket.py
app/intelligence/social_cooccurrence.py
```

This separation makes it possible to run the blockchain engine even when no social source is configured.

---

# Paper execution and position management

Paper execution is not a fake transaction broadcast.

Instead, the engine creates a simulated trade record containing information such as:

- wallet;
- token;
- quantity;
- requested price;
- simulated execution price;
- notional;
- slippage;
- signal ID;
- timing/latency;
- detector metadata;
- execution metadata.

### Dynamic slippage

The paper execution model accounts for configurable:

- paper liquidity;
- trade notional;
- volatility;
- network delay.

Example:

```text
PAPER_NOTIONAL_SOL=1
PAPER_LIQUIDITY_SOL=100
PAPER_VOLATILITY_BPS=100
PAPER_NETWORK_DELAY_MS=100
```

This is intentionally more informative than assuming a constant fixed slippage percentage.

### Position policy

The current position manager uses:

- **10% take profit**
- **8% stop loss**
- **900 seconds maximum hold**

These values are implemented defaults for the simulation layer and should be treated as strategy parameters, not claims about future market performance.

The manager uses a read-only Jupiter quote when possible and falls back to an available observed mark when the quote provider is unavailable.

---

# Shadow simulation

The project contains multiple simulation levels:

### Local shadow simulation

Used for deterministic sellability/P&L modelling without requiring a live transaction.

### On-chain shadow simulation

Used to inspect whether a transaction/instruction path can be simulated against the chain without submitting it.

### Orca shadow builder

The TypeScript tooling can build unsigned Orca Whirlpools instructions for development/testing.

**Unsigned does not mean executed.** The project intentionally does not provide the private-key signing/broadcast step.

---

# Replay, backtesting, and Monte Carlo

The engine is not limited to live observation.

## Replay

```text
app/replay/engine.py
app/replay/compare.py
```

Replay allows historical event streams to be fed through strategy logic.

## Monte Carlo

```text
app/replay/monte_carlo.py
scripts/run_monte_carlo.py
```

Monte Carlo tooling can be used to examine how simulated strategy results vary under repeated randomized assumptions.

## Phase-5 simulation/reporting

The repository also contains:

```text
app/simulation/live_48h.py
app/reporting/phase5.py
scripts/run_48h_simulation.py
scripts/report_phase5.py
```

These components are useful for comparing signal quality, paper execution behaviour, P&L, win/loss outcomes, false positives, slippage, and latency.

---

# Database

PostgreSQL is the system's durable state store.

The base schema is:

```text
database/schema.sql
```

Important tables include:

| Table | Purpose |
|---|---|
| `tracked_wallets` | Wallets monitored by the engine |
| `funding_ledger` | Funding/ancestry relationships |
| `token_buy_events` | Normalized wallet buy observations |
| `token_metadata` | Token metadata and network |
| `simulated_trades` | Paper positions and outcomes |
| `social_sources` | Configured social sources |
| `social_posts` | Observed social posts |
| `wallet_features` | Derived wallet behaviour features |
| `signal_scores` | Persisted signal scores |
| `execution_events` | Paper execution lifecycle events |
| `replay_events` | Replay event streams |
| `stream_checkpoints` | Durable ingestion checkpoints |
| `observed_transactions` | Transaction-level observation/deduplication |
| `dex_trade_observations` | Normalized DEX evidence |

The database also contains indexes and constraints intended to make the live observation path idempotent and queryable.

## Migrations

The repository currently contains these ordered migrations:

```text
003_phase3_spatiotemporal_clustering.sql
004_phase4_social_stream.sql
005_phase4_social_cooccurrence.sql
006_engine_optimization.sql
007_mainnet_paper_cutover.sql
008_live_engine_hardening.sql
```

Apply them in order after the base schema when setting up an existing database.

> The repository does not currently provide a general-purpose migration runner. Migration application should therefore be handled explicitly by the deployment/setup process.

---

# Project structure

```text
.
├── app/
│   ├── config/
│   │   └── settings.py
│   ├── database/
│   │   └── connection.py
│   ├── events/
│   │   └── bus.py
│   ├── execution/
│   │   ├── lifecycle.py
│   │   └── slippage.py
│   ├── ingestion/
│   │   ├── dex_decoder.py
│   │   ├── helius_parser.py
│   │   └── mainnet_wallet_stream.py
│   ├── intelligence/
│   │   ├── clustering.py
│   │   ├── first_funder.py
│   │   ├── onchain_shadow.py
│   │   ├── orca_shadow.py
│   │   ├── scoring.py
│   │   ├── shadow.py
│   │   ├── sliding_clustering.py
│   │   ├── social_cooccurrence.py
│   │   └── wallet_features.py
│   ├── market/
│   │   └── jupiter.py
│   ├── observability/
│   │   └── latency.py
│   ├── replay/
│   │   ├── compare.py
│   │   ├── engine.py
│   │   └── monte_carlo.py
│   ├── reporting/
│   │   └── phase5.py
│   ├── runtime/
│   │   ├── pipeline.py
│   │   ├── safety.py
│   │   └── service.py
│   ├── simulation/
│   │   ├── live_48h.py
│   │   └── position_manager.py
│   └── social/
│       ├── models.py
│       ├── repository.py
│       ├── solana_mints.py
│       └── websocket.py
│
├── database/
│   ├── schema.sql
│   └── migrations/
│
├── scripts/
│   ├── init_db.py
│   ├── run_live_engine.py
│   ├── run_mainnet_stream.py
│   ├── run_48h_simulation.py
│   ├── run_monte_carlo.py
│   ├── run_clustering.py
│   ├── run_first_funder.py
│   ├── run_onchain_shadow.py
│   ├── run_shadow.py
│   ├── run_social_cooccurrence.py
│   ├── run_social_websocket.py
│   ├── replay_jsonl.py
│   ├── refresh_wallet_features.py
│   └── report_phase5.py
│
├── tests/
│   └── unit/
│
├── .env.example
├── package.json
├── pyproject.toml
└── README.md
```

---

# Requirements

## Software

- Python **3.11+**
- PostgreSQL
- Node.js/npm for the TypeScript Orca shadow tooling
- Internet access to the configured Solana RPC/WebSocket endpoint

## Python dependencies

The project declares:

- `psycopg2-binary`
- `websockets`
- `grpcio`
- `python-dotenv`

Test dependencies are provided through the `test` optional extra and include pytest.

---

# Local setup

## 1. Clone the repository

```bash
git clone https://github.com/nebulyn05/solana-insider-engine.git
cd solana-insider-engine
```

## 2. Create a virtual environment

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

## 3. Install the project

```bash
python -m pip install --upgrade pip
pip install -e .
```

For development/testing:

```bash
pip install -e ".[test]"
```

## 4. Create PostgreSQL database

Example:

```sql
CREATE DATABASE solana_insider_sim;
```

Then configure `DATABASE_URL`.

Example:

```text
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/solana_insider_sim
```

## 5. Copy environment configuration

Linux/macOS:

```bash
cp .env.example .env
```

Windows:

```powershell
Copy-Item .env.example .env
```

Edit `.env` before starting the engine.

## 6. Initialize the base database schema

```bash
python scripts/init_db.py
```

This executes:

```text
database/schema.sql
```

against the configured PostgreSQL database.

## 7. Apply migrations

Apply migrations in numerical order:

```bash
psql "$DATABASE_URL" -f database/migrations/003_phase3_spatiotemporal_clustering.sql
psql "$DATABASE_URL" -f database/migrations/004_phase4_social_stream.sql
psql "$DATABASE_URL" -f database/migrations/005_phase4_social_cooccurrence.sql
psql "$DATABASE_URL" -f database/migrations/006_engine_optimization.sql
psql "$DATABASE_URL" -f database/migrations/007_mainnet_paper_cutover.sql
psql "$DATABASE_URL" -f database/migrations/008_live_engine_hardening.sql
```

If using a GUI PostgreSQL client, execute the same files in the same order.

---

# Environment configuration

Start from:

```text
.env.example
```

## Core application

```text
APP_ENV=production
LOG_LEVEL=INFO
```

## Solana

The project is configured for mainnet:

```text
SOLANA_NETWORK=mainnet-beta
SOLANA_RPC_URL=https://api.mainnet.solana.com
SOLANA_WS_URL=wss://api.mainnet.solana.com
```

The public Solana endpoint can be rate-limited. For sustained operation, use a dedicated RPC provider.

## Optional Helius

```text
HELIUS_API_KEY=
HELIUS_GRPC_ENDPOINT=https://laserstream-mainnet-ewr.helius-rpc.com
HELIUS_PARSED_EVENTS_URL=https://mainnet.helius-rpc.com/v1/parsed-events/transactions
```

The API key is optional for the local decoder path but useful for richer parsed transaction classification.

## Optional Jupiter

```text
JUPITER_API_KEY=
JUPITER_QUOTE_URL=https://lite-api.jup.ag/swap/v1/quote
```

Jupiter is used as a **read-only market quote source** for paper position marking.

## Optional providers

The environment template also contains:

```text
SHYFT_API_KEY=
SOLANA_TRACKER_API_KEY=
```

These are reserved for integrations that may be enabled by future ingestion/provider adapters.

---

# Important strategy settings

### Cluster detection

```text
MIN_WARM_WALLETS=3
CLUSTER_WINDOW_SECONDS=30
```

### Signal threshold

```text
SIGNAL_THRESHOLD=30
```

### Paper execution

```text
PAPER_NOTIONAL_SOL=1
PAPER_LIQUIDITY_SOL=100
PAPER_VOLATILITY_BPS=100
PAPER_NETWORK_DELAY_MS=100
```

### Runtime monitoring

```text
POSITION_MONITOR_INTERVAL_SEC=2
SOCIAL_CONFIRMATION_INTERVAL_SEC=15
SOCIAL_CONFIRMATION_BATCH=100
WALLET_FEATURE_REFRESH_INTERVAL_SEC=60
```

### Safety

Keep these values exactly as shown for the intended runtime:

```text
PAPER_TRADING=true
LIVE_EXECUTION=false
```

---

# Adding wallets to track

Wallets are stored in:

```text
tracked_wallets
```

At minimum, a tracked wallet should have:

- a valid Solana address;
- `network='mainnet-beta'`;
- `is_tracked=true`.

Example SQL:

```sql
INSERT INTO tracked_wallets (
    wallet_address,
    network,
    label,
    is_tracked
)
VALUES (
    'YOUR_SOLANA_WALLET_ADDRESS',
    'mainnet-beta',
    'wallet-1',
    TRUE
)
ON CONFLICT (wallet_address)
DO UPDATE SET
    network = EXCLUDED.network,
    label = EXCLUDED.label,
    is_tracked = EXCLUDED.is_tracked;
```

Only add wallets you are authorized to monitor.

---

# Running the live paper engine

Once PostgreSQL, the schema, migrations, and environment are ready:

```bash
python scripts/run_live_engine.py
```

The process should be treated as a long-running worker.

Typical log activity includes:

- WebSocket connection/reconnection;
- transaction recovery;
- transaction decoding;
- buy observations;
- cluster detection;
- signal scoring;
- paper entries;
- social confirmations;
- paper position exits.

The engine is designed to reconnect after stream errors.

---

# Running individual components

## Mainnet wallet stream

```bash
python scripts/run_mainnet_stream.py
```

Use this when you want to observe the ingestion layer separately from the full supervisor.

## Refresh wallet features

```bash
python scripts/refresh_wallet_features.py
```

## Run clustering workflow

```bash
python scripts/run_clustering.py
```

## First-funder analysis

```bash
python scripts/run_first_funder.py
```

## Social WebSocket

```bash
python scripts/run_social_websocket.py
```

## Social co-occurrence

```bash
python scripts/run_social_cooccurrence.py
```

## Local shadow simulation

```bash
python scripts/run_shadow.py
```

## On-chain shadow tooling

```bash
python scripts/run_onchain_shadow.py
```

## Monte Carlo

```bash
python scripts/run_monte_carlo.py
```

## Replay JSONL

```bash
python scripts/replay_jsonl.py
```

## Phase-5 reporting

```bash
python scripts/report_phase5.py
```

---

# Testing

The repository contains unit tests covering major areas including:

- clustering;
- DEX decoding;
- event bus;
- execution lifecycle;
- first-funder analysis;
- 48-hour simulation;
- Monte Carlo;
- on-chain shadow simulation;
- Orca shadow construction;
- reporting;
- replay;
- scoring;
- local shadow simulation;
- social co-occurrence;
- social WebSocket handling.

Run the test suite with:

```bash
pytest
```

For a focused run:

```bash
pytest tests/unit/test_dex_decoder.py
```

**Do not interpret a passing unit suite as proof that the live mainnet pipeline is production-ready.** Live RPC behaviour, provider limits, transaction formats, database state, and external service availability require separate integration/operational validation.

---

# Operational considerations

## RPC reliability

The default public Solana RPC is useful for development but should not be assumed to provide production-grade throughput or latency.

For sustained observation:

- use a dedicated RPC provider;
- monitor rate limits;
- configure appropriate timeouts;
- keep WebSocket and HTTP/RPC endpoints available;
- monitor reconnect frequency.

## Database

PostgreSQL is part of the runtime, not merely a reporting database.

It stores:

- checkpoints;
- observed transactions;
- normalized trade evidence;
- wallet features;
- social observations;
- signals;
- paper positions;
- execution events;
- replay events.

Back up the database before major schema changes.

## Monitoring

The project contains latency instrumentation and structured runtime logging. For a production deployment, these should eventually feed a centralized monitoring system with:

- process health;
- RPC health;
- database health;
- event throughput;
- reconnect rate;
- signal rate;
- paper-entry rate;
- paper-exit rate;
- exception rate;
- latency distributions.

---

# Known limitations

This section intentionally documents what the current repository **does not** claim to solve.

### 1. No real-money execution

There is no supported live trading path.

### 2. Local DEX decoding is conservative

The local decoder is not a universal Solana swap decoder. It focuses on strong evidence and configured program IDs.

### 3. Venue-specific adapters are limited

Additional DEX/router-specific instruction parsers can be added as the monitored venue set expands.

### 4. Public RPC may be insufficient for sustained production traffic

A dedicated provider is recommended for long-running observation.

### 5. Historical backtesting depends on available datasets

Replay quality is limited by the completeness and quality of the recorded event data.

### 6. Social intelligence depends on configured sources

No social provider automatically guarantees complete coverage of X, Telegram, or other platforms.

### 7. Paper results are not live performance

Simulated fills, slippage, latency, liquidity, and quote availability are models. They are not evidence that a future real transaction would receive the same execution.

### 8. Mainnet observation is not the same as production readiness

Before treating the engine as an operational system, validate:

- database migrations;
- RPC capacity;
- reconnect behaviour;
- duplicate handling;
- transaction decoder accuracy;
- token decimal handling;
- social ingestion;
- paper lifecycle correctness;
- alerting;
- backups;
- resource consumption.

---

# Development principles

## Safety first

Observation and simulation must remain isolated from signing/broadcasting.

## Evidence over heuristics

A signal should be supported by multiple observable facts whenever possible:

- wallet history;
- timing;
- clustering;
- funding;
- DEX evidence;
- social confirmation;
- market conditions.

## Durable state

Important observations should survive process restarts.

## Idempotency

Reconnects and historical recovery must not create duplicate trade observations or paper entries.

## Explainability

Signal scores should retain their component breakdown rather than only storing a final number.

## Reproducibility

Simulation and replay workflows should be deterministic where practical and should retain the assumptions used to produce results.

## Mainnet realism without financial risk

The engine should observe **real mainnet conditions** while keeping the execution layer entirely simulated.

---

# Current system status

The repository has progressed from an initial simulation backend into a mainnet observation and paper-trading engine with:

- mainnet wallet streaming;
- transaction recovery and deduplication;
- DEX-aware decoding;
- wallet clustering;
- funding/ancestry analysis;
- social confirmation;
- wallet feature extraction;
- signal scoring;
- dynamic paper slippage;
- paper position lifecycle;
- Jupiter-based read-only marking;
- shadow simulation;
- replay;
- Monte Carlo analysis;
- latency instrumentation;
- PostgreSQL persistence.

The next level of engineering should focus on **operational hardening, broader venue-specific decoding, richer market data, stronger historical datasets, integration testing, and production observability** rather than adding a real-money execution path to this repository.

---

## License

Add the project's intended license here before public distribution if one has not yet been selected.

## Repository

**Solana Insider Tracking & Proactive Execution System**

`nebulyn05/solana-insider-engine`

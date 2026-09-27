from dataclasses import dataclass
import os

from dotenv import load_dotenv

load_dotenv()

MAINNET_GENESIS_HASH = "5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp"


@dataclass(frozen=True)
class Settings:
    app_env: str
    log_level: str
    database_url: str
    solana_network: str
    solana_rpc_url: str
    solana_ws_url: str
    helius_api_key: str | None
    helius_grpc_endpoint: str | None
    shyft_api_key: str | None
    solana_tracker_api_key: str | None
    paper_trading: bool
    live_execution: bool


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Required environment variable is not set: {name}")
    return value


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


_network = os.getenv("SOLANA_NETWORK", "mainnet-beta")
if _network != "mainnet-beta":
    raise RuntimeError("This engine is configured for Solana mainnet-beta only")

_paper_trading = _bool("PAPER_TRADING", True)
_live_execution = _bool("LIVE_EXECUTION", False)
if not _paper_trading or _live_execution:
    raise RuntimeError("Safety boundary requires PAPER_TRADING=true and LIVE_EXECUTION=false")


settings = Settings(
    app_env=os.getenv("APP_ENV", "production"),
    log_level=os.getenv("LOG_LEVEL", "INFO"),
    database_url=_required("DATABASE_URL"),
    solana_network=_network,
    solana_rpc_url=os.getenv("SOLANA_RPC_URL", "https://api.mainnet.solana.com"),
    solana_ws_url=os.getenv("SOLANA_WS_URL", "wss://api.mainnet.solana.com"),
    helius_api_key=os.getenv("HELIUS_API_KEY") or None,
    helius_grpc_endpoint=os.getenv(
        "HELIUS_GRPC_ENDPOINT",
        "https://laserstream-mainnet-ewr.helius-rpc.com",
    ) or None,
    shyft_api_key=os.getenv("SHYFT_API_KEY") or None,
    solana_tracker_api_key=os.getenv("SOLANA_TRACKER_API_KEY") or None,
    paper_trading=_paper_trading,
    live_execution=_live_execution,
)

from dataclasses import dataclass
import os

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    app_env: str
    log_level: str
    database_url: str
    solana_rpc_url: str
    solana_ws_url: str
    helius_api_key: str | None
    helius_grpc_endpoint: str | None
    shyft_api_key: str | None
    solana_tracker_api_key: str | None
    helius_cex_wallets: str | None


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Required environment variable is not set: {name}")
    return value


settings = Settings(
    app_env=os.getenv("APP_ENV", "development"),
    log_level=os.getenv("LOG_LEVEL", "INFO"),
    database_url=_required("DATABASE_URL"),
    solana_rpc_url=os.getenv("SOLANA_RPC_URL", "https://api.devnet.solana.com"),
    solana_ws_url=os.getenv("SOLANA_WS_URL", "wss://api.devnet.solana.com"),
    helius_api_key=os.getenv("HELIUS_API_KEY") or None,
    helius_grpc_endpoint=os.getenv("HELIUS_GRPC_ENDPOINT") or None,
    shyft_api_key=os.getenv("SHYFT_API_KEY") or None,
    solana_tracker_api_key=os.getenv("SOLANA_TRACKER_API_KEY") or None,
    helius_cex_wallets=os.getenv("HELIUS_CEX_WALLETS") or None,
)

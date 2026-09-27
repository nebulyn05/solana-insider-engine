from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class OrcaShadowBuild:
    protocol: str
    cluster: str
    pool: str
    input_mint: str
    user: str
    amount_base_units: int
    slippage_bps: int
    instruction_count: int
    quote: dict
    transaction_base64: str
    signed: bool
    broadcast: bool


def build_orca_swap_transaction(
    pool: str,
    input_mint: str,
    amount_base_units: int,
    user: str,
    slippage_bps: int = 100,
    rpc_url: str = "https://api.devnet.solana.com",
) -> OrcaShadowBuild:
    """Build an unsigned Orca Whirlpool Devnet swap transaction.

    The TypeScript Orca SDK resolves pool, mint, token-account and tick-array
    state from Devnet and creates the real Whirlpool swap instructions.
    This function only compiles an unsigned wire transaction; it never signs
    or broadcasts it.
    """
    if not pool or not input_mint or not user:
        raise ValueError("pool, input_mint, and user are required")
    if amount_base_units <= 0:
        raise ValueError("amount_base_units must be positive")
    if not 0 <= slippage_bps <= 10_000:
        raise ValueError("slippage_bps must be between 0 and 10000")

    repo_root = Path(__file__).resolve().parents[2]
    command = [
        "npm",
        "run",
        "build:orca-shadow",
        "--",
        "--pool",
        pool,
        "--input-mint",
        input_mint,
        "--amount",
        str(amount_base_units),
        "--user",
        user,
        "--slippage-bps",
        str(slippage_bps),
        "--rpc-url",
        rpc_url,
    ]

    completed = subprocess.run(
        command,
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"Orca swap builder failed: {detail}")

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Orca swap builder returned invalid JSON") from exc

    return OrcaShadowBuild(
        protocol=payload["protocol"],
        cluster=payload["cluster"],
        pool=payload["pool"],
        input_mint=payload["input_mint"],
        user=payload["user"],
        amount_base_units=int(payload["amount_base_units"]),
        slippage_bps=int(payload["slippage_bps"]),
        instruction_count=int(payload["instruction_count"]),
        quote=payload["quote"],
        transaction_base64=payload["transaction_base64"],
        signed=bool(payload["signed"]),
        broadcast=bool(payload["broadcast"]),
    )

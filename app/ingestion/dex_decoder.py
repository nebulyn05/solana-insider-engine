from __future__ import annotations

import json
import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

KNOWN_PROGRAM_NAMES = {
    "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc": "orca",
}

SWAP_LOG_MARKERS = (
    "swap",
    "route",
    "exactinput",
    "exactoutput",
    "swap_v2",
)


@dataclass(frozen=True)
class DexTrade:
    wallet_address: str
    dex_name: str
    program_id: str
    input_mint: str | None
    output_mint: str
    input_amount: Decimal | None
    output_amount: Decimal
    price_sol: Decimal
    confidence: Decimal
    evidence: dict[str, Any]


def configured_programs() -> dict[str, str]:
    value = os.getenv("DEX_PROGRAMS", "")
    programs = dict(KNOWN_PROGRAM_NAMES)
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        if "=" in item:
            program_id, name = item.split("=", 1)
            programs[program_id.strip()] = name.strip().lower()
    return programs


def _amount(item: dict[str, Any]) -> Decimal:
    token = item.get("uiTokenAmount") or {}
    raw = Decimal(str(token.get("amount", "0")))
    decimals = int(token.get("decimals", 0))
    return raw / (Decimal(10) ** decimals)


def _token_deltas(wallet: str, meta: dict[str, Any]) -> tuple[list[tuple[str, Decimal]], list[tuple[str, Decimal]]]:
    def aggregate(items: list[dict[str, Any]]) -> dict[str, Decimal]:
        result: dict[str, Decimal] = {}
        for item in items:
            if item.get("owner") != wallet:
                continue
            mint = item.get("mint")
            if not mint:
                continue
            result[mint] = result.get(mint, Decimal("0")) + _amount(item)
        return result

    pre = aggregate(meta.get("preTokenBalances") or [])
    post = aggregate(meta.get("postTokenBalances") or [])
    received: list[tuple[str, Decimal]] = []
    spent: list[tuple[str, Decimal]] = []
    for mint in set(pre) | set(post):
        delta = post.get(mint, Decimal("0")) - pre.get(mint, Decimal("0"))
        if delta > 0:
            received.append((mint, delta))
        elif delta < 0:
            spent.append((mint, -delta))
    return spent, received


def _program_ids(tx: dict[str, Any]) -> set[str]:
    message = ((tx.get("transaction") or {}).get("message") or {})
    ids: set[str] = set()
    for key in message.get("accountKeys") or []:
        if isinstance(key, dict) and key.get("pubkey"):
            ids.add(key["pubkey"])
    for instruction in message.get("instructions") or []:
        if isinstance(instruction, dict) and instruction.get("programId"):
            ids.add(instruction["programId"])
    for group in (tx.get("meta") or {}).get("innerInstructions") or []:
        for instruction in group.get("instructions") or []:
            if isinstance(instruction, dict) and instruction.get("programId"):
                ids.add(instruction["programId"])
    return ids


def _logs(tx: dict[str, Any]) -> list[str]:
    return [str(x).lower() for x in ((tx.get("meta") or {}).get("logMessages") or [])]


def decode_wallet_swap(
    wallet: str,
    tx: dict[str, Any],
    *,
    signature: str,
) -> list[DexTrade]:
    meta = tx.get("meta") or {}
    if meta.get("err") is not None:
        return []

    programs = configured_programs()
    present = _program_ids(tx)
    matched = [(pid, programs[pid]) for pid in present if pid in programs]
    logs = _logs(tx)
    swap_log = any(any(marker in line for marker in SWAP_LOG_MARKERS) for line in logs)

    pre_sol = None
    post_sol = None
    keys = ((tx.get("transaction") or {}).get("message") or {}).get("accountKeys") or []
    key_strings = [k.get("pubkey") if isinstance(k, dict) else k for k in keys]
    if wallet in key_strings:
        idx = key_strings.index(wallet)
        pre_balances = meta.get("preBalances") or []
        post_balances = meta.get("postBalances") or []
        if idx < len(pre_balances) and idx < len(post_balances):
            pre_sol = Decimal(pre_balances[idx]) / Decimal(1_000_000_000)
            post_sol = Decimal(post_balances[idx]) / Decimal(1_000_000_000)

    if pre_sol is None or post_sol is None or pre_sol <= post_sol:
        return []

    spent, received = _token_deltas(wallet, meta)
    if not received:
        return []

    # A candidate is a trade only when an explicitly configured DEX program
    # participates, or when the transaction carries a swap log marker.
    if not matched and not swap_log:
        return []

    sol_spent = pre_sol - post_sol
    program_id, dex_name = matched[0] if matched else ("unknown", "unknown")
    confidence = Decimal("0.92") if matched else Decimal("0.72")

    results: list[DexTrade] = []
    for output_mint, output_amount in received:
        if output_amount <= 0:
            continue
        input_amount = sol_spent
        price = sol_spent / output_amount
        results.append(
            DexTrade(
                wallet_address=wallet,
                dex_name=dex_name,
                program_id=program_id,
                input_mint="SOL",
                output_mint=output_mint,
                input_amount=input_amount,
                output_amount=output_amount,
                price_sol=price,
                confidence=confidence,
                evidence={
                    "signature": signature,
                    "program_ids": sorted(present & set(programs)),
                    "swap_log_detected": swap_log,
                    "decoder": "mainnet-dex-evidence-v1",
                    "input_asset": "SOL",
                },
            )
        )
    return results


def encode_evidence(value: dict[str, Any]) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)

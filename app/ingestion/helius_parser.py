from __future__ import annotations

import json
import os
import urllib.request
from decimal import Decimal
from typing import Any

from app.ingestion.dex_decoder import DexTrade


def _post(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        body = json.load(response)
    if body.get("error"):
        raise RuntimeError(body["error"])
    return body


def _decimals(tx: dict[str, Any], mint: str) -> int:
    for item in (tx.get("meta") or {}).get("postTokenBalances") or []:
        if item.get("mint") == mint:
            return int((item.get("uiTokenAmount") or {}).get("decimals", 0))
    for item in (tx.get("meta") or {}).get("preTokenBalances") or []:
        if item.get("mint") == mint:
            return int((item.get("uiTokenAmount") or {}).get("decimals", 0))
    return 0


def decode_with_helius(
    wallet: str,
    signature: str,
    tx: dict[str, Any],
) -> list[DexTrade]:
    api_key = os.getenv("HELIUS_API_KEY")
    if not api_key:
        return []

    endpoint = os.getenv(
        "HELIUS_PARSED_EVENTS_URL",
        "https://mainnet.helius-rpc.com/v1/parsed-events/transactions",
    )
    body = _post(
        f"{endpoint}?api-key={api_key}",
        {"transactions": [signature]},
    )
    items = body.get("result") or body.get("transactions") or []
    if isinstance(items, dict):
        items = [items]
    if not items:
        return []

    result = items[0]
    summary = result.get("summary") or {}
    parsed = summary.get("parsedData") or {}
    if str(summary.get("type", "")).lower() != "swap":
        return []

    output_mint = parsed.get("output_mint") or parsed.get("outputMint")
    input_mint = parsed.get("input_mint") or parsed.get("inputMint")
    if not output_mint or not input_mint:
        return []

    input_raw = Decimal(str(parsed.get("in_amount") or parsed.get("input_amount") or "0"))
    output_raw = Decimal(str(parsed.get("actual_out_amount") or parsed.get("out_amount") or "0"))
    if input_raw <= 0 or output_raw <= 0:
        return []

    input_decimals = 9 if input_mint in {
        "So11111111111111111111111111111111111111112",
        "SOL",
    } else _decimals(tx, input_mint)
    output_decimals = _decimals(tx, output_mint)

    input_amount = input_raw / (Decimal(10) ** input_decimals)
    output_amount = output_raw / (Decimal(10) ** output_decimals)
    if input_amount <= 0 or output_amount <= 0:
        return []

    if input_mint not in {
        "So11111111111111111111111111111111111111112",
        "SOL",
    }:
        return []

    protocol = str(parsed.get("protocol") or "helius-decoded").lower()
    description = str(summary.get("description") or "")
    return [
        DexTrade(
            wallet_address=wallet,
            dex_name=protocol,
            program_id="helius-parsed",
            input_mint="SOL",
            output_mint=output_mint,
            input_amount=input_amount,
            output_amount=output_amount,
            price_sol=input_amount / output_amount,
            confidence=Decimal("0.99"),
            evidence={
                "signature": signature,
                "decoder": "helius-parsed-events-v1",
                "summary_type": summary.get("type"),
                "description": description,
                "protocol": protocol,
                "input_mint": input_mint,
                "output_mint": output_mint,
            },
        )
    ]

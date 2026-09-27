from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from decimal import Decimal


SOL_MINT = "So11111111111111111111111111111111111111112"
DEFAULT_QUOTE_URL = "https://lite-api.jup.ag/swap/v1/quote"


def quote_sell_to_sol(token_mint: str, raw_amount: int) -> Decimal | None:
    if not token_mint or raw_amount <= 0:
        return None

    base = os.getenv("JUPITER_QUOTE_URL", DEFAULT_QUOTE_URL)
    params = urllib.parse.urlencode({
        "inputMint": token_mint,
        "outputMint": SOL_MINT,
        "amount": str(raw_amount),
        "slippageBps": "50",
        "instructionVersion": "V2",
    })
    request = urllib.request.Request(
        f"{base}?{params}",
        headers={"Accept": "application/json"},
        method="GET",
    )
    api_key = os.getenv("JUPITER_API_KEY")
    if api_key:
        request.add_header("x-api-key", api_key)

    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            body = json.load(response)
        out_amount = body.get("outAmount")
        if out_amount is None:
            return None
        return Decimal(str(out_amount)) / Decimal(1_000_000_000)
    except Exception:
        return None

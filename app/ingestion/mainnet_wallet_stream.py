from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.request
from datetime import datetime, timezone
from typing import Any

import websockets

from app.database.connection import get_connection
from app.ingestion.dex_decoder import DexTrade, decode_wallet_swap
from app.ingestion.helius_parser import decode_with_helius
from app.events.bus import EngineEvent
from app.runtime.pipeline import LivePaperPipeline
from app.intelligence.sell_distribution import detect_sell, persist_sell_observations

LOGGER = logging.getLogger("mainnet.wallet_stream")
MAINNET_GENESIS_HASH = "5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp"
STREAM_NAME = "mainnet-wallets-v3"


def _rpc(url: str, method: str, params: list[Any]) -> dict[str, Any]:
    payload = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params,
    }).encode()
    request = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        body = json.load(response)
    if body.get("error"):
        raise RuntimeError(body["error"])
    return body


def _wallets() -> list[str]:
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """SELECT wallet_address FROM tracked_wallets
               WHERE network='mainnet-beta' AND is_tracked=TRUE
               ORDER BY wallet_address"""
        )
        return [r[0] for r in cursor.fetchall()]


def _verify_mainnet(rpc_url: str) -> None:
    result = _rpc(rpc_url, "getGenesisHash", [])["result"]
    if result != MAINNET_GENESIS_HASH:
        raise RuntimeError(f"not mainnet: genesis={result}")


def _checkpoint(wallet: str) -> tuple[int | None, str | None]:
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            "SELECT last_slot,last_signature FROM stream_checkpoints WHERE stream_name=%s",
            (f"{STREAM_NAME}:{wallet}",),
        )
        row = cursor.fetchone()
        return (row[0], row[1]) if row else (None, None)


def _save_checkpoint(wallet: str, slot: int | None, signature: str | None) -> None:
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """INSERT INTO stream_checkpoints(stream_name,last_slot,last_signature,updated_at)
               VALUES(%s,%s,%s,NOW())
               ON CONFLICT(stream_name) DO UPDATE
               SET last_slot=EXCLUDED.last_slot,
                   last_signature=EXCLUDED.last_signature,
                   updated_at=NOW()""",
            (f"{STREAM_NAME}:{wallet}", slot, signature),
        )
        conn.commit()


def _claim_transaction(
    signature: str,
    slot: int | None,
    block_time: int | None,
    wallet: str,
    tx: dict[str, Any],
) -> bool:
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """INSERT INTO observed_transactions
               (signature,slot,block_time,wallet_address,raw)
               VALUES(%s,%s,%s,%s,%s::jsonb)
               ON CONFLICT(signature) DO NOTHING
               RETURNING signature""",
            (
                signature, slot,
                datetime.fromtimestamp(block_time, tz=timezone.utc) if block_time else None,
                wallet, json.dumps(tx),
            ),
        )
        inserted = cursor.fetchone()
        if inserted:
            conn.commit()
            return True

        # A single Solana transaction can touch multiple tracked wallets.
        # Permit each wallet to be processed while keeping signature-level
        # transaction storage deduplicated.
        cursor.execute(
            "SELECT wallet_address FROM observed_transactions WHERE signature=%s",
            (signature,),
        )
        existing = cursor.fetchone()
        conn.commit()
        return existing is not None and existing[0] != wallet


def _persist_dex_observation(trade: DexTrade, signature: str, tx: dict[str, Any]) -> None:
    block_time = tx.get("blockTime")
    observed = (
        datetime.fromtimestamp(block_time, tz=timezone.utc)
        if block_time else datetime.now(timezone.utc)
    )
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """INSERT INTO dex_trade_observations
               (transaction_signature,wallet_address,dex_name,program_id,
                side,input_mint,output_mint,input_amount,output_amount,
                price_sol,confidence,evidence,observed_at)
               VALUES(%s,%s,%s,%s,'BUY',%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
               ON CONFLICT(transaction_signature,wallet_address,dex_name,output_mint)
               DO UPDATE SET confidence=EXCLUDED.confidence,
                             evidence=EXCLUDED.evidence""",
            (
                signature, trade.wallet_address, trade.dex_name, trade.program_id,
                trade.input_mint, trade.output_mint, trade.input_amount,
                trade.output_amount, trade.price_sol, trade.confidence,
                json.dumps(trade.evidence), observed,
            ),
        )
        cursor.execute(
            """INSERT INTO token_metadata(mint_address,network)
               VALUES(%s,'mainnet-beta')
               ON CONFLICT(mint_address) DO UPDATE SET last_updated_at=NOW()""",
            (trade.output_mint,),
        )
        cursor.execute(
            """UPDATE tracked_wallets
               SET last_seen_at=%s,updated_at=NOW()
               WHERE wallet_address=%s AND network='mainnet-beta'""",
            (observed, trade.wallet_address),
        )
        conn.commit()


def _record_buy(trade: DexTrade, signature: str, observed: datetime) -> None:
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """INSERT INTO token_buy_events
               (wallet_address,token_mint,transaction_signature,
                observed_at,executed_price,dex_name,dex_program_id,
                detection_confidence,detection_evidence)
               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
               ON CONFLICT(transaction_signature) DO UPDATE
               SET dex_name=EXCLUDED.dex_name,
                   dex_program_id=EXCLUDED.dex_program_id,
                   detection_confidence=EXCLUDED.detection_confidence,
                   detection_evidence=EXCLUDED.detection_evidence""",
            (
                trade.wallet_address, trade.output_mint, signature, observed,
                trade.price_sol, trade.dex_name, trade.program_id,
                trade.confidence, json.dumps(trade.evidence),
            ),
        )
        conn.commit()


def _decode_trades(wallet: str, signature: str, tx: dict[str, Any]) -> list[DexTrade]:
    # Helius Parsed Events supplies IDL-backed instruction decoding when an
    # API key is configured. The local decoder remains the fallback.
    try:
        parsed = decode_with_helius(wallet, signature, tx)
        if parsed:
            return parsed
    except Exception:
        LOGGER.exception("helius parser failed; using local decoder")
    return decode_wallet_swap(wallet, tx, signature=signature)


def _process_transaction(
    rpc_url: str,
    wallet: str,
    signature: str,
    pipeline: LivePaperPipeline,
    loop: asyncio.AbstractEventLoop,
) -> None:
    tx = _rpc(
        rpc_url,
        "getTransaction",
        [
            signature,
            {
                "commitment": "confirmed",
                "maxSupportedTransactionVersion": 0,
                "encoding": "jsonParsed",
            },
        ],
    ).get("result")
    if not tx:
        return

    if not _claim_transaction(signature, tx.get("slot"), tx.get("blockTime"), wallet, tx):
        return

    sell_observations = detect_sell(wallet, tx, signature)
    if sell_observations:
        count = persist_sell_observations(sell_observations)
        LOGGER.info("SELL_OBSERVED wallet=%s signature=%s count=%s", wallet, signature, count)

    trades = _decode_trades(wallet, signature, tx)
    for trade in trades:
        _persist_dex_observation(trade, signature, tx)
        observed = (
            datetime.fromtimestamp(tx["blockTime"], tz=timezone.utc)
            if tx.get("blockTime")
            else datetime.now(timezone.utc)
        )
        _record_buy(trade, signature, observed)
        loop.create_task(
            pipeline.handle(
                EngineEvent(
                    event_type="BUY_OBSERVED",
                    occurred_at=observed,
                    payload={
                        "wallet_address": wallet,
                        "token_mint": trade.output_mint,
                        "price_sol": str(trade.price_sol),
                        "signature": signature,
                        "dex_name": trade.dex_name,
                        "confidence": str(trade.confidence),
                    },
                )
            )
        )
        LOGGER.info(
            "DEX_BUY wallet=%s mint=%s dex=%s price_sol=%s signature=%s confidence=%s",
            wallet, trade.output_mint, trade.dex_name, trade.price_sol,
            signature, trade.confidence,
        )


def _recover_wallet(
    rpc_url: str,
    wallet: str,
    pipeline: LivePaperPipeline,
    loop: asyncio.AbstractEventLoop,
) -> None:
    _, last_signature = _checkpoint(wallet)
    signatures = _rpc(
        rpc_url,
        "getSignaturesForAddress",
        [wallet, {"limit": 1000, "commitment": "confirmed"}],
    ).get("result") or []

    pending = []
    for item in signatures:
        signature = item.get("signature")
        if not signature:
            continue
        if signature == last_signature:
            break
        if item.get("err") is None:
            pending.append((item.get("slot"), signature))

    for slot, signature in reversed(pending):
        _process_transaction(rpc_url, wallet, signature, pipeline, loop)
        _save_checkpoint(wallet, slot, signature)


async def run_forever() -> None:
    rpc_url = os.getenv("SOLANA_RPC_URL", "https://api.mainnet.solana.com")
    ws_url = os.getenv("SOLANA_WS_URL", "wss://api.mainnet.solana.com")
    if os.getenv("SOLANA_NETWORK", "mainnet-beta") != "mainnet-beta":
        raise RuntimeError("SOLANA_NETWORK must be mainnet-beta")
    _verify_mainnet(rpc_url)

    pipeline = LivePaperPipeline()
    loop = asyncio.get_running_loop()

    while True:
        wallets = _wallets()
        if not wallets:
            raise RuntimeError("No tracked mainnet wallets configured")

        try:
            for wallet in wallets:
                await asyncio.to_thread(_recover_wallet, rpc_url, wallet, pipeline, loop)

            async with websockets.connect(
                ws_url, ping_interval=20, ping_timeout=20, max_size=8_000_000
            ) as ws:
                subscription_wallet: dict[int, str] = {}
                request_wallet: dict[int, str] = {}
                request_id = 1
                for wallet in wallets:
                    request_wallet[request_id] = wallet
                    await ws.send(json.dumps({
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "method": "logsSubscribe",
                        "params": [{"mentions": [wallet]}, {"commitment": "confirmed"}],
                    }))
                    request_id += 1

                while True:
                    message = json.loads(await ws.recv())
                    if message.get("result") is not None and message.get("id") in request_wallet:
                        subscription_wallet[int(message["result"])] = request_wallet[int(message["id"])]
                        continue

                    if message.get("method") != "logsNotification":
                        continue

                    params = message.get("params") or {}
                    subscription = params.get("subscription")
                    wallet = subscription_wallet.get(subscription)
                    value = (params.get("result") or {}).get("value") or {}
                    signature = value.get("signature")
                    if not wallet or not signature or value.get("err") is not None:
                        continue

                    _process_transaction(rpc_url, wallet, signature, pipeline, loop)
                    slot = (params.get("result") or {}).get("context", {}).get("slot")
                    _save_checkpoint(wallet, slot, signature)

        except asyncio.CancelledError:
            raise
        except Exception:
            LOGGER.exception("mainnet stream disconnected; reconnecting")
            await asyncio.sleep(2)


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(run_forever())


if __name__ == "__main__":
    main()

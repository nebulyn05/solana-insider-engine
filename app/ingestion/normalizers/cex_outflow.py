from __future__ import annotations

import asyncio
import json
import urllib.request
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID, uuid4

from app.config.settings import settings
from app.database.connection import get_connection
from app.ingestion.helius.proto import geyser_pb2

LAMPORTS_PER_SOL = Decimal(1_000_000_000)


@dataclass(frozen=True)
class CexOutflow:
    signature: str
    slot: int
    source_wallet: str
    destination_wallet: str
    amount_sol: Decimal
    lineage_id: UUID
    fresh_on_chain: bool = False


def _b58(data: bytes) -> str:
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    if not data:
        return ""
    number = int.from_bytes(data, "big")
    encoded: list[str] = []
    while number:
        number, remainder = divmod(number, 58)
        encoded.append(alphabet[remainder])
    leading_zeroes = len(data) - len(data.lstrip(b"\x00"))
    return "1" * leading_zeroes + "".join(reversed(encoded))


def _fresh_from_rpc(wallet: str) -> bool:
    payload = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getSignaturesForAddress",
        "params": [wallet, {"limit": 1}],
    }).encode()
    request = urllib.request.Request(
        settings.solana_rpc_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        body = json.load(response)
    if body.get("error"):
        raise RuntimeError(f"Solana RPC error for {wallet}: {body['error']}")
    return not body.get("result")


def _source_and_deltas(
    info: geyser_pb2.SubscribeUpdateTransactionInfo,
    cex_wallets: set[str],
) -> tuple[str | None, list[tuple[str, int]]]:
    message = info.transaction.message
    keys = [_b58(key) for key in message.account_keys]
    meta = info.meta
    if not keys or len(meta.pre_balances) != len(keys) or len(meta.post_balances) != len(keys):
        return None, []
    source = next((wallet for wallet in cex_wallets if wallet in keys), None)
    if source is None:
        return None, []
    deltas = [
        (key, int(post) - int(pre))
        for key, pre, post in zip(keys, meta.pre_balances, meta.post_balances)
        if int(post) > int(pre) and key != source
    ]
    return source, deltas


def normalize_cex_outflow(
    update: geyser_pb2.SubscribeUpdate,
    cex_wallets: set[str],
) -> list[CexOutflow]:
    if not update.HasField("transaction"):
        return []
    info = update.transaction.transaction
    if info.is_vote or not info.signature or not info.transaction.message.account_keys:
        return []
    source, deltas = _source_and_deltas(info, cex_wallets)
    if source is None:
        return []

    signature = _b58(info.signature)
    return [
        CexOutflow(
            signature=signature,
            slot=update.transaction.slot,
            source_wallet=source,
            destination_wallet=destination,
            amount_sol=Decimal(lamport_delta) / LAMPORTS_PER_SOL,
            lineage_id=uuid4(),
        )
        for destination, lamport_delta in deltas
    ]


async def enrich_freshness(events: list[CexOutflow]) -> list[CexOutflow]:
    async def check(event: CexOutflow) -> CexOutflow | None:
        fresh = await asyncio.to_thread(_fresh_from_rpc, event.destination_wallet)
        return CexOutflow(**{**event.__dict__, "fresh_on_chain": True}) if fresh else None

    checked = await asyncio.gather(*(check(event) for event in events))
    return [event for event in checked if event is not None]


def persist_outflows(events: list[CexOutflow]) -> int:
    if not events:
        return 0
    with get_connection() as conn, conn.cursor() as cursor:
        count = 0
        for event in events:
            cursor.execute(
                """INSERT INTO tracked_wallets
                   (wallet_address, network, label, cex_label, is_cex, is_tracked)
                   VALUES (%s, 'devnet', 'CEX hot wallet', %s, TRUE, TRUE)
                   ON CONFLICT (wallet_address) DO UPDATE
                   SET cex_label = EXCLUDED.cex_label,
                       is_cex = TRUE,
                       updated_at = NOW()""",
                (event.source_wallet, "configured-cex"),
            )
            cursor.execute(
                """INSERT INTO tracked_wallets
                   (wallet_address, network, label, is_tracked)
                   VALUES (%s, 'devnet', 'fresh CEX-funded address', TRUE)
                   ON CONFLICT (wallet_address) DO NOTHING
                   RETURNING id""",
                (event.destination_wallet,),
            )
            row = cursor.fetchone()
            if row is None:
                cursor.execute(
                    "SELECT id FROM tracked_wallets WHERE wallet_address = %s",
                    (event.destination_wallet,),
                )
            destination_id = cursor.fetchone()[0]
            cursor.execute(
                "SELECT id FROM tracked_wallets WHERE wallet_address = %s",
                (event.source_wallet,),
            )
            source_id = cursor.fetchone()[0]
            cursor.execute(
                """INSERT INTO funding_ledger
                   (transaction_signature, slot, source_wallet_id, destination_wallet_id,
                    amount, hop_depth, lineage_id, metadata)
                   VALUES (%s, %s, %s, %s, %s, 0, %s, %s::jsonb)
                   ON CONFLICT (transaction_signature) DO NOTHING""",
                (
                    event.signature,
                    event.slot,
                    source_id,
                    destination_id,
                    event.amount_sol,
                    str(event.lineage_id),
                    json.dumps({
                        "detector": "cex_outflow_scanner",
                        "fresh_on_chain": event.fresh_on_chain,
                    }),
                ),
            )
            count += cursor.rowcount
        conn.commit()
        return count

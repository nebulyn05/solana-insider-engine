from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from app.config.settings import settings
from app.database.connection import get_connection

LAMPORTS_PER_SOL = Decimal(1_000_000_000)
MAX_ANCESTRY_HOPS = 5


@dataclass(frozen=True)
class FundingEdge:
    signature: str
    slot: int
    source_wallet: str
    destination_wallet: str
    amount_sol: Decimal


@dataclass(frozen=True)
class RootClassification:
    wallet: str
    flagged: bool
    reason: str | None
    label: str | None


@dataclass(frozen=True)
class AncestryResult:
    wallet: str
    lineage_id: UUID
    edges: tuple[FundingEdge, ...]
    root_wallet: str
    root_classification: RootClassification
    max_hops_reached: bool


def _rpc(method: str, params: list[Any]) -> Any:
    payload = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params,
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
        raise RuntimeError(f"Solana RPC error for {method}: {body['error']}")
    return body.get("result")


def _find_source_from_balances(
    transaction: dict[str, Any],
    destination_wallet: str,
) -> tuple[str, Decimal] | None:
    meta = transaction.get("meta") or {}
    message = (transaction.get("transaction") or {}).get("message") or {}
    keys = message.get("accountKeys") or []
    pre = meta.get("preBalances") or []
    post = meta.get("postBalances") or []

    if len(keys) != len(pre) or len(keys) != len(post):
        return None

    normalized_keys = [
        key if isinstance(key, str) else key.get("pubkey")
        for key in keys
    ]
    if destination_wallet not in normalized_keys:
        return None

    destination_index = normalized_keys.index(destination_wallet)
    destination_delta = int(post[destination_index]) - int(pre[destination_index])
    if destination_delta <= 0:
        return None

    candidates: list[tuple[int, str]] = []
    for index, wallet in enumerate(normalized_keys):
        if not wallet or wallet == destination_wallet:
            continue
        delta = int(post[index]) - int(pre[index])
        if delta < 0:
            candidates.append((-delta, wallet))

    if not candidates:
        return None

    candidates.sort(reverse=True)
    source_delta, source_wallet = candidates[0]
    amount = min(destination_delta, source_delta)
    return source_wallet, Decimal(amount) / LAMPORTS_PER_SOL


def _find_inbound_edge(
    destination_wallet: str,
    current_slot: int | None = None,
) -> FundingEdge | None:
    signatures = _rpc(
        "getSignaturesForAddress",
        [destination_wallet, {"limit": 20}],
    ) or []

    for item in signatures:
        if item.get("err") is not None:
            continue
        signature = item.get("signature")
        slot = int(item.get("slot", 0))
        if not signature:
            continue
        if current_slot is not None and slot >= current_slot:
            continue

        transaction = _rpc(
            "getTransaction",
            [
                signature,
                {
                    "encoding": "jsonParsed",
                    "commitment": "confirmed",
                    "maxSupportedTransactionVersion": 0,
                },
            ],
        )
        if not transaction:
            continue

        source = _find_source_from_balances(transaction, destination_wallet)
        if source is None:
            continue

        source_wallet, amount_sol = source
        return FundingEdge(
            signature=signature,
            slot=slot,
            source_wallet=source_wallet,
            destination_wallet=destination_wallet,
            amount_sol=amount_sol,
        )

    return None


def _classify_root(wallet: str) -> RootClassification:
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """SELECT is_cex, cex_label, multi_hop_label, label, metadata
               FROM tracked_wallets
               WHERE wallet_address = %s""",
            (wallet,),
        )
        row = cursor.fetchone()

    if row is None:
        return RootClassification(wallet, False, None, None)

    is_cex, cex_label, multi_hop_label, label, metadata = row
    metadata = metadata or {}
    bridge_label = metadata.get("bridge_label")
    if is_cex or cex_label:
        return RootClassification(
            wallet, True, "cex", cex_label or label or "CEX wallet"
        )
    if bridge_label:
        return RootClassification(wallet, True, "bridge", str(bridge_label))
    if multi_hop_label:
        return RootClassification(
            wallet, True, "multi_hop_cluster", multi_hop_label
        )
    if label and "bridge" in label.lower():
        return RootClassification(wallet, True, "bridge", label)

    return RootClassification(wallet, False, None, label)


def trace_ancestry(
    wallet: str,
    max_hops: int = MAX_ANCESTRY_HOPS,
) -> AncestryResult:
    if not wallet:
        raise ValueError("wallet is required")
    if not 1 <= max_hops <= MAX_ANCESTRY_HOPS:
        raise ValueError(f"max_hops must be between 1 and {MAX_ANCESTRY_HOPS}")

    lineage_id = uuid4()
    edges: list[FundingEdge] = []
    current_wallet = wallet
    current_slot: int | None = None
    visited = {wallet}

    for _ in range(max_hops):
        edge = _find_inbound_edge(current_wallet, current_slot)
        if edge is None or edge.source_wallet in visited:
            break

        edges.append(edge)
        visited.add(edge.source_wallet)
        current_wallet = edge.source_wallet
        current_slot = edge.slot

        classification = _classify_root(current_wallet)
        if classification.flagged:
            return AncestryResult(
                wallet=wallet,
                lineage_id=lineage_id,
                edges=tuple(edges),
                root_wallet=current_wallet,
                root_classification=classification,
                max_hops_reached=False,
            )

    classification = _classify_root(current_wallet)
    return AncestryResult(
        wallet=wallet,
        lineage_id=lineage_id,
        edges=tuple(edges),
        root_wallet=current_wallet,
        root_classification=classification,
        max_hops_reached=len(edges) >= max_hops,
    )


def persist_ancestry(result: AncestryResult) -> int:
    if not result.edges:
        return 0

    with get_connection() as conn, conn.cursor() as cursor:
        inserted = 0

        for depth, edge in enumerate(reversed(result.edges), start=0):
            cursor.execute(
                """INSERT INTO tracked_wallets
                   (wallet_address, network, label, is_tracked)
                   VALUES (%s, 'devnet', 'ancestry-discovered wallet', TRUE)
                   ON CONFLICT (wallet_address) DO NOTHING""",
                (edge.source_wallet,),
            )
            cursor.execute(
                """INSERT INTO tracked_wallets
                   (wallet_address, network, label, is_tracked)
                   VALUES (%s, 'devnet', 'ancestry destination wallet', TRUE)
                   ON CONFLICT (wallet_address) DO NOTHING""",
                (edge.destination_wallet,),
            )

            cursor.execute(
                "SELECT id FROM tracked_wallets WHERE wallet_address = %s",
                (edge.source_wallet,),
            )
            source_id = cursor.fetchone()[0]
            cursor.execute(
                "SELECT id FROM tracked_wallets WHERE wallet_address = %s",
                (edge.destination_wallet,),
            )
            destination_id = cursor.fetchone()[0]

            cursor.execute(
                """INSERT INTO funding_ledger
                   (transaction_signature, slot, source_wallet_id,
                    destination_wallet_id, amount, hop_depth, lineage_id, metadata)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                   ON CONFLICT (transaction_signature) DO UPDATE
                   SET hop_depth = EXCLUDED.hop_depth,
                       lineage_id = EXCLUDED.lineage_id,
                       metadata = funding_ledger.metadata || EXCLUDED.metadata""",
                (
                    edge.signature,
                    edge.slot,
                    source_id,
                    destination_id,
                    edge.amount_sol,
                    depth,
                    str(result.lineage_id),
                    json.dumps({
                        "detector": "multi_hop_ancestry_engine",
                        "root_wallet": result.root_wallet,
                        "root_flagged": result.root_classification.flagged,
                        "root_reason": result.root_classification.reason,
                        "root_label": result.root_classification.label,
                    }),
                ),
            )
            inserted += cursor.rowcount

        conn.commit()
        return inserted

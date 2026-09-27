from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.config.settings import settings


LAMPORTS_PER_SOL = Decimal("1000000000")


@dataclass(frozen=True)
class TokenBalanceDelta:
    account_index: int
    mint: str
    owner: str | None
    before: Decimal
    after: Decimal
    delta: Decimal


@dataclass(frozen=True)
class AccountState:
    address: str
    lamports: int
    owner: str
    executable: bool
    data: Any


@dataclass(frozen=True)
class OnChainSimulationResult:
    success: bool
    slot: int | None
    error: Any
    logs: tuple[str, ...]
    units_consumed: int | None
    fee_lamports: int | None
    return_data: Any
    pre_balances_lamports: tuple[int, ...]
    post_balances_lamports: tuple[int, ...]
    token_balance_deltas: tuple[TokenBalanceDelta, ...]
    accounts: tuple[AccountState, ...]
    invoked_programs: tuple[str, ...]
    inner_instructions: Any


class SolanaSimulationClient:
    """RPC-only transaction simulator.

    Transactions are supplied as base64-encoded wire transactions. The client
    never signs or broadcasts them. Solana's simulateTransaction RPC executes
    the instructions against the RPC node's simulated bank state and returns
    execution logs and post-simulation state.
    """

    def __init__(self, rpc_url: str | None = None) -> None:
        self.rpc_url = rpc_url or settings.solana_rpc_url

    def simulate(
        self,
        encoded_transaction: str,
        account_addresses: tuple[str, ...] = (),
        *,
        commitment: str = "confirmed",
        replace_recent_blockhash: bool = True,
        inner_instructions: bool = True,
    ) -> OnChainSimulationResult:
        if not encoded_transaction:
            raise ValueError("encoded_transaction is required")

        config: dict[str, Any] = {
            "encoding": "base64",
            "commitment": commitment,
            "replaceRecentBlockhash": replace_recent_blockhash,
            "sigVerify": False,
            "innerInstructions": inner_instructions,
        }
        if account_addresses:
            config["accounts"] = {
                "encoding": "jsonParsed",
                "addresses": list(dict.fromkeys(account_addresses)),
            }

        payload = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "simulateTransaction",
                "params": [encoded_transaction, config],
            }
        ).encode()

        request = urllib.request.Request(
            self.rpc_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(request, timeout=15) as response:
            body = json.load(response)

        if body.get("error"):
            raise RuntimeError(
                f"Solana RPC error for simulateTransaction: {body['error']}"
            )

        result = body.get("result") or {}
        value = result.get("value") or {}

        pre = tuple(int(value.get("preBalances") or ()))
        post = tuple(int(value.get("postBalances") or ()))
        token_deltas = _token_balance_deltas(
            value.get("preTokenBalances") or (),
            value.get("postTokenBalances") or (),
        )

        accounts = tuple(
            _account_state(address, account)
            for address, account in zip(
                account_addresses,
                value.get("accounts") or (),
                strict=False,
            )
            if account is not None
        )

        return OnChainSimulationResult(
            success=value.get("err") is None,
            slot=(result.get("context") or {}).get("slot"),
            error=value.get("err"),
            logs=tuple(value.get("logs") or ()),
            units_consumed=_optional_int(value.get("unitsConsumed")),
            fee_lamports=_optional_int(value.get("fee")),
            return_data=value.get("returnData"),
            pre_balances_lamports=pre,
            post_balances_lamports=post,
            token_balance_deltas=token_deltas,
            accounts=accounts,
            invoked_programs=_invoked_programs(value.get("logs") or ()),
            inner_instructions=value.get("innerInstructions"),
        )


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _token_balance_deltas(
    pre_balances: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    post_balances: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> tuple[TokenBalanceDelta, ...]:
    pre_by_index = {int(item["accountIndex"]): item for item in pre_balances}
    post_by_index = {int(item["accountIndex"]): item for item in post_balances}

    deltas: list[TokenBalanceDelta] = []
    for index in sorted(set(pre_by_index) | set(post_by_index)):
        before_item = pre_by_index.get(index)
        after_item = post_by_index.get(index)
        item = after_item or before_item
        if item is None:
            continue

        before = _token_amount(pre_by_index.get(index))
        after = _token_amount(post_by_index.get(index))
        deltas.append(
            TokenBalanceDelta(
                account_index=index,
                mint=str(item.get("mint", "")),
                owner=(item.get("owner") or None),
                before=before,
                after=after,
                delta=after - before,
            )
        )

    return tuple(deltas)


def _token_amount(item: dict[str, Any] | None) -> Decimal:
    if not item:
        return Decimal(0)
    token_amount = item.get("uiTokenAmount") or {}
    raw = token_amount.get("uiAmountString")
    if raw is not None:
        return Decimal(str(raw))
    raw_amount = token_amount.get("amount")
    decimals = int(token_amount.get("decimals", 0))
    if raw_amount is None:
        return Decimal(0)
    return Decimal(str(raw_amount)) / (Decimal(10) ** decimals)


def _account_state(address: str, account: dict[str, Any]) -> AccountState:
    return AccountState(
        address=address,
        lamports=int(account.get("lamports", 0)),
        owner=str(account.get("owner", "")),
        executable=bool(account.get("executable", False)),
        data=account.get("data"),
    )


def _invoked_programs(logs: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    programs: list[str] = []
    for log in logs:
        if not log.startswith("Program ") or " invoke [" not in log:
            continue
        program = log.removeprefix("Program ").split(" invoke [", 1)[0]
        if program not in programs:
            programs.append(program)
    return tuple(programs)


@dataclass(frozen=True)
class OnChainShadowVerdict:
    buy: OnChainSimulationResult
    sell: OnChainSimulationResult | None
    sellable: bool
    reason: str | None


class OnChainShadowSimulator:
    """Simulates supplied BUY/SELL instructions without broadcasting.

    A combined transaction can contain BUY followed by SELL instructions and
    is the preferred way to test an atomic round trip. When separate BUY and
    SELL transactions are supplied, each simulation starts from the RPC's
    current bank state; the second simulation does not inherit mutations from
    the first.
    """

    def __init__(self, client: SolanaSimulationClient | None = None) -> None:
        self.client = client or SolanaSimulationClient()

    def simulate_buy(
        self,
        encoded_transaction: str,
        account_addresses: tuple[str, ...] = (),
    ) -> OnChainSimulationResult:
        return self.client.simulate(encoded_transaction, account_addresses)

    def simulate_round_trip(
        self,
        buy_transaction: str,
        sell_transaction: str | None = None,
        account_addresses: tuple[str, ...] = (),
    ) -> OnChainShadowVerdict:
        buy = self.client.simulate(buy_transaction, account_addresses)
        if not buy.success:
            return OnChainShadowVerdict(
                buy=buy,
                sell=None,
                sellable=False,
                reason="buy_simulation_failed",
            )

        if sell_transaction is None:
            return OnChainShadowVerdict(
                buy=buy,
                sell=None,
                sellable=False,
                reason="sell_simulation_not_supplied",
            )

        sell = self.client.simulate(sell_transaction, account_addresses)
        if not sell.success:
            return OnChainShadowVerdict(
                buy=buy,
                sell=sell,
                sellable=False,
                reason="sell_simulation_failed",
            )

        return OnChainShadowVerdict(
            buy=buy,
            sell=sell,
            sellable=True,
            reason=None,
        )

    def simulate_atomic_round_trip(
        self,
        encoded_buy_then_sell_transaction: str,
        account_addresses: tuple[str, ...] = (),
    ) -> OnChainShadowVerdict:
        result = self.client.simulate(
            encoded_buy_then_sell_transaction,
            account_addresses,
        )
        return OnChainShadowVerdict(
            buy=result,
            sell=None,
            sellable=result.success,
            reason=None if result.success else "atomic_round_trip_failed",
        )

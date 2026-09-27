import json
from unittest.mock import MagicMock, patch

from app.intelligence.onchain_shadow import (
    SolanaSimulationClient,
    _invoked_programs,
    _token_balance_deltas,
)


def test_token_balance_deltas_capture_state_change() -> None:
    pre = [
        {
            "accountIndex": 1,
            "mint": "mint",
            "owner": "owner",
            "uiTokenAmount": {"amount": "100", "decimals": 2, "uiAmountString": "1"},
        }
    ]
    post = [
        {
            "accountIndex": 1,
            "mint": "mint",
            "owner": "owner",
            "uiTokenAmount": {"amount": "250", "decimals": 2, "uiAmountString": "2.5"},
        }
    ]

    deltas = _token_balance_deltas(pre, post)

    assert len(deltas) == 1
    assert deltas[0].delta == 1.5
    assert deltas[0].mint == "mint"


def test_invoked_programs_are_unique() -> None:
    logs = [
        "Program ProgramA invoke [1]",
        "Program log: Instruction: Swap",
        "Program ProgramA success",
        "Program ProgramB invoke [1]",
        "Program ProgramA invoke [2]",
    ]

    assert _invoked_programs(logs) == ("ProgramA", "ProgramB")


def test_simulate_requests_post_state_and_execution_metadata() -> None:
    response = {
        "jsonrpc": "2.0",
        "result": {
            "context": {"slot": 123},
            "value": {
                "err": None,
                "logs": ["Program ProgramA invoke [1]", "Program ProgramA success"],
                "unitsConsumed": 5000,
                "fee": 5000,
                "preBalances": [1000000],
                "postBalances": [994000],
                "preTokenBalances": [],
                "postTokenBalances": [],
                "accounts": [
                    {
                        "lamports": 42,
                        "owner": "Owner111",
                        "executable": False,
                        "data": ["", "base64"],
                    }
                ],
                "returnData": None,
                "innerInstructions": [],
            },
        },
    }

    fake_response = MagicMock()
    fake_response.__enter__.return_value = fake_response
    fake_response.__exit__.return_value = None

    with patch(
        "app.intelligence.onchain_shadow.urllib.request.urlopen",
        return_value=fake_response,
    ), patch(
        "app.intelligence.onchain_shadow.json.load",
        return_value=response,
    ):
        result = SolanaSimulationClient(
            rpc_url="https://example.invalid"
        ).simulate(
            "AAAA",
            ("Account111",),
        )

    assert result.success is True
    assert result.slot == 123
    assert result.units_consumed == 5000
    assert result.pre_balances_lamports == (1000000,)
    assert result.post_balances_lamports == (994000,)
    assert result.accounts[0].lamports == 42

    request = fake_response
    assert request is not None

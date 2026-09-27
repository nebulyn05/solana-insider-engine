from unittest.mock import patch

from app.intelligence.orca_shadow import build_orca_swap_transaction


def test_orca_builder_parses_unsigned_transaction() -> None:
    payload = (
        '{"protocol":"orca_whirlpool","cluster":"devnet",'
        '"pool":"pool","input_mint":"mint","user":"user",'
        '"amount_base_units":"1000","slippage_bps":100,'
        '"instruction_count":5,"quote":{"tokenEstA":"900"},'
        '"transaction_base64":"AAAA","signed":false,"broadcast":false}'
    )

    completed = type(
        "Completed",
        (),
        {"returncode": 0, "stdout": payload, "stderr": ""},
    )()

    with patch(
        "app.intelligence.orca_shadow.subprocess.run",
        return_value=completed,
    ):
        result = build_orca_swap_transaction(
            pool="pool",
            input_mint="mint",
            amount_base_units=1000,
            user="user",
        )

    assert result.protocol == "orca_whirlpool"
    assert result.cluster == "devnet"
    assert result.amount_base_units == 1000
    assert result.transaction_base64 == "AAAA"
    assert result.signed is False
    assert result.broadcast is False

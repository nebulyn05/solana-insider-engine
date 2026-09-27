from decimal import Decimal

from app.ingestion.dex_decoder import decode_wallet_swap


WALLET = "Wallet1111111111111111111111111111111111111"
MINT = "Mint1111111111111111111111111111111111111111"


def _tx():
    return {
        "slot": 1,
        "blockTime": 1700000000,
        "transaction": {
            "message": {
                "accountKeys": [
                    {"pubkey": WALLET},
                    {"pubkey": "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc"},
                ],
                "instructions": [
                    {
                        "programId": "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc",
                    }
                ],
            }
        },
        "meta": {
            "err": None,
            "preBalances": [10_000_000_000, 0],
            "postBalances": [9_000_000_000, 0],
            "preTokenBalances": [
                {
                    "owner": WALLET,
                    "mint": MINT,
                    "uiTokenAmount": {"amount": "0", "decimals": 6},
                }
            ],
            "postTokenBalances": [
                {
                    "owner": WALLET,
                    "mint": MINT,
                    "uiTokenAmount": {"amount": "1000000", "decimals": 6},
                }
            ],
            "logMessages": ["Program log: swap"],
        },
    }


def test_decodes_configured_orca_swap():
    trades = decode_wallet_swap(WALLET, _tx(), signature="sig")
    assert len(trades) == 1
    assert trades[0].dex_name == "orca"
    assert trades[0].output_mint == MINT
    assert trades[0].input_amount == Decimal("1")
    assert trades[0].output_amount == Decimal("1")
    assert trades[0].price_sol == Decimal("1")


def test_rejects_plain_balance_change_without_dex_evidence():
    tx = _tx()
    tx["transaction"]["message"]["instructions"] = []
    tx["meta"]["logMessages"] = []
    assert decode_wallet_swap(WALLET, tx, signature="sig") == []

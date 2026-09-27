from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import websockets

from app.database.connection import get_connection
from app.intelligence.clustering import record_buy_event

LOGGER = logging.getLogger("mainnet.wallet_stream")
MAINNET_GENESIS_HASH = "5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp"


def _rpc(url: str, method: str, params: list[Any]) -> dict[str, Any]:
    payload=json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params}).encode()
    request=urllib.request.Request(url,data=payload,headers={"Content-Type":"application/json"},method="POST")
    with urllib.request.urlopen(request,timeout=15) as response:
        body=json.load(response)
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


def _verify_mainnet(rpc_url:str)->None:
    result=_rpc(rpc_url,"getGenesisHash",[])["result"]
    if result!=MAINNET_GENESIS_HASH:
        raise RuntimeError(f"not mainnet: genesis={result}")


def _ui_amount(balance:dict[str,Any])->Decimal:
    amount=Decimal(balance["uiTokenAmount"]["amount"])
    decimals=int(balance["uiTokenAmount"]["decimals"])
    return amount/(Decimal(10)**decimals)


def _extract_buy_events(wallet:str, signature:str, tx:dict[str,Any])->list[tuple[str,Decimal,datetime]]:
    meta=tx.get("meta") or {}
    if meta.get("err") is not None:
        return []
    transaction=tx.get("transaction") or {}
    message=transaction.get("message") or {}
    keys=message.get("accountKeys") or []
    key_strings=[k.get("pubkey") if isinstance(k,dict) else k for k in keys]
    if wallet not in key_strings:
        return []

    wallet_index=key_strings.index(wallet)
    pre_balances=meta.get("preBalances") or []
    post_balances=meta.get("postBalances") or []
    if wallet_index>=len(pre_balances) or wallet_index>=len(post_balances):
        return []
    sol_delta=Decimal(post_balances[wallet_index]-pre_balances[wallet_index])/Decimal(1_000_000_000)
    if sol_delta >= 0:
        return []

    def aggregate(items:list[dict[str,Any]])->dict[tuple[str,int],Decimal]:
        out={}
        for item in items:
            if item.get("owner")!=wallet: continue
            mint=item.get("mint")
            if not mint: continue
            key=(mint,int(item["uiTokenAmount"]["decimals"]))
            out[key]=out.get(key,Decimal("0"))+_ui_amount(item)
        return out

    pre=aggregate(meta.get("preTokenBalances") or [])
    post=aggregate(meta.get("postTokenBalances") or [])
    block_time=tx.get("blockTime")
    observed=datetime.fromtimestamp(block_time,tz=timezone.utc) if block_time else datetime.now(timezone.utc)
    events=[]
    for (mint,decimals),after in post.items():
        before=pre.get((mint,decimals),Decimal("0"))
        delta=after-before
        if delta<=0: continue
        price=(-sol_delta)/delta
        events.append((mint,price,observed))
    return events


async def run_forever() -> None:
    rpc_url=os.getenv("SOLANA_RPC_URL","https://api.mainnet.solana.com")
    ws_url=os.getenv("SOLANA_WS_URL","wss://api.mainnet.solana.com")
    if os.getenv("SOLANA_NETWORK","mainnet-beta")!="mainnet-beta":
        raise RuntimeError("SOLANA_NETWORK must be mainnet-beta")
    _verify_mainnet(rpc_url)

    while True:
        wallets=_wallets()
        if not wallets:
            raise RuntimeError("No tracked mainnet wallets configured")
        try:
            async with websockets.connect(ws_url,ping_interval=20,ping_timeout=20,max_size=8_000_000) as ws:
                subscriptions={}
                for wallet in wallets:
                    await ws.send(json.dumps({
                        "jsonrpc":"2.0","id":wallet,
                        "method":"logsSubscribe",
                        "params":[{"mentions":[wallet]},{"commitment":"confirmed"}]
                    }))
                while True:
                    message=json.loads(await ws.recv())
                    if message.get("method")!="logsNotification":
                        continue
                    value=message["params"]["result"]["value"]
                    if value.get("err") is not None:
                        continue
                    signature=value["signature"]
                    wallet_hits=wallets
                    for wallet in wallet_hits:
                        tx=_rpc(rpc_url,"getTransaction",[signature,{"commitment":"confirmed","maxSupportedTransactionVersion":0,"encoding":"jsonParsed"}]).get("result")
                        if not tx: continue
                        for mint,price,observed in _extract_buy_events(wallet,signature,tx):
                            record_buy_event(wallet,mint,signature,observed,price)
                            with get_connection() as conn, conn.cursor() as cursor:
                                cursor.execute("UPDATE tracked_wallets SET last_seen_at=%s,updated_at=NOW() WHERE wallet_address=%s",(observed,wallet))
                                cursor.execute(
                                    """INSERT INTO token_metadata(mint_address,network,decimals)
                                       VALUES(%s,'mainnet-beta',%s)
                                       ON CONFLICT(mint_address) DO UPDATE SET last_updated_at=NOW()""",
                                    (mint,0)
                                )
                                conn.commit()
                            LOGGER.info("BUY_OBSERVED wallet=%s mint=%s price_sol=%s signature=%s",wallet,mint,price,signature)
        except asyncio.CancelledError:
            raise
        except Exception:
            LOGGER.exception("mainnet stream disconnected; reconnecting")
            await asyncio.sleep(2)


def main()->None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL","INFO"),format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(run_forever())


if __name__=="__main__": main()

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4
import urllib.request

from app.database.connection import get_connection
from app.intelligence.clustering import find_spatiotemporal_cluster

LOGGER = logging.getLogger("mainnet.paper_simulation")
MAINNET_GENESIS_HASH = "5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp"


@dataclass(frozen=True)
class SimulationConfig:
    duration_hours: Decimal = Decimal("48")
    poll_seconds: int = 2
    slippage_percent: Decimal = Decimal("4.0")
    notional_sol: Decimal = Decimal("1")

    def validate(self) -> None:
        if self.duration_hours <= 0 or self.poll_seconds < 1:
            raise ValueError("duration_hours and poll_seconds must be positive")
        if not Decimal("3") <= self.slippage_percent <= Decimal("5"):
            raise ValueError("slippage_percent must be between 3 and 5")
        if self.notional_sol <= 0:
            raise ValueError("notional_sol must be positive")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _verify_mainnet(rpc_url: str) -> None:
    payload=json.dumps({"jsonrpc":"2.0","id":1,"method":"getGenesisHash","params":[]}).encode()
    request=urllib.request.Request(rpc_url,data=payload,headers={"Content-Type":"application/json"},method="POST")
    with urllib.request.urlopen(request,timeout=10) as response:
        body=json.load(response)
    if body.get("error") or body.get("result") != MAINNET_GENESIS_HASH:
        raise RuntimeError(f"Mainnet RPC verification failed: {body.get('error') or body.get('result')}")
    LOGGER.info("verified Solana mainnet RPC endpoint: %s",rpc_url)


def _candidate_events(after:datetime):
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """SELECT id,token_mint,observed_at FROM token_buy_events
               WHERE observed_at >= %s ORDER BY observed_at ASC,id ASC""",(after,)
        )
        return [(int(r[0]),r[1],r[2].astimezone(timezone.utc)) for r in cursor.fetchall()]


def _insert_simulated_entry(token_mint,signal_id,requested_price,notional_sol,slippage_percent,signal_created_at):
    slippage_bps=slippage_percent*Decimal("100")
    executed_price=requested_price*(Decimal("1")+slippage_percent/Decimal("100"))
    quantity=notional_sol/executed_price
    slippage_amount=executed_price-requested_price
    trade_id=str(uuid4())
    detected_at=_utc_now()
    execution_at=_utc_now()
    entry_latency_ms=Decimal(str((detected_at-signal_created_at).total_seconds()*1000))
    decision_latency_ms=Decimal(str((execution_at-detected_at).total_seconds()*1000))
    total_latency_ms=Decimal(str((execution_at-signal_created_at).total_seconds()*1000))
    metadata=json.dumps({"detector":"phase5_48h_simulation","execution":"paper","network":"mainnet-beta","mock_slippage_model":"fixed_buy_price_penalty"})
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """INSERT INTO token_metadata(mint_address,network)
               VALUES(%s,'mainnet-beta') ON CONFLICT(mint_address) DO NOTHING""",(token_mint,)
        )
        cursor.execute(
            """INSERT INTO simulated_trades
               (trade_id,token_mint,side,status,quantity,requested_price,executed_price,
                requested_notional,executed_notional,slippage_bps,slippage_amount,
                signal_id,signal_created_at,detected_at,entry_latency_ms,decision_latency_ms,
                execution_latency_ms,total_latency_ms,metadata)
               VALUES(%s,%s,'BUY','OPEN',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
               ON CONFLICT(signal_id) DO NOTHING RETURNING id""",
            (trade_id,token_mint,quantity,requested_price,executed_price,notional_sol,notional_sol,
             slippage_bps,slippage_amount*quantity,signal_id,signal_created_at,detected_at,
             entry_latency_ms,decision_latency_ms,decision_latency_ms,total_latency_ms,metadata)
        )
        inserted=cursor.fetchone() is not None
        conn.commit()
    return inserted


def run(config:SimulationConfig)->None:
    config.validate()
    rpc_url=os.getenv("SOLANA_RPC_URL","https://api.mainnet.solana.com")
    if os.getenv("SOLANA_NETWORK","mainnet-beta")!="mainnet-beta":
        raise RuntimeError("SOLANA_NETWORK must be mainnet-beta")
    _verify_mainnet(rpc_url)
    started_at=_utc_now()
    deadline=started_at+timedelta(hours=float(config.duration_hours))
    cursor_time=started_at
    LOGGER.info("starting mainnet paper simulation until %s",deadline.isoformat())
    while _utc_now()<deadline:
        for _,token_mint,observed_at in _candidate_events(cursor_time):
            cursor_time=max(cursor_time,observed_at+timedelta(microseconds=1))
            signal=find_spatiotemporal_cluster(token_mint,observed_at)
            if signal is None: continue
            _insert_simulated_entry(signal.token_mint,f"phase5:{signal.signal_id}",signal.representative_price,config.notional_sol,config.slippage_percent,signal.window_start)
        remaining=(deadline-_utc_now()).total_seconds()
        if remaining>0: time.sleep(min(config.poll_seconds,remaining))
    LOGGER.info("mainnet paper simulation window completed")


def main()->None:
    parser=argparse.ArgumentParser(description="Run the mainnet paper-trading simulation.")
    parser.add_argument("--hours",type=Decimal,default=Decimal("48"))
    parser.add_argument("--poll-seconds",type=int,default=2)
    parser.add_argument("--slippage-percent",type=Decimal,default=Decimal("4.0"))
    parser.add_argument("--notional-sol",type=Decimal,default=Decimal("1"))
    args=parser.parse_args()
    logging.basicConfig(level=os.getenv("LOG_LEVEL","INFO"),format="%(asctime)s %(levelname)s %(name)s %(message)s")
    run(SimulationConfig(args.hours,args.poll_seconds,args.slippage_percent,args.notional_sol))


if __name__=="__main__": main()

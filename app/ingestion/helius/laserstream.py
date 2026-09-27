from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence

import grpc

from app.config.settings import settings
from app.ingestion.helius.proto import geyser_pb2, geyser_pb2_grpc


class LaserStreamClient:
    """Async Yellowstone-compatible client for Helius LaserStream Devnet."""

    def __init__(self, wallets: Sequence[str], from_slot: int | None = None) -> None:
        if not settings.helius_api_key:
            raise RuntimeError("HELIUS_API_KEY is required for LaserStream")
        if not settings.helius_grpc_endpoint:
            raise RuntimeError("HELIUS_GRPC_ENDPOINT is required for LaserStream")
        self.wallets = tuple(dict.fromkeys(wallets))
        self.from_slot = from_slot

    @staticmethod
    def _target(endpoint: str) -> str:
        target = endpoint.removeprefix("https://").removeprefix("http://").rstrip("/")
        return target if ":" in target.rsplit("/", 1)[-1] else f"{target}:443"

    def _request(self) -> geyser_pb2.SubscribeRequest:
        tx_filter = geyser_pb2.SubscribeRequestFilterTransactions(
            vote=False,
            failed=False,
            account_include=list(self.wallets),
        )
        kwargs = {
            "transactions": {"cex-outflows": tx_filter},
            "commitment": geyser_pb2.CONFIRMED,
        }
        if self.from_slot is not None:
            kwargs["from_slot"] = self.from_slot
        return geyser_pb2.SubscribeRequest(**kwargs)

    async def updates(self) -> AsyncIterator[geyser_pb2.SubscribeUpdate]:
        credentials = grpc.ssl_channel_credentials()
        channel = grpc.aio.secure_channel(
            self._target(settings.helius_grpc_endpoint),
            credentials,
        )
        stub = geyser_pb2_grpc.GeyserStub(channel)

        async def requests() -> AsyncIterator[geyser_pb2.SubscribeRequest]:
            yield self._request()
            ping_id = 0
            while True:
                await asyncio.sleep(20)
                ping_id += 1
                yield geyser_pb2.SubscribeRequest(
                    ping=geyser_pb2.SubscribeRequestPing(id=ping_id)
                )

        try:
            call = stub.Subscribe(
                requests(),
                metadata=(("x-token", settings.helius_api_key),),
            )
            async for update in call:
                yield update
        finally:
            await channel.close()

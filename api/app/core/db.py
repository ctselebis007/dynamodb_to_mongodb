"""One cached AsyncMongoClient, rebuilt when the connection string changes."""

from __future__ import annotations

import asyncio

import certifi
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from app.core.errors import AppError
from app.core.settings import get_settings

APP_NAME = "mongodb-demo-kit"


def make_client(uri: str, timeout_ms: int = 5000) -> AsyncMongoClient:
    kwargs: dict = {"appName": APP_NAME, "serverSelectionTimeoutMS": timeout_ms}
    lower = uri.lower()
    if lower.startswith("mongodb+srv://") or "tls=true" in lower or "ssl=true" in lower:
        kwargs["tlsCAFile"] = certifi.where()
    return AsyncMongoClient(uri, **kwargs)


class ClientCache:
    def __init__(self) -> None:
        self._client: AsyncMongoClient | None = None
        self._uri: str | None = None
        self._lock = asyncio.Lock()

    async def get(self, uri: str) -> AsyncMongoClient:
        async with self._lock:
            if self._client is None or self._uri != uri:
                old = self._client
                self._client, self._uri = make_client(uri), uri
                if old is not None:
                    await old.close()
            return self._client

    async def close(self) -> None:
        async with self._lock:
            if self._client is not None:
                await self._client.close()
            self._client, self._uri = None, None


clients = ClientCache()


async def get_db() -> AsyncDatabase:
    settings = get_settings()
    if not settings.mongo_uri:
        raise AppError(
            "NOT_CONFIGURED", "No MongoDB connection string saved.", "Open Setup and save one.", 409
        )
    client = await clients.get(settings.mongo_uri)
    return client[settings.db_name]

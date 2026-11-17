"""`_demo_meta` tracks what the database was seeded/indexed with."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import Depends
from pymongo.asynchronous.database import AsyncDatabase

from app.core.db import get_db
from app.core.errors import AppError
from app.core.models import ApiModel
from app.core.settings import Settings, get_settings

META_COLLECTION = "_demo_meta"
META_ID = "meta"


class DemoMeta(ApiModel):
    provider: str
    model: str
    dims: int
    seeded_at: datetime | None = None
    indexed_at: datetime | None = None
    modules: list[str] = []


async def read_meta(db: AsyncDatabase) -> DemoMeta | None:
    doc = await db[META_COLLECTION].find_one({"_id": META_ID}, {"_id": 0})
    return DemoMeta.model_validate(doc) if doc else None


async def write_meta(db: AsyncDatabase, **fields: Any) -> None:
    await db[META_COLLECTION].update_one({"_id": META_ID}, {"$set": fields}, upsert=True)


def now() -> datetime:
    return datetime.now(UTC)


def readiness_error(settings: Settings, meta: DemoMeta | None) -> AppError | None:
    if meta is None or meta.seeded_at is None:
        return AppError(
            "NOT_SEEDED", "The demo data has not been seeded.", "Run Seed on Setup.", 409
        )
    if (meta.provider, meta.model) != (settings.provider, settings.model):
        return AppError(
            "RESEED_REQUIRED",
            f"Data was embedded with {meta.provider}/{meta.model}, "
            f"settings use {settings.provider}/{settings.model}.",
            "Re-seed and re-index on Setup.",
            409,
        )
    if meta.indexed_at is None:
        return AppError(
            "INDEX_NOT_READY",
            "Indexes are not ready.",
            "Run Create Indexes and wait for ready.",
            409,
        )
    return None


async def require_ready(db: AsyncDatabase = Depends(get_db)) -> DemoMeta:
    meta = await read_meta(db)
    err = readiness_error(get_settings(), meta)
    if err:
        raise err
    assert meta is not None
    return meta

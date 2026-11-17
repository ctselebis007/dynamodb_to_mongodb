"""Shared `{ results, pipeline, timings }` response shape for module query endpoints."""

from __future__ import annotations

import json
import time
from typing import Any, Generic, TypeVar

from bson import json_util
from pydantic import BaseModel
from pymongo.asynchronous.collection import AsyncCollection

from app.core.models import ApiModel

Pipeline = list[dict[str, Any]]
T = TypeVar("T")


class Timings(ApiModel):
    server_ms: float
    embed_ms: float | None = None
    rerank_ms: float | None = None


class QueryResponse(ApiModel, Generic[T]):  # noqa: UP046
    results: list[T]
    pipeline: Pipeline
    timings: Timings
    explain: dict[str, Any] | None = None


class PipelineRun(BaseModel):
    results: list[dict[str, Any]]
    pipeline: Pipeline
    server_ms: float
    explain: dict[str, Any] | None = None


def to_json(value: Any) -> Any:
    """BSON types (ObjectId, datetime, Timestamp, ...) to plain JSON values."""
    return json.loads(json_util.dumps(value, json_options=json_util.RELAXED_JSON_OPTIONS))


async def run_pipeline(
    coll: AsyncCollection, pipeline: Pipeline, explain: bool = False
) -> PipelineRun:
    start = time.perf_counter()
    cursor = await coll.aggregate(pipeline)
    results = await cursor.to_list()
    server_ms = round((time.perf_counter() - start) * 1000, 2)
    stats = None
    if explain:
        stats = to_json(
            await coll.database.command(
                "explain",
                {"aggregate": coll.name, "pipeline": pipeline, "cursor": {}},
                verbosity="executionStats",
            )
        )
    return PipelineRun(results=results, pipeline=pipeline, server_ms=server_ms, explain=stats)

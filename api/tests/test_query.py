from typing import Any

import pytest

from app.core.query import run_pipeline


class FakeCursor:
    async def to_list(self) -> list[dict[str, Any]]:
        return [{"_id": "a"}]


class FakeColl:
    name = "things"

    async def aggregate(self, pipeline: list[dict[str, Any]]) -> FakeCursor:
        return FakeCursor()


async def test_returns_exact_pipeline_and_timing():
    pipeline = [{"$match": {"x": 1}}, {"$limit": 5}]
    run = await run_pipeline(FakeColl(), pipeline)  # type: ignore[arg-type]
    assert run.pipeline == pipeline
    assert run.server_ms >= 0
    assert run.results == [{"_id": "a"}]
    assert run.explain is None


@pytest.mark.atlas
async def test_explain_returns_stats(atlas_db):
    await atlas_db.things.insert_many([{"x": i} for i in range(5)])
    run = await run_pipeline(atlas_db.things, [{"$match": {"x": {"$gte": 2}}}], explain=True)
    assert len(run.results) == 3
    assert run.explain is not None

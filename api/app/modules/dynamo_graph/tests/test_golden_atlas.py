"""Golden answers: seed scale 1 into a throwaway Atlas DB and check every sample query
against Sample_Queries_Criteria.md. Run with MONGODB_URI_TEST set: pytest -m atlas"""

import asyncio
import json
import random
from typing import Any

import pytest
from pymongo.operations import SearchIndexModel

from app.core.errors import AppError
from app.core.query import run_pipeline, to_json
from app.modules.dynamo_graph import indexes, seed, writes
from app.modules.dynamo_graph.catalog import QUERIES, evaluate
from app.modules.dynamo_graph.router import BUILDERS

IXSCAN_QUERIES = ["T1", "T2", "A2", "A3"]


async def _seed_and_index(db) -> None:
    for name, docs in seed.generate(random.Random(0)).items():
        await db[name].insert_many(docs)
    for idx in indexes.regular():
        await db[idx["collection"]].create_index(
            idx["keys"], name=idx["name"], unique=idx.get("unique", False)
        )
    for spec in indexes.search():
        await db[spec["collection"]].create_search_index(
            SearchIndexModel(definition=spec["definition"], name=spec["name"])
        )
    for _ in range(120):
        info = await (await db[seed.TALENT].list_search_indexes(indexes.TALENT_SEARCH)).to_list()
        if info and info[0].get("status") == "READY" and info[0].get("queryable"):
            return
        await asyncio.sleep(3)
    pytest.fail("Search index did not become READY")


def _winning_stages(explain: dict) -> str:
    return json.dumps(explain)


@pytest.mark.atlas
async def test_golden_answers_and_writes(atlas_db, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(seed.SCALE_ENV, raising=False)
    await _seed_and_index(atlas_db)

    failures = []
    for qid, spec in QUERIES.items():
        model, coll, build = BUILDERS[qid]
        run = await run_pipeline(
            atlas_db[coll],
            build(model.model_validate(spec.defaults)),
            explain=qid in IXSCAN_QUERIES,
        )
        doc = to_json(run.results)[0] if run.results else {}
        for check in spec.checks:
            ok, actual = evaluate(check, doc)
            if not ok:
                failures.append(f"{qid} {check.path}: expected {check.expected!r}, got {actual!r}")
        if run.explain is not None:
            plan = _winning_stages(run.explain)
            if "IXSCAN" not in plan or "COLLSCAN" in plan:
                failures.append(f"{qid}: expected IXSCAN without COLLSCAN")
    assert not failures, "\n".join(failures)

    # Atomic replace: a simulated failure rolls back, a normal run commits.
    quad: dict[str, Any] = {
        "graph": "talent:metadata",
        "subject": "line:REALGAR_SHOAL_ZIRCON_SAVANNA_BASIN_BASALT",
        "predicate": "rdfs:label",
    }
    label = "TALUS-Basin Magnetite & Hoodoo"
    total = await atlas_db[seed.TALENT].count_documents({})
    aborted = await writes.replace_quad(atlas_db, **quad, old_object=label,
                                        new_object="Renamed", simulate_failure=True)  # fmt: skip
    assert aborted["committed"] is False and aborted["objects_after"] == [label]
    done = await writes.replace_quad(atlas_db, **quad, old_object=label, new_object="Renamed")
    assert done["committed"] is True and done["objects_after"] == ["Renamed"]
    assert await atlas_db[seed.TALENT].count_documents({}) == total
    with pytest.raises(AppError) as exc:
        await writes.replace_quad(atlas_db, **quad, old_object=label, new_object="Again")
    assert exc.value.code == "QUAD_NOT_FOUND"

    # Reloading the graph restores the workbook state.
    reload = await writes.reload_graph(atlas_db, "talent:metadata")
    assert reload["deleted"] == reload["inserted"] == 5602
    assert await atlas_db[seed.TALENT].count_documents({}) == total
    assert await atlas_db[seed.TALENT].count_documents(quad | {"object": label}) == 1

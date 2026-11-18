"""Write-pattern demos: atomic quad replace and a transactional named-graph reload."""

from __future__ import annotations

import time
from typing import Any

from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.core.errors import AppError
from app.modules.dynamo_graph.seed import META, TALENT, load_fixture

RELOAD_BATCH = 1000


class SimulatedFailure(Exception):
    pass


async def current_scale(db: AsyncDatabase) -> int:
    doc = await db[META].find_one({"_id": "scale"})
    return int(doc["scale"]) if doc else 1


async def replace_quad(
    db: AsyncDatabase,
    graph: str,
    subject: str,
    predicate: str,
    old_object: str,
    new_object: str,
    simulate_failure: bool = False,
) -> dict[str, Any]:
    """Delete one quad and insert its replacement in a single transaction."""
    coll = db[TALENT]
    key = {"graph": graph, "subject": subject, "predicate": predicate}

    async def txn(session: AsyncClientSession) -> None:
        old = await coll.find_one_and_delete(key | {"object": old_object}, session=session)
        if old is None:
            raise AppError(
                "QUAD_NOT_FOUND",
                f"No quad ({graph}, {subject}, {predicate}, {old_object}).",
                "Check the current object with the 'after' list, or reload the graph.",
                409,
            )
        new = {k: v for k, v in old.items() if k != "_id"} | {"object": new_object}
        if old["object_kind"] == "literal":
            new["object_label"] = new_object
        try:
            await coll.insert_one(new, session=session)
        except DuplicateKeyError:
            raise AppError(
                "QUAD_EXISTS", "The replacement quad already exists.", "Pick another object.", 409
            ) from None
        if simulate_failure:
            raise SimulatedFailure("Simulated failure after delete + insert")

    start = time.perf_counter()
    committed, message = True, "Committed: old quad deleted, replacement inserted."
    async with db.client.start_session() as session:
        try:
            await session.with_transaction(txn)
        except SimulatedFailure as exc:
            committed, message = False, f"Aborted ({exc}); nothing changed."
    ms = round((time.perf_counter() - start) * 1000, 2)
    after = await coll.find(key, {"_id": 0, "object": 1}).to_list()
    return {
        "committed": committed,
        "message": message,
        "ms": ms,
        "objects_after": sorted(d["object"] for d in after),
    }


def _ms(since: float) -> float:
    return round((time.perf_counter() - since) * 1000, 2)


def _by_predicate(graph: str) -> list[dict[str, Any]]:
    return [
        {"$match": {"graph": graph}},
        {"$group": {"_id": "$predicate", "quads": {"$sum": 1}}},
        {"$sort": {"quads": -1, "_id": 1}},
    ]


async def _profile(db: AsyncDatabase, graph: str) -> tuple[list[dict[str, Any]], float]:
    start = time.perf_counter()
    rows = await (await db[TALENT].aggregate(_by_predicate(graph))).to_list()
    return rows, _ms(start)


def _summary(rows: list[dict[str, Any]]) -> str:
    total = sum(r["quads"] for r in rows)
    return f"{total:,} quads across {len(rows)} predicates"


async def reload_graph(db: AsyncDatabase, graph: str) -> dict[str, Any]:
    """Replace every quad of one named graph from the fixtures, atomically for readers.

    Returns a per-step timeline (reads, aggregation pipelines, transactional writes, commit).
    """
    if await current_scale(db) != 1:
        raise AppError(
            "RELOAD_DISABLED",
            "Graph reload is only enabled at scale 1.",
            "At scale-up size a single transaction would exceed the 60s limit; "
            "production would use a staged load + swap.",
            409,
        )
    total_start = time.perf_counter()
    start = time.perf_counter()
    docs = [d for d in load_fixture(TALENT) if d["graph"] == graph]
    if not docs:
        raise AppError("UNKNOWN_GRAPH", f"No fixture quads for graph '{graph}'.", "", 404)
    steps: list[dict[str, Any]] = [
        {
            "name": "Load workbook quads",
            "op": "fixture read",
            "kind": "app",
            "in_transaction": False,
            "command": {"filter": {"graph": graph}},
            "docs": len(docs),
            "ms": _ms(start),
            "result": f"{len(docs):,} quads read from the fixture",
        }
    ]
    before, before_ms = await _profile(db, graph)
    steps.append(
        {
            "name": "Profile current graph",
            "op": "aggregate",
            "kind": "aggregate",
            "in_transaction": False,
            "command": _by_predicate(graph),
            "docs": sum(r["quads"] for r in before),
            "ms": before_ms,
            "result": _summary(before),
        }
    )

    coll = db[TALENT]
    counts = {"deleted": 0, "inserted": 0}
    txn_steps: list[dict[str, Any]] = []
    attempts = 0
    callback_end = 0.0

    async def txn(session: AsyncClientSession) -> None:
        nonlocal attempts, callback_end
        attempts += 1
        txn_steps.clear()
        t = time.perf_counter()
        counts["deleted"] = (
            await coll.delete_many({"graph": graph}, session=session)
        ).deleted_count
        txn_steps.append(
            {
                "name": "Delete current graph",
                "op": "deleteMany",
                "kind": "write",
                "in_transaction": True,
                "command": {"filter": {"graph": graph}},
                "docs": counts["deleted"],
                "ms": _ms(t),
                "result": f"{counts['deleted']:,} quads deleted",
            }
        )
        batches = range(0, len(docs), RELOAD_BATCH)
        for n, i in enumerate(batches, 1):
            batch = [dict(d) for d in docs[i : i + RELOAD_BATCH]]
            t = time.perf_counter()
            await coll.insert_many(batch, session=session)
            txn_steps.append(
                {
                    "name": f"Insert batch {n}/{len(batches)}",
                    "op": "insertMany",
                    "kind": "write",
                    "in_transaction": True,
                    "command": {"documents": len(batch), "ordered": True},
                    "docs": len(batch),
                    "ms": _ms(t),
                    "result": f"quads {i + 1:,}–{i + len(batch):,} inserted",
                }
            )
        counts["inserted"] = len(docs)
        callback_end = time.perf_counter()

    start = time.perf_counter()
    async with db.client.start_session() as session:
        await session.with_transaction(txn)
    txn_ms = _ms(start)
    commit_ms = _ms(callback_end)
    work_ms = round(sum(s["ms"] for s in txn_steps), 2)
    steps.append(
        {
            "name": "Session + transaction overhead",
            "op": "startTransaction",
            "kind": "txn",
            "in_transaction": True,
            "command": {"startTransaction": True, "autocommit": False},
            "docs": None,
            "ms": round(max(txn_ms - work_ms - commit_ms, 0.0), 2),
            "result": f"{attempts} attempt{'s' if attempts != 1 else ''}",
        }
    )
    steps.extend(txn_steps)
    steps.append(
        {
            "name": "Commit transaction",
            "op": "commitTransaction",
            "kind": "txn",
            "in_transaction": True,
            "command": {"commitTransaction": 1},
            "docs": None,
            "ms": commit_ms,
            "result": "changes visible to readers",
        }
    )

    after, after_ms = await _profile(db, graph)
    steps.append(
        {
            "name": "Verify reloaded graph",
            "op": "aggregate",
            "kind": "aggregate",
            "in_transaction": False,
            "command": _by_predicate(graph),
            "docs": sum(r["quads"] for r in after),
            "ms": after_ms,
            "result": _summary(after),
        }
    )
    return {
        "graph": graph,
        **counts,
        "ms": txn_ms,
        "total_ms": _ms(total_start),
        "steps": steps,
    }

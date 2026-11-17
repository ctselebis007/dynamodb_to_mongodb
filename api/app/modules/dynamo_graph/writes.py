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


async def reload_graph(db: AsyncDatabase, graph: str) -> dict[str, Any]:
    """Replace every quad of one named graph from the fixtures, atomically for readers."""
    if await current_scale(db) != 1:
        raise AppError(
            "RELOAD_DISABLED",
            "Graph reload is only enabled at scale 1.",
            "At scale-up size a single transaction would exceed the 60s limit; "
            "production would use a staged load + swap.",
            409,
        )
    docs = [d for d in load_fixture(TALENT) if d["graph"] == graph]
    if not docs:
        raise AppError("UNKNOWN_GRAPH", f"No fixture quads for graph '{graph}'.", "", 404)
    coll = db[TALENT]
    counts = {"deleted": 0, "inserted": 0}

    async def txn(session: AsyncClientSession) -> None:
        counts["deleted"] = (
            await coll.delete_many({"graph": graph}, session=session)
        ).deleted_count
        for i in range(0, len(docs), RELOAD_BATCH):
            batch = [dict(d) for d in docs[i : i + RELOAD_BATCH]]
            await coll.insert_many(batch, session=session)
        counts["inserted"] = len(docs)

    start = time.perf_counter()
    async with db.client.start_session() as session:
        await session.with_transaction(txn)
    return {"graph": graph, **counts, "ms": round((time.perf_counter() - start) * 1000, 2)}

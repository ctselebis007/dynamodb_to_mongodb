"""Seed and index jobs driven by each module's seed.py / indexes.py."""

from __future__ import annotations

import asyncio
import random
import time

from pymongo.asynchronous.database import AsyncDatabase
from pymongo.operations import SearchIndexModel

from app.core.embeddings import EmbeddingProvider
from app.core.errors import AppError
from app.core.jobs import Job
from app.core.meta import now, write_meta
from app.core.registry import ModuleInfo
from app.core.settings import Settings

EMBED_FIELD = "embedding"
EMBED_BATCH = 128
INSERT_BATCH = 500
DEFAULT_SEED = 42


def embed_text(doc: dict, fields: list[str]) -> str:
    return "\n".join(str(doc[f]) for f in fields if doc.get(f))


async def seed_all(
    db: AsyncDatabase,
    provider: EmbeddingProvider,
    settings: Settings,
    modules: list[ModuleInfo],
    job: Job,
) -> None:
    plan: list[tuple[str, list[dict], list[str]]] = []
    for m in modules:
        assert m.seed is not None
        data = m.seed.generate(random.Random(getattr(m.seed, "SEED", DEFAULT_SEED)))
        for name in m.seed.collections():
            docs = data.get(name, [])
            plan.append((name, docs, m.seed.embed_fields.get(name, [])))
            job.step(name, f"{name} ({len(docs)} docs)")

    await write_meta(
        db,
        provider=settings.provider,
        model=settings.model,
        dims=settings.dims,
        seeded_at=None,
        indexed_at=None,
        modules=[m.slug for m in modules],
    )

    total = sum(len(docs) for _, docs, _ in plan) or 1
    done = 0
    for name, docs, fields in plan:
        step = job.step(name, status="running", detail="dropping collection")
        await db.drop_collection(name)
        n = len(docs)
        if fields:
            texts = [embed_text(d, fields) for d in docs]
            for i in range(0, n, EMBED_BATCH):
                vectors = await provider.embed(texts[i : i + EMBED_BATCH], "document")
                for doc, vec in zip(docs[i : i + EMBED_BATCH], vectors, strict=True):
                    doc[EMBED_FIELD] = vec
                embedded = min(i + EMBED_BATCH, n)
                step.detail = f"embedded {embedded}/{n}"
                step.progress = int(90 * embedded / n)
                job.progress = int(100 * (done + 0.9 * embedded) / total)
        for i in range(0, n, INSERT_BATCH):
            await db[name].insert_many(docs[i : i + INSERT_BATCH])
            step.detail = f"inserted {min(i + INSERT_BATCH, n)}/{n}"
        done += n
        step.status, step.progress, step.detail = "done", 100, f"{n} docs"
        job.progress = int(100 * done / total)

    await write_meta(db, seeded_at=now())


async def build_indexes(
    db: AsyncDatabase,
    modules: list[ModuleInfo],
    dims: int,
    job: Job,
    poll_s: float = 3.0,
    timeout_s: float = 900.0,
) -> None:
    await write_meta(db, indexed_at=None)
    pending: list[tuple[str, str, str]] = []
    for m in modules:
        assert m.indexes is not None
        for idx in m.indexes.regular():
            step = job.step(
                f"regular:{idx['name']}",
                f"{idx['collection']}.{idx['name']}",
                status="running",
                detail="creating",
            )
            await db[idx["collection"]].create_index(
                idx["keys"], name=idx["name"], unique=idx.get("unique", False)
            )
            step.status, step.progress, step.detail = "done", 100, "ready"

        specs = [(s, "search") for s in m.indexes.search()]
        specs += [(s, "vectorSearch") for s in m.indexes.vector(dims)]
        for spec, kind in specs:
            coll = db[spec["collection"]]
            step_id = f"{kind}:{spec['name']}"
            job.step(
                step_id,
                f"{spec['collection']}.{spec['name']} ({kind})",
                status="running",
                detail="creating",
            )
            existing = await (await coll.list_search_indexes(spec["name"])).to_list()
            if existing:
                await coll.update_search_index(spec["name"], spec["definition"])
            else:
                await coll.create_search_index(
                    SearchIndexModel(definition=spec["definition"], name=spec["name"], type=kind)
                )
            pending.append((spec["collection"], spec["name"], step_id))

    deadline = time.monotonic() + timeout_s
    while pending:
        still: list[tuple[str, str, str]] = []
        for coll_name, name, step_id in pending:
            info = await (await db[coll_name].list_search_indexes(name)).to_list()
            status = info[0].get("status", "PENDING") if info else "PENDING"
            step = job.step(step_id, detail=status.lower())
            if status == "FAILED":
                raise AppError(
                    "INDEX_FAILED",
                    f"Index {name} failed to build.",
                    "Check the index definition in the Atlas UI.",
                    500,
                )
            if status == "READY" and info[0].get("queryable"):
                step.status, step.progress = "done", 100
            else:
                still.append((coll_name, name, step_id))
        pending = still
        total = len(job.steps) or 1
        job.progress = int(100 * sum(s.status == "done" for s in job.steps) / total)
        if pending:
            if time.monotonic() > deadline:
                raise AppError(
                    "INDEX_NOT_READY",
                    "Timed out waiting for indexes.",
                    "Check index status in the Atlas UI, then retry.",
                    504,
                )
            await asyncio.sleep(poll_s)

    await write_meta(db, indexed_at=now())

"""Setup page API: settings, connection tests, seed and index jobs, readiness status."""

from __future__ import annotations

import asyncio
import re
import time
import uuid
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ValidationError

from app.core.db import get_db, make_client
from app.core.embeddings import make_provider
from app.core.errors import AppError, to_app_error
from app.core.jobs import Job, JobError, jobs
from app.core.meta import DemoMeta, read_meta, readiness_error
from app.core.models import ApiModel
from app.core.registry import ModuleInfo
from app.core.seeding import build_indexes, seed_all
from app.core.settings import MaskedSettings, Settings, SettingsUpdate, get_settings, get_store

router = APIRouter(prefix="/api/setup", tags=["setup"])

URI_RE = re.compile(r"^mongodb(\+srv)?://[^/\s]+")
MIN_MAJOR_VERSION = 9


class CheckRow(ApiModel):
    id: str
    label: str
    status: Literal["ok", "warn", "fail", "skip"]
    message: str = ""
    hint: str = ""
    ms: float | None = None


class CheckResults(ApiModel):
    rows: list[CheckRow]


class SetupStatus(ApiModel):
    configured: bool
    reachable: bool
    seeded: bool
    indexed: bool
    reseed_required: bool
    meta: DemoMeta | None = None
    modules: list[str]
    error: JobError | None = None


class SeedRequest(BaseModel):
    confirm: bool = False


def _validated(fn, *args) -> Settings:
    try:
        return fn(*args)
    except ValidationError as exc:
        msg = "; ".join(
            f"{'.'.join(map(str, e['loc'])) or 'settings'}: {e['msg']}" for e in exc.errors()
        )
        raise AppError("VALIDATION_ERROR", msg, "Check the form values.", 422) from None


def _modules(request: Request) -> list[ModuleInfo]:
    return request.app.state.modules


@router.get("", response_model=MaskedSettings)
async def read_setup() -> MaskedSettings:
    return get_store().load().masked()


@router.put("", response_model=MaskedSettings)
async def update_setup(update: SettingsUpdate) -> MaskedSettings:
    return _validated(get_store().save, update).masked()


@router.get("/status", response_model=SetupStatus)
async def setup_status(request: Request) -> SetupStatus:
    settings = get_settings()
    modules = [m.slug for m in _modules(request)]
    if not settings.mongo_uri:
        return SetupStatus(
            configured=False,
            reachable=False,
            seeded=False,
            indexed=False,
            reseed_required=False,
            modules=modules,
        )
    try:
        meta = await read_meta(await get_db())
    except Exception as exc:
        err = to_app_error(exc)
        return SetupStatus(
            configured=True,
            reachable=False,
            seeded=False,
            indexed=False,
            reseed_required=False,
            modules=modules,
            error=JobError(code=err.code, message=err.message, hint=err.hint),
        )
    err = readiness_error(settings, meta)
    return SetupStatus(
        configured=True,
        reachable=True,
        seeded=bool(meta and meta.seeded_at),
        indexed=bool(meta and meta.indexed_at),
        reseed_required=err is not None and err.code == "RESEED_REQUIRED",
        meta=meta,
        modules=modules,
    )


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)


async def _check_atlas(s: Settings) -> list[CheckRow]:
    labels = {
        "uri": "Connection string",
        "ping": "Atlas ping + version",
        "write": "Write permission",
        "search": "Search available",
        "rank_fusion": "$rankFusion supported",
    }

    def rows(done: list[CheckRow]) -> list[CheckRow]:
        seen = {r.id for r in done}
        return done + [
            CheckRow(id=k, label=v, status="skip") for k, v in labels.items() if k not in seen
        ]

    if not s.mongo_uri:
        return rows(
            [
                CheckRow(
                    id="uri",
                    label=labels["uri"],
                    status="fail",
                    message="No connection string.",
                    hint="Paste the mongodb+srv:// string from Atlas → Connect.",
                )
            ]
        )
    if not URI_RE.match(s.mongo_uri):
        return rows(
            [
                CheckRow(
                    id="uri",
                    label=labels["uri"],
                    status="fail",
                    message="Must start with mongodb+srv:// or mongodb://",
                    hint="Copy it from Atlas → Connect → Drivers.",
                )
            ]
        )
    out = [CheckRow(id="uri", label=labels["uri"], status="ok", message="Valid format")]

    try:
        client = make_client(s.mongo_uri)
    except Exception as exc:
        err = to_app_error(exc)
        out[0] = CheckRow(
            id="uri", label=labels["uri"], status="fail", message=err.message, hint=err.hint
        )
        return rows(out)

    coll = client[s.db_name][f"_demokit_check_{uuid.uuid4().hex[:8]}"]
    wrote = False
    try:
        t = time.perf_counter()
        try:
            await client.admin.command("ping")
            version = (await client.admin.command("buildInfo"))["version"]
        except Exception as exc:
            err = to_app_error(exc)
            out.append(
                CheckRow(
                    id="ping",
                    label=labels["ping"],
                    status="fail",
                    message=err.message,
                    hint=err.hint,
                    ms=_ms(t),
                )
            )
            return rows(out)
        atlas = ".mongodb.net" in s.mongo_uri
        major = int(version.split(".")[0])
        out.append(
            CheckRow(
                id="ping",
                label=labels["ping"],
                status="ok" if major >= MIN_MAJOR_VERSION else "warn",
                message=f"MongoDB {version} · {'Atlas' if atlas else 'not Atlas'}"
                " · tier not exposed to drivers (M10+ recommended)",
                hint="" if major >= MIN_MAJOR_VERSION else "This kit targets MongoDB 9.0.",
                ms=_ms(t),
            )
        )

        t = time.perf_counter()
        try:
            await coll.insert_one({"_id": 1})
            wrote = True
            out.append(
                CheckRow(
                    id="write",
                    label=labels["write"],
                    status="ok",
                    message=f"Can write to '{s.db_name}'",
                    ms=_ms(t),
                )
            )
        except Exception as exc:
            err = to_app_error(exc)
            out.append(
                CheckRow(
                    id="write",
                    label=labels["write"],
                    status="fail",
                    message=err.message,
                    hint=f"Use a database user with readWrite on '{s.db_name}'.",
                    ms=_ms(t),
                )
            )
            return rows(out)

        t = time.perf_counter()
        try:
            await (await coll.list_search_indexes()).to_list()
            out.append(
                CheckRow(
                    id="search",
                    label=labels["search"],
                    status="ok",
                    message="listSearchIndexes succeeded",
                    ms=_ms(t),
                )
            )
        except Exception as exc:
            out.append(
                CheckRow(
                    id="search",
                    label=labels["search"],
                    status="fail",
                    message=to_app_error(exc).message,
                    hint="Search and Vector Search need an Atlas cluster.",
                    ms=_ms(t),
                )
            )

        t = time.perf_counter()
        try:
            pipeline = [
                {"$rankFusion": {"input": {"pipelines": {"p": [{"$sort": {"_id": 1}}]}}}},
                {"$limit": 1},
            ]
            await (await coll.aggregate(pipeline)).to_list()
            out.append(
                CheckRow(
                    id="rank_fusion",
                    label=labels["rank_fusion"],
                    status="ok",
                    message="Hybrid search available",
                    ms=_ms(t),
                )
            )
        except Exception as exc:
            out.append(
                CheckRow(
                    id="rank_fusion",
                    label=labels["rank_fusion"],
                    status="fail",
                    message=to_app_error(exc).message,
                    hint="Hybrid columns need $rankFusion (Atlas 9.0).",
                    ms=_ms(t),
                )
            )
    finally:
        if wrote:
            try:
                await coll.drop()
            except Exception:
                pass
        await client.close()
    return rows(out)


async def _check_embedding(s: Settings) -> CheckRow:
    label = f"Test embedding ({s.provider} · {s.model})"
    if not s.api_key:
        return CheckRow(
            id="embedding",
            label=label,
            status="fail",
            message="No API key.",
            hint="Paste a Voyage (Atlas model API key) or OpenAI key.",
        )
    t = time.perf_counter()
    try:
        vectors = await make_provider(s).embed(["MongoDB demo kit connection test"], "query")
    except Exception as exc:
        err = to_app_error(exc)
        return CheckRow(
            id="embedding",
            label=label,
            status="fail",
            message=err.message,
            hint=err.hint,
            ms=_ms(t),
        )
    dims = len(vectors[0])
    return CheckRow(
        id="embedding",
        label=label,
        status="ok" if dims == s.dims else "warn",
        message=f"{dims} dims",
        hint="" if dims == s.dims else f"Expected {s.dims} dims for this model.",
        ms=_ms(t),
    )


@router.post("/test", response_model=CheckResults)
async def test_connections(update: SettingsUpdate) -> CheckResults:
    s = _validated(get_store().merged, update)
    atlas, embedding = await asyncio.gather(_check_atlas(s), _check_embedding(s))
    return CheckResults(rows=[*atlas, embedding])


@router.post("/seed", response_model=Job)
async def start_seed(req: SeedRequest, request: Request) -> Job:
    if not req.confirm:
        raise AppError(
            "CONFIRM_REQUIRED",
            "Seeding drops and recreates the demo collections.",
            "Confirm the dialog to continue.",
            400,
        )
    settings = get_settings()
    db = await get_db()
    provider = make_provider(settings)
    modules = [m for m in _modules(request) if m.seed]

    async def run(job: Job) -> None:
        await seed_all(db, provider, settings, modules, job)

    return jobs.start("seed", run)


@router.post("/indexes", response_model=Job)
async def start_indexes(request: Request) -> Job:
    db = await get_db()
    meta = await read_meta(db)
    err = readiness_error(get_settings(), meta)
    if err and err.code != "INDEX_NOT_READY":
        raise err
    assert meta is not None
    modules = [m for m in _modules(request) if m.indexes]

    async def run(job: Job) -> None:
        await build_indexes(db, modules, meta.dims, job)

    return jobs.start("indexes", run)

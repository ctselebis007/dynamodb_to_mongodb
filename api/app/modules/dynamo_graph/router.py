from __future__ import annotations

import time
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, StringConstraints, ValidationError
from pymongo.asynchronous.database import AsyncDatabase

from app.core.db import get_db
from app.core.embeddings import make_provider
from app.core.errors import AppError
from app.core.meta import DemoMeta, read_meta, require_ready
from app.core.models import ApiModel
from app.core.query import Pipeline, Timings, run_pipeline, to_json
from app.core.settings import get_settings
from app.modules.dynamo_graph import pipelines as p
from app.modules.dynamo_graph import writes
from app.modules.dynamo_graph.catalog import QUERIES, evaluate
from app.modules.dynamo_graph.indexes import AICP_VECTOR, TALENT_SEARCH
from app.modules.dynamo_graph.seed import AICP, TALENT

MODULE_SLUG = "dynamo-graph"
router = APIRouter(prefix=f"/api/{MODULE_SLUG}", tags=[MODULE_SLUG])


def module_seeded(meta: DemoMeta | None) -> bool:
    return bool(meta and meta.seeded_at and MODULE_SLUG in meta.modules)


async def require_module_ready(meta: DemoMeta = Depends(require_ready)) -> DemoMeta:
    """The kit's readiness is per database; this module's data may predate it."""
    if not module_seeded(meta):
        raise AppError(
            "MODULE_NOT_SEEDED",
            "The DynamoDB → MongoDB data has not been seeded yet.",
            "Run Seed Database and Create Indexes on Setup again.",
            409,
        )
    return meta


IdStr = Annotated[str, StringConstraints(min_length=1, max_length=200)]


class _Inputs(BaseModel):
    model_config = {"extra": "forbid"}


class T1In(_Inputs):
    graph: IdStr
    subject: IdStr
    predicate: IdStr


class T2In(_Inputs):
    predicate: IdStr
    object: IdStr
    graph: str | None = Field(default=None, max_length=200)


class T3In(_Inputs):
    start: IdStr
    max_depth: int = Field(default=3, ge=1, le=5)


class T4In(_Inputs):
    costcenter: IdStr


class T5In(_Inputs):
    area: IdStr


class T6In(_Inputs):
    word: str = Field(min_length=1, max_length=100)


class NoIn(_Inputs):
    pass


class A1In(_Inputs):
    entity: IdStr


class A2In(_Inputs):
    object_id: IdStr


class A3In(_Inputs):
    subject: IdStr


class A5In(_Inputs):
    base: str = Field(default="v1.02", min_length=1, max_length=50)
    live: str = Field(default="LIVE", min_length=1, max_length=50)


BUILDERS: dict[str, tuple[type[_Inputs], str, Any]] = {
    "T1": (T1In, TALENT, lambda i: p.t1_children(i.graph, i.subject, i.predicate)),
    "T2": (T2In, TALENT, lambda i: p.t2_reverse(i.predicate, i.object, i.graph)),
    "T3": (T3In, TALENT, lambda i: p.t3_subtree(i.start, i.max_depth)),
    "T4": (T4In, TALENT, lambda i: p.t4_path_up(i.costcenter)),
    "T5": (T5In, TALENT, lambda i: p.t5_lines_github(i.area)),
    "T6": (T6In, TALENT, lambda i: p.t6_label_search(i.word)),
    "T7": (NoIn, TALENT, lambda i: p.t7_costcentres_per_business()),
    "A1": (A1In, AICP, lambda i: p.a1_entity_facts(i.entity)),
    "A2": (A2In, AICP, lambda i: p.a2_pointing_at(i.object_id)),
    "A3": (A3In, AICP, lambda i: p.a3_reified_about(i.subject)),
    "A4": (NoIn, AICP, lambda i: p.a4_claims()),
    "A5": (A5In, AICP, lambda i: p.a5_snapshot_diff(i.base, i.live)),
}
SEARCH_INDEX_FOR = {"T6": (TALENT, TALENT_SEARCH)}
# $facet always emits a summary document; these counts tell an empty answer apart.
EMPTY_WHEN_ZERO = {"T3": "total_nodes", "T6": "distinct_entities"}


class CheckResult(ApiModel):
    path: str
    mode: str
    expected: Any
    actual: Any
    ok: bool


class QuerySpecOut(ApiModel):
    id: str
    group: str
    title: str
    pattern: str
    dynamo_today: str
    defaults: dict[str, Any]
    ideal: list[CheckResult]


class Catalog(ApiModel):
    scale: int
    seeded: bool
    queries: list[QuerySpecOut]


class QueryRequest(BaseModel):
    inputs: dict[str, Any] = {}
    explain: bool = False


class QueryResult(ApiModel):
    results: list[dict[str, Any]]
    pipeline: Pipeline
    timings: Timings
    explain: dict[str, Any] | None = None
    scale: int
    match: bool | None = None
    checks: list[CheckResult] = []
    note: str | None = None


class SemanticRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=5, ge=1, le=20)
    explain: bool = False


class ReplaceRequest(BaseModel):
    graph: IdStr
    subject: IdStr
    predicate: IdStr
    old_object: IdStr
    new_object: IdStr
    simulate_failure: bool = False


class ReplaceResult(ApiModel):
    committed: bool
    message: str
    ms: float
    objects_after: list[str]


class ReloadRequest(BaseModel):
    graph: Literal["talent:hierarchy", "talent:costcenters", "talent:github", "talent:metadata"]


class ReloadStep(ApiModel):
    name: str
    op: str
    kind: Literal["app", "aggregate", "write", "txn"]
    in_transaction: bool
    command: dict[str, Any] | list[dict[str, Any]]
    docs: int | None = None
    ms: float
    result: str


class ReloadResult(ApiModel):
    graph: str
    deleted: int
    inserted: int
    ms: float
    total_ms: float
    steps: list[ReloadStep]


def _parse_inputs(model: type[_Inputs], raw: dict[str, Any]) -> _Inputs:
    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        msg = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
        raise AppError("VALIDATION_ERROR", msg, "Check the query inputs.", 422) from None


async def _require_search_index(db: AsyncDatabase, coll: str, name: str) -> None:
    info = await (await db[coll].list_search_indexes(name)).to_list()
    if not info or info[0].get("status") != "READY":
        status = info[0].get("status", "missing") if info else "missing"
        raise AppError(
            "INDEX_NOT_READY",
            f"Search index '{name}' is {status.lower()}.",
            "Wait for Create Indexes on Setup to finish.",
            409,
        )


@router.get("/catalog", response_model=Catalog)
async def catalog(db: AsyncDatabase = Depends(get_db)) -> Catalog:
    return Catalog(
        scale=await writes.current_scale(db),
        seeded=module_seeded(await read_meta(db)),
        queries=[
            QuerySpecOut(
                id=q.id,
                group=q.group,
                title=q.title,
                pattern=q.pattern,
                dynamo_today=q.dynamo_today,
                defaults=q.defaults,
                ideal=[
                    CheckResult(path=c.path, mode=c.mode, expected=c.expected, actual=None,
                                ok=False)
                    for c in q.checks
                ],
            )
            for q in QUERIES.values()
        ],
    )  # fmt: skip


@router.post(
    "/query/{query_id}", response_model=QueryResult, dependencies=[Depends(require_module_ready)]
)
async def run_query(
    query_id: str, req: QueryRequest, db: AsyncDatabase = Depends(get_db)
) -> QueryResult:
    if query_id not in BUILDERS:
        raise AppError("UNKNOWN_QUERY", f"Unknown query '{query_id}'.", "Use T1–T7 or A1–A5.", 404)
    model, coll, build = BUILDERS[query_id]
    inputs = _parse_inputs(model, req.inputs)
    if query_id in SEARCH_INDEX_FOR:
        await _require_search_index(db, *SEARCH_INDEX_FOR[query_id])
    run = await run_pipeline(db[coll], build(inputs), explain=req.explain)
    results = to_json(run.results)
    scale = await writes.current_scale(db)

    spec = QUERIES[query_id]
    is_default = inputs.model_dump() == model.model_validate(spec.defaults).model_dump()
    checks: list[CheckResult] = []
    match: bool | None = None
    if scale == 1 and is_default:
        doc = results[0] if results else {}
        for c in spec.checks:
            ok, actual = evaluate(c, doc)
            checks.append(
                CheckResult(path=c.path, mode=c.mode, expected=c.expected, actual=actual, ok=ok)
            )
        match = all(c.ok for c in checks)
    return QueryResult(
        results=results,
        pipeline=run.pipeline,
        timings=Timings(server_ms=run.server_ms),
        explain=run.explain,
        scale=scale,
        match=match,
        checks=checks,
        note=None if _has_answer(query_id, results) else "No match for these inputs.",
    )


def _has_answer(query_id: str, results: list[dict[str, Any]]) -> bool:
    if not results:
        return False
    field = EMPTY_WHEN_ZERO.get(query_id)
    return field is None or bool(results[0].get(field))


@router.post("/semantic", response_model=QueryResult, dependencies=[Depends(require_module_ready)])
async def semantic(req: SemanticRequest, db: AsyncDatabase = Depends(get_db)) -> QueryResult:
    await _require_search_index(db, AICP, AICP_VECTOR)
    start = time.perf_counter()
    [vector] = await make_provider(get_settings()).embed([req.text], "query")
    embed_ms = round((time.perf_counter() - start) * 1000, 2)
    run = await run_pipeline(db[AICP], p.semantic_search(vector, req.limit), explain=req.explain)
    results = to_json(run.results)
    return QueryResult(
        results=results,
        pipeline=run.pipeline,
        timings=Timings(server_ms=run.server_ms, embed_ms=embed_ms),
        explain=run.explain,
        scale=await writes.current_scale(db),
        note=None if results else "No match.",
    )


@router.post(
    "/writes/replace-quad",
    response_model=ReplaceResult,
    dependencies=[Depends(require_module_ready)],
)
async def replace_quad(req: ReplaceRequest, db: AsyncDatabase = Depends(get_db)) -> ReplaceResult:
    return ReplaceResult(**await writes.replace_quad(db, **req.model_dump()))


@router.post(
    "/writes/reload-graph",
    response_model=ReloadResult,
    dependencies=[Depends(require_module_ready)],
)
async def reload_graph(req: ReloadRequest, db: AsyncDatabase = Depends(get_db)) -> ReloadResult:
    return ReloadResult(**await writes.reload_graph(db, req.graph))

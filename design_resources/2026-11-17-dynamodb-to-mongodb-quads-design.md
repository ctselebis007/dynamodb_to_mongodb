# DynamoDB → MongoDB Quad Store Demo: Design

*Date: 2026-11-17 · Status: Approved for implementation planning · Inputs: [Sample_Queries_Criteria.md](./Sample_Queries_Criteria.md) and the workbook HTML exports in this folder*

## 1. Goal and scope

Build one interactive **Demo Kit module** (`dynamo_graph`) that loads the synthetic DynamoDB data into MongoDB Atlas. It answers each of the 12 sample queries (T1–T7, A1–A5) in **one call**, shows the pipeline, timings and `explain()`, and compares the actual result with the ideal answer in the criteria doc.

| In scope | Out of scope (YAGNI) |
|---|---|
| Both tables: `talent-rdf-quads`, `aicp-quads` | The "two more quad stores" (~487K quads, unconfirmed) |
| Workbook volume (`scale = 1`) and a synthetic ~300K-quad scale-up (`scale = 20`) | Multi-million stress data |
| Atlas Search for T6, plus a bonus Vector Search over aicp labels/comments | Live DynamoDB connection, CDC/sync |
| Write demos: atomic quad replace, timed named-graph reload | Narrative edits that create new HIST/LIVE revisions |
| | Production staged-load-and-swap for large graph reloads |

## 2. Design decisions

| Decision | Choice | Why |
|---|---|---|
| Deliverable | Demo module in this kit (API + UI) | Shows each query live with pipeline and timings |
| Data source | One-time converter: HTML sheets → JSON fixtures in the repo | Deterministic, fast seeding; no dependency on the DynamoDB JSON export |
| Talent model | **One document per quad**, predicate-filtered `$graphLookup` | Same grain as DynamoDB; any-predicate reverse lookups; per-graph reload is trivial; new sources need an extractor only |
| Rejected | Entity documents with embedded edges | `$graphLookup` can't choose which embedded edge to follow (upward `belongsTo*` and `rdf:type` edges leak in); per-graph refresh becomes scattered partial updates |
| Rejected | Quads + derived `nodes` collection | Two stores to keep in sync for little gain at this size |
| AICP model | **One document per DynamoDB item**, `facts` kept nested (customer requirement) | Matches the source; multikey indexes cover nested reverse lookups |

## 3. Architecture

```
api/app/modules/dynamo_graph/
  convert.py     one-time converter: workbook HTML sheets -> fixtures/*.json.gz
  seed.py        collections(), generate(rng): load fixtures; optional scale-up; embed_fields
  indexes.py     regular(), search(), vector(dims)
  pipelines.py   pure builders, one per query (T1–T7, A1–A5, semantic)
  catalog.py     query metadata, default inputs, ideal answers, compare helper
  writes.py      atomic quad replace, named-graph reload
  router.py      /api/dynamo-graph/{catalog, query/{id}, semantic, writes/*}
  tests/
web/src/modules/dynamo_graph/
  index.tsx      Tabs: Talent | AICP | Writes | Semantic. One QueryCard per query.
```

Each **query card** shows pre-filled inputs, the ideal answer, the actual result, a ✅/❌ match badge (`scale = 1` only), a "DynamoDB today: N calls / MongoDB: 1 call" chip, and the kit's Query Drawer (pipeline, server ms, `explain()`).

**Scale-up** (`scale = 20`, ~313K quads): clones the talent graph with suffixed ids (`business:REALGAR_SHOAL~07`), so shape and fan-out stay realistic. aicp is not scaled.

## 4. Data model

### `talent_quads`: one document per quad (15,651)

```js
{ _id: ObjectId, graph: "talent:costcenters", subject: "costcenter:9900228084",
  predicate: "belongsToLine", object: "line:REALGAR_SHOAL_ZIRCON_SAVANNA_BASIN_BASALT",
  object_kind: "iri",            // "literal" for rdfs:label / costCenterId values
  subject_label: "9900228084", object_label: "TALUS-Basin Magnetite & Hoodoo" }
```

`PK`, `SK`, `GSI1PK` and `GSI1SK` are dropped because they're concatenations of the fields above. `object_kind` is derived by the converter. T6 needs it because `rdfs:label` quads carry the label text as their object.

| Index | Serves |
|---|---|
| `{graph:1, predicate:1, object:1, subject:1}` unique | Quad identity, idempotent load, per-graph reload, T7 (prefix `{graph, predicate}`) |
| `{subject:1, predicate:1, object:1}` | T1, T4, T5, `$graphLookup` hops |
| `{object:1, predicate:1}` | T2 and any reverse lookup, any predicate (replaces the GSI and the Scan) |
| Atlas Search `talent_labels` | T6: `subject_label`, `object_label` (standard analyzer), `object_kind` as token |

### `aicp_items`: one document per DynamoDB item (818)

```js
{ _id: "QUADS#LIVE|ENTITY#K06", pk: "QUADS#LIVE", sk: "ENTITY#K06", kind: "entity", id: "K06",
  iri: "https://example.org/mobilesec/id/K06",
  facts:   [{ graph, predicate, object: { kind, id | value, datatype, lang } }],
  reifies: { graph, triple: { subject: { id }, predicate, object: { kind, id | value } } },
  itemVersion: 0, liveRevision: 0, ...,
  search_text: "label + comment values"  // derived, for embeddings only
}
```

DynamoDB types are unmarshalled: N → number, BOOL → bool, NULL → `null`, a blank cell means the attribute is absent. Nested `facts`, `reifies`, `triple`, `terms` and `changes` stay as stored. The vocabulary stays embedded in its META item (`terms`, ~27 KB).

| Index | Serves |
|---|---|
| `{pk:1, sk:1}` unique | A1 point read; A4 (`sk` prefix `CLAIM#`); A5 (`HIST#`, `ENTITY#`) |
| `{pk:1, "facts.object.id":1}` multikey | A2 reverse lookup inside nested facts |
| `{pk:1, "reifies.triple.subject.id":1}` | A3 triple-term lookup (232 items carry `reifies`) |
| Vector Search `aicp_semantic` on `embedding` (filter `pk`) | Bonus semantic search |

### Answers to the customer's open questions (criteria doc §6)

1. **T3 crosses graphs.** Restrict `$graphLookup` by **predicate**, not graph (`hasArea`, `hasLine`, `hasCostCenter`). Verified on the workbook: 18 / 36 / 148 links, 197 nodes, 143 distinct cost centres.
2. **Bare ids vs IRIs.** Don't normalize for Phase 1. Facts reference the bare `id`, which every entity carries and which is indexed. Full IRIs can be rebuilt from the META `namespaces` map.
3. **Snapshots.** Use one collection with `pk` as the snapshot discriminator. One collection per snapshot makes A5 a cross-collection job and grows the collection list without limit.
4. **Indexing triple terms.** Use a multikey index on `reifies.triple.subject.id` (extend with predicate/object only if new queries need them).

## 5. Query pipelines (one `aggregate` each)

| # | Pipeline | DynamoDB today |
|---|---|---|
| T1 | `$match {graph, subject, predicate}` → `$group` objects | 1 Query |
| T2 | `$match {object, predicate}` (graph optional) → `$group` subjects | GSI Query or Scan |
| **T3** | `$match {subject: start}` + `$limit 1` → `$graphLookup {from: talent_quads, startWith: start, connectFromField: "object", connectToField: "subject", restrictSearchWithMatch: {predicate: {$in: [...]}}, maxDepth: 2–4, depthField: "depth"}` → `$unwind` → `$group` by `object` with `$min: depth` → `$facet` per-depth counts and node list | 55 Queries |
| T4 | `$match {graph, subject, predicate: /^belongsTo/}` → `$lookup` the line's `rdfs:label` in `talent:metadata` → `$group` into one row | 1 Query |
| T5 | `$match` area `hasLine` → `$lookup` (sub-pipeline: `subject = $$line`, `predicate: hasGitHubCostCenter`) → `$project` | 23 Queries |
| T6 | `$search` compound `should` text on both labels → keep the matching side, `object_kind: "iri"` only → `$group` distinct entity → `$facet` by type prefix | Full Scan |
| T7 | `$match {graph: talent:costcenters, predicate: belongsToBusiness}` → `$sortByCount: "$object"` → `$facet {top5, total}` | Scan + code |
| A1 | `$match {pk: "QUADS#LIVE", sk: "ENTITY#<id>"}` → `$unwind: facts` → `$group` by predicate local name (derived in-pipeline) | 1 GetItem |
| A2 | `$match {pk, "facts.object.id": X}` → `$unwind` → re-`$match` → `$group` | Scan + code |
| A3 | `$match {pk, "reifies.triple.subject.id": X}` → `$project` triple, graph, confidence and evidence count from the reifier's facts | Scan + code |
| A4 | `$match {sk: /^CLAIM#/}` → `$project` triple, statedBy, agreedBy, contestedBy, resolutionState | 1 Query |
| A5 | `$match {pk: "QUADS#LIVE", sk: /^ENTITY#/, itemVersion: {$gt: 0}}` → `$lookup` same `sk` in `QUADS#v1.02` (fact counts) → `$lookup` HIST rows by `entityId` → `$project` changes | 2 GetItems + Query + code |
| Bonus | `$vectorSearch` on `aicp_items` (filter `pk: QUADS#LIVE`) → `$project` id, label, score | n/a |

### Writes (`writes.py`)

- **Atomic quad replace**: `with_transaction` runs `delete_one(old)` + `insert_one(new)`, then re-runs T4 to show the effect. A "simulate failure" toggle raises inside the callback to prove the rollback.
- **Named-graph reload**: inside one transaction, `delete_many({graph})` + batched `insert_many` from fixtures, timed against the 15K-docs-in-5-minutes target. Readers see the old graph until commit. Only enabled at `scale = 1`.

## 6. Error handling

| Situation | Behavior |
|---|---|
| Not seeded/indexed | `require_ready` → 409, and the UI points to Setup |
| Search/Vector index not READY | 409 on T6/semantic only; other cards keep working |
| Input id not found | 200 with empty results and `note: "no match"` |
| Bad input | 422 (Pydantic). Ids are exact-match only, never put into `$regex`. T6 input goes to `$search` only |
| Result ≠ ideal | ❌ badge with an expected-vs-actual diff (`scale = 1`); "n/a (scaled)" otherwise |
| Atomic replace conflict | Transaction aborts → 409 with the reason; driver retries transient errors |
| Large reload | Disabled at `scale = 20` (60s transaction limit). The production approach (staged load + swap) is documented, not built |
| Fixture missing/corrupt | Seed fails fast and names the file. No silent partial seed |
| Converter drift | Converter asserts the README row counts (15,651 / 818 / 4,974 / 239) and stops on mismatch |

## 7. Testing

1. **Converter** (offline): row counts, type unmarshalling, `object_kind` tagging.
2. **Pipeline builders** (no DB, part of `npm test`): stage shape. Examples: T3 restricts on `predicate`, not `graph`; T2 matches on `object` first.
3. **Golden answers** (`pytest -m atlas`, needs `MONGODB_URI_TEST`): seed `scale = 1` and assert T1 = 18, T2 = 220, T3 = 18/36/148/143 (197 nodes), T4 path + label, T5 = 22/22, T6 = 14 (4 area, 10 line), T7 top 5 + 20 businesses, A1 = 21, A2 = 24/24, A3 = 5, A4 = 7, A5 = 2 entities / 4 changes. `explain()` shows `IXSCAN` for T1, T2, A2, A3. Write demos: commit, rollback, and reload counts.
4. **Scale smoke** (manual): `scale = 20`; record p95 of T3, T6, A2 over 20 runs (recorded, not pass/fail).
5. **Web** (Vitest): query card renders expected vs actual and the match badge.

## 8. Notes for later phases

- The per-request budgets (<100–500 ms, hundreds of readers) don't conflict with this model. Point and reverse lookups are single-index reads; T3 is bounded by `maxDepth` and predicate filters.
- Snapshot retention (criteria doc "[CONFIRM]") can use the Archive pattern on `pk` without changing the schema.

## 9. Implementation notes (changes from the original design)

- **Converter location**: it lives at `api/app/modules/dynamo_graph/convert.py` instead of `scripts/`, so it shares the API's Python environment, tests and lint.
- **Placeholder cells**: the items sheet holds placeholders for nested lists (`"7 facts (see sheet aicp-quads facts)"`, `"145 terms (see sheet aicp-quads vocabulary)"`). The converter rebuilds `facts` (in fact order, with `reifiedBy` and nested triple terms) and `terms` from their own sheets. It reads top-level DynamoDB types from the Attribute dictionary sheet.
- **Unique index order**: the quad identity index is `{graph, predicate, object, subject}`, so its `{graph, predicate}` prefix also serves T7.
- **`expected.py` → `catalog.py`**: the file also holds query metadata and default inputs.
- **T6**: `$search` on `subject_label`, then `$unionWith` a second `$search` on `object_label`, filtered to `object_kind: "iri"`. Token matching gives the expected 14 entities.
- **A3**: confidence and evidence come from the reifier's own `…/confidence` and `…/evidence` facts, as the criteria doc specifies.
- **Module readiness**: the kit's readiness flag is per database. Endpoints also return 409 `MODULE_NOT_SEEDED` until `dynamo-graph` appears in `_demo_meta.modules`.
- **Scale**: set with the `DYNAMO_GRAPH_SCALE` environment variable (1–50) when starting the API.
- **Verified**: the golden-answer test (`pytest -m atlas`) passes all 12 queries, shows IXSCAN for T1/T2/A2/A3, and passes the commit, rollback and reload checks.

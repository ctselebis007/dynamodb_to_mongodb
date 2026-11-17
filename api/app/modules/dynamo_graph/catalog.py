"""The 12 sample queries: inputs, DynamoDB baseline, and ideal answers from
Sample_Queries_Criteria.md, plus a comparison helper for the match badge."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Mode = Literal["eq", "includes"]


@dataclass(frozen=True)
class Check:
    path: str
    expected: Any
    mode: Mode = "eq"


@dataclass(frozen=True)
class QuerySpec:
    id: str
    group: Literal["talent", "aicp"]
    title: str
    pattern: str
    dynamo_today: str
    defaults: dict[str, Any]
    checks: list[Check] = field(default_factory=list)


def _c(path: str, expected: Any, mode: Mode = "eq") -> Check:
    return Check(path, expected, mode)


QUERIES: dict[str, QuerySpec] = {
    q.id: q
    for q in [
        QuerySpec(
            "T1", "talent", "All direct children of one business", "Point read", "1 Query",
            {"graph": "talent:hierarchy", "subject": "business:REALGAR_SHOAL",
             "predicate": "hasArea"},
            [
                _c("count", 18),
                _c("objects", ["area:REALGAR_SHOAL_BARITE_GLACIER",
                               "area:REALGAR_SHOAL_BAUXITE_COVE",
                               "area:REALGAR_SHOAL_CANYON_BASALT",
                               "area:REALGAR_SHOAL_FEN_CAVERN",
                               "area:REALGAR_SHOAL_FLUORITE_BOG"], "includes"),
            ],
        ),
        QuerySpec(
            "T2", "talent", "All cost centres that belong to one area", "Reverse lookup",
            "1 Query on the predicate GSI; a Scan if the predicate is unknown",
            {"graph": "talent:costcenters", "predicate": "belongsToArea",
             "object": "area:WOLFRAMITE_PRAIRIE"},
            [
                _c("count", 220),
                _c("subjects", ["costcenter:9900354667", "costcenter:9901457396",
                                "costcenter:9901521554", "costcenter:9901662592",
                                "costcenter:9902111636"], "includes"),
            ],
        ),
        QuerySpec(
            "T3", "talent", "Whole subtree under one business, 3 levels", "Multi-hop traversal",
            "55 Queries, one per node",
            {"start": "business:REALGAR_SHOAL", "max_depth": 3},
            [
                _c("links_by_depth.1", 18),
                _c("links_by_depth.2", 36),
                _c("links_by_depth.3", 148),
                _c("nodes_by_depth.3", 143),
                _c("total_nodes", 197),
                _c("nodes", [{"node": "area:REALGAR_SHOAL_PLAIN", "depth": 1},
                             {"node": "line:REALGAR_SHOAL_PLAIN_TALUS_HOODOO", "depth": 2}],
                   "includes"),
            ],
        ),
        QuerySpec(
            "T4", "talent", "Path from one cost centre up to its business", "Upward traversal",
            "1 Query",
            {"costcenter": "costcenter:9900228084"},
            [
                _c("line", "line:REALGAR_SHOAL_ZIRCON_SAVANNA_BASIN_BASALT"),
                _c("area", "area:REALGAR_SHOAL_ZIRCON_SAVANNA"),
                _c("business", "business:REALGAR_SHOAL"),
                _c("line_label", "TALUS-Basin Magnetite & Hoodoo"),
            ],
        ),
        QuerySpec(
            "T5", "talent", "Lines under one area with their GitHub cost centre",
            "Cross-graph join", "23 Queries",
            {"area": "area:BUTTE_MORAINE_ESKER"},
            [
                _c("lines", 22),
                _c("lines_with_github_cost_centre", 22),
                _c("rows", [
                    {"line": "line:BUTTE_MORAINE_ESKER_WOLFRAMITE_702",
                     "github": "ghcostcenter:GH_QUARTZ_VARISCITE"},
                    {"line": "line:BUTTE_MORAINE_ESKER_BUTTE_GRANITE",
                     "github": "ghcostcenter:GH_QUARTZ_VARISCITE"},
                    {"line": "line:BUTTE_MORAINE_ESKER_REALGAR_TOMBOLO",
                     "github": "ghcostcenter:GH_QUARTZ_VARISCITE"},
                    {"line": "line:BUTTE_MORAINE_ESKER_SODALITE_CAVERN",
                     "github": "ghcostcenter:GH_QUARTZ_VARISCITE"},
                ], "includes"),
            ],
        ),
        QuerySpec(
            "T6", "talent", "Find entities whose label contains a word", "Text search",
            "Full Scan of 15,651 items",
            {"word": "LAGOON"},
            [
                _c("distinct_entities", 14),
                _c("by_type", {"area": 4, "line": 10}),
                _c("entities", ["area:GRANITE_MALACHITE_LAGOON", "area:GYPSUM_LAGOON",
                                "area:REALGAR_SHOAL_ORPIMENT_LAGOON",
                                "area:SODALITE_ESKER_BAUXITE_LAGOON"], "includes"),
            ],
        ),
        QuerySpec(
            "T7", "talent", "Cost centres per business, top 5", "Aggregation",
            "Full Scan + code",
            {},
            [
                _c("top_5", [
                    {"business": "business:WOLFRAMITE", "cost_centres": 1198},
                    {"business": "business:REALGAR_SHOAL", "cost_centres": 143},
                    {"business": "business:BUTTE_MORAINE", "cost_centres": 136},
                    {"business": "business:GRANITE", "cost_centres": 70},
                    {"business": "business:WADI", "cost_centres": 66},
                ]),
                _c("businesses_total", 20),
            ],
        ),
        QuerySpec(
            "A1", "aicp", "Every fact about one entity in the LIVE snapshot",
            "Point read, nested", "1 GetItem",
            {"entity": "S-sso_claude_ai_enforced"},
            [
                _c("facts", 21),
                _c("by_predicate.type",
                   ["https://example.org/mobilesec/ontology/LLMVendorControl"]),
                _c("by_predicate.enforcedBy", ["ClaudeAdminConsole"]),
                _c("by_predicate.measuredOn", ["2026-06-19", "2026-04-27"]),
                _c("by_predicate.conflictsWith", ["claim-person05-sso-blocks-google"]),
                _c("by_predicate.inventoryTool", ["33"]),
            ],
        ),
        QuerySpec(
            "A2", "aicp", "Which entities point at one entity", "Reverse lookup, nested",
            "Scan of the snapshot + code",
            {"object_id": "ClaudeAdminConsole"},
            [
                _c("facts_pointing_here", 24),
                _c("distinct_subjects", 24),
                _c("by_predicate", {"enforcedBy": 24}),
                _c("rows", [{"subject": s, "predicate": "enforcedBy"} for s in
                            ["K01", "K06", "S-allowed_invite_domains",
                             "S-claude_code_trusted_devices"]], "includes"),
            ],
        ),
        QuerySpec(
            "A3", "aicp", "Every reified statement about one subject, with its annotations",
            "RDF 1.2 reifiers", "Scan + code",
            {"subject": "K06"},
            [
                _c("reifiers", 5),
                _c("rows", [
                    {"reifier": "assess-q01-person05-sso-claim", "graph": "inferred",
                     "triple": ["K06", "blocks", "GoogleSignIn"], "confidence": "High",
                     "evidence": 6},
                    {"reifier": "claim-person05-sso-blocks-google",
                     "graph": "meeting-20260702", "triple": ["K06", "blocks", "GoogleSignIn"],
                     "confidence": None, "evidence": 1},
                    {"reifier": "rf-5c0362397f57", "graph": "inferred",
                     "triple": ["K06", "granularity", "OrgWide"], "confidence": "High",
                     "evidence": 0},
                    {"reifier": "rf-2eebe635da79", "graph": "inferred",
                     "triple": ["K06", "identifiedAs", "V-RequireSSOForClaude"],
                     "confidence": "High", "evidence": 0},
                ], "includes"),
            ],
        ),
        QuerySpec(
            "A4", "aicp", "All claims with who stated, agreed or contested them",
            "RDF 1.2 claims", "1 Query",
            {},
            [
                _c("claims", 7),
                _c("rows", [
                    {"id": "assess-q01-person05-sso-claim", "pk": "QUADS#v1.02",
                     "triple": ["K06", "blocks", "GoogleSignIn"], "statedBy": [],
                     "agreedBy": [], "contestedBy": [],
                     "resolutionState": "ResolvedPartlySupported"},
                    {"id": "claim-person08-android-chrome", "pk": "QUADS#v1.02",
                     "triple": ["ClaudeAI-AndroidWorkProfileChrome",
                                "allowsCorporateDataUpload", "true"],
                     "statedBy": ["Person-08"], "agreedBy": [], "contestedBy": [],
                     "resolutionState": "Unresolved"},
                    {"id": "claim-person08-mobile-web-upload", "pk": "QUADS#v1.02",
                     "triple": ["ClaudeAI-MobileBrowser", "allowsCorporateDataUpload", "true"],
                     "statedBy": ["Person-08"], "agreedBy": [], "contestedBy": ["Person-02"],
                     "resolutionState": "Unresolved"},
                ], "includes"),
            ],
        ),
        QuerySpec(
            "A5", "aicp", "What changed between snapshot v1.02 and LIVE", "Version diff",
            "2 GetItems + history Query + code",
            {"base": "v1.02", "live": "LIVE"},
            [
                _c("changed_entities", 2),
                _c("rows", [
                    {"entity": "A4", "itemVersion": 2, "liveRevision": 4, "facts_base": 10,
                     "facts_live": 10, "changes": [
                         {"history": "00000003", "field": "inventoryTools", "op": "set",
                          "before": [], "after": ["33"]},
                         {"history": "00000004", "field": "inventoryTools", "op": "set",
                          "before": ["33"], "after": []},
                     ]},
                    {"entity": "S-ip_allowlist", "itemVersion": 2, "liveRevision": 2,
                     "facts_base": 19, "facts_live": 19, "changes": [
                         {"history": "00000001", "field": "confidence", "op": "replace",
                          "before": "High", "after": "Medium"},
                         {"history": "00000002", "field": "confidence", "op": "replace",
                          "before": "Medium", "after": "High"},
                     ]},
                ], "includes"),
            ],
        ),
    ]
}  # fmt: skip

_MISSING = object()


def resolve(doc: Any, path: str) -> Any:
    for part in path.split("."):
        if isinstance(doc, dict) and part in doc:
            doc = doc[part]
        else:
            return _MISSING
    return doc


def _subset(expected: Any, actual: Any) -> bool:
    """Dicts match when every expected key matches; other values must be equal."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        return all(k in actual and _subset(v, actual[k]) for k, v in expected.items())
    if isinstance(expected, list) and isinstance(actual, list):
        return len(expected) == len(actual) and all(map(_subset, expected, actual))
    return expected == actual


def evaluate(check: Check, doc: Any) -> tuple[bool, Any]:
    actual = resolve(doc, check.path)
    if actual is _MISSING:
        return False, None
    if check.mode == "includes":
        ok = isinstance(actual, list) and all(
            any(_subset(e, a) for a in actual) for e in check.expected
        )
        return ok, f"{len(actual)} items" if isinstance(actual, list) else actual
    return _subset(check.expected, actual), actual

"""Pure pipeline builders, one per sample query. Each returns a single summary document
shaped like the ideal answer in Sample_Queries_Criteria.md."""

from __future__ import annotations

from typing import Any

from app.core.query import Pipeline
from app.modules.dynamo_graph.indexes import AICP_VECTOR, TALENT_SEARCH
from app.modules.dynamo_graph.seed import AICP, TALENT

LIVE = "QUADS#LIVE"
T3_PREDICATES = ["hasArea", "hasLine", "hasCostCenter"]
UPWARD_PREDICATES = {
    "belongsToLine": "line",
    "belongsToArea": "area",
    "belongsToBusiness": "business",
}


def _local(expr: Any) -> dict[str, Any]:
    """Local name of an IRI (text after the last / or #); bare ids pass through unchanged."""
    return {
        "$getField": {
            "field": "match",
            "input": {"$regexFind": {"input": expr, "regex": "[^/#]+$"}},
        }
    }


def _term_value(term: str) -> dict[str, Any]:
    """`{kind: iri, id}` -> local name of id; `{kind: literal, value}` -> value."""
    return {"$ifNull": [_local(f"{term}.id"), f"{term}.value"]}


def _counts_object(expr: str) -> dict[str, Any]:
    """$sortByCount output -> {value: count}."""
    return {
        "$arrayToObject": {"$map": {"input": expr, "in": {"k": "$$this._id", "v": "$$this.count"}}}
    }


def _sorted(expr: Any) -> dict[str, Any]:
    return {"$sortArray": {"input": expr, "sortBy": 1}}


# ---------- talent-rdf-quads ----------


def t1_children(graph: str, subject: str, predicate: str) -> Pipeline:
    return [
        {"$match": {"graph": graph, "subject": subject, "predicate": predicate}},
        {"$group": {"_id": None, "objects": {"$push": "$object"}}},
        {
            "$project": {
                "_id": 0,
                "subject": {"$literal": subject},
                "predicate": {"$literal": predicate},
                "count": {"$size": "$objects"},
                "objects": _sorted("$objects"),
            }
        },
    ]


def t2_reverse(predicate: str, object_: str, graph: str | None = None) -> Pipeline:
    match: dict[str, Any] = {"object": object_, "predicate": predicate}
    if graph:
        match["graph"] = graph
    return [
        {"$match": match},
        {"$group": {"_id": None, "subjects": {"$addToSet": "$subject"}}},
        {
            "$project": {
                "_id": 0,
                "object": {"$literal": object_},
                "predicate": {"$literal": predicate},
                "count": {"$size": "$subjects"},
                "subjects": _sorted("$subjects"),
            }
        },
    ]


def t3_subtree(start: str, max_depth: int = 3, predicates: list[str] | None = None) -> Pipeline:
    """Edges are followed by predicate, not graph: hop 3 lives in talent:costcenters."""
    return [
        {"$match": {"subject": start}},
        {"$limit": 1},
        {
            "$graphLookup": {
                "from": TALENT,
                "startWith": "$subject",
                "connectFromField": "object",
                "connectToField": "subject",
                "as": "edges",
                "maxDepth": max_depth - 1,
                "depthField": "hop",
                "restrictSearchWithMatch": {"predicate": {"$in": predicates or T3_PREDICATES}},
            }
        },
        {"$unwind": "$edges"},
        {"$replaceWith": "$edges"},
        {
            "$facet": {
                "links": [{"$group": {"_id": {"$add": ["$hop", 1]}, "n": {"$sum": 1}}}],
                "nodes": [
                    {
                        "$group": {
                            "_id": "$object",
                            "depth": {"$min": {"$add": ["$hop", 1]}},
                            "parent": {"$min": "$subject"},
                        }
                    },
                    {"$sort": {"depth": 1, "_id": 1}},
                    {"$project": {"_id": 0, "node": "$_id", "depth": 1, "parent": 1}},
                ],
            }
        },
        {
            "$project": {
                "start": {"$literal": start},
                "links_by_depth": {
                    "$arrayToObject": {
                        "$map": {
                            "input": {"$sortArray": {"input": "$links", "sortBy": {"_id": 1}}},
                            "in": {"k": {"$toString": "$$this._id"}, "v": "$$this.n"},
                        }
                    }
                },
                "nodes_by_depth": {
                    "$arrayToObject": {
                        "$map": {
                            "input": {"$range": [1, max_depth + 1]},
                            "as": "d",
                            "in": {
                                "k": {"$toString": "$$d"},
                                "v": {
                                    "$size": {
                                        "$filter": {
                                            "input": "$nodes",
                                            "cond": {"$eq": ["$$this.depth", "$$d"]},
                                        }
                                    }
                                },
                            },
                        }
                    }
                },
                "total_nodes": {"$size": "$nodes"},
                "nodes": 1,
            }
        },
    ]


def t4_path_up(costcenter: str) -> Pipeline:
    return [
        {
            "$match": {
                "graph": "talent:costcenters",
                "subject": costcenter,
                "predicate": {"$in": list(UPWARD_PREDICATES)},
            }
        },
        {
            "$group": {
                "_id": "$subject",
                "pairs": {"$push": {"k": "$predicate", "v": "$object"}},
            }
        },
        {"$replaceWith": {"$mergeObjects": [{"costcenter": "$_id"}, {"$arrayToObject": "$pairs"}]}},
        {"$project": {"costcenter": 1, **{v: f"${k}" for k, v in UPWARD_PREDICATES.items()}}},
        {
            "$lookup": {
                "from": TALENT,
                "localField": "line",
                "foreignField": "subject",
                "pipeline": [{"$match": {"graph": "talent:metadata", "predicate": "rdfs:label"}}],
                "as": "label",
            }
        },
        {"$set": {"line_label": {"$first": "$label.object"}}},
        {"$unset": "label"},
    ]


def t5_lines_github(area: str) -> Pipeline:
    return [
        {"$match": {"graph": "talent:hierarchy", "subject": area, "predicate": "hasLine"}},
        {
            "$lookup": {
                "from": TALENT,
                "localField": "object",
                "foreignField": "subject",
                "pipeline": [
                    {"$match": {"graph": "talent:github", "predicate": "hasGitHubCostCenter"}}
                ],
                "as": "gh",
            }
        },
        {"$sort": {"object": 1}},
        {
            "$group": {
                "_id": None,
                "lines": {"$sum": 1},
                "lines_with_github_cost_centre": {
                    "$sum": {"$cond": [{"$gt": [{"$size": "$gh"}, 0]}, 1, 0]}
                },
                "rows": {"$push": {"line": "$object", "github": {"$first": "$gh.object"}}},
            }
        },
        {"$project": {"_id": 0, "area": {"$literal": area}, "lines": 1,
                      "lines_with_github_cost_centre": 1, "rows": 1}},
    ]  # fmt: skip


def t6_label_search(word: str) -> Pipeline:
    """Subject labels always name an entity; object labels only when the object is an IRI
    (rdfs:label quads carry the label text itself as object)."""
    return [
        {"$search": {"index": TALENT_SEARCH, "text": {"query": word, "path": "subject_label"}}},
        {"$project": {"_id": 0, "entity": "$subject"}},
        {
            "$unionWith": {
                "coll": TALENT,
                "pipeline": [
                    {
                        "$search": {
                            "index": TALENT_SEARCH,
                            "compound": {
                                "must": [{"text": {"query": word, "path": "object_label"}}],
                                "filter": [{"equals": {"path": "object_kind", "value": "iri"}}],
                            },
                        }
                    },
                    {"$project": {"_id": 0, "entity": "$object"}},
                ],
            }
        },
        {"$group": {"_id": "$entity"}},
        {"$set": {"type": {"$arrayElemAt": [{"$split": ["$_id", ":"]}, 0]}}},
        {
            "$facet": {
                "by_type": [{"$sortByCount": "$type"}],
                "entities": [
                    {"$sort": {"_id": 1}},
                    {"$group": {"_id": None, "ids": {"$push": "$_id"}}},
                ],
            }
        },
        {
            "$project": {
                "word": {"$literal": word},
                "distinct_entities": {"$size": {"$ifNull": [{"$first": "$entities.ids"}, []]}},
                "by_type": _counts_object("$by_type"),
                "entities": {"$ifNull": [{"$first": "$entities.ids"}, []]},
            }
        },
    ]  # fmt: skip


def t7_costcentres_per_business(top: int = 5) -> Pipeline:
    return [
        {"$match": {"graph": "talent:costcenters", "predicate": "belongsToBusiness"}},
        {"$group": {"_id": "$object", "cost_centres": {"$sum": 1}}},
        {"$sort": {"cost_centres": -1, "_id": 1}},
        {
            "$facet": {
                "top": [
                    {"$limit": top},
                    {"$project": {"_id": 0, "business": "$_id", "cost_centres": 1}},
                ],
                "total": [{"$count": "n"}],
            }
        },
        {"$project": {"top_5": "$top", "businesses_total": {"$first": "$total.n"}}},
    ]


# ---------- aicp-quads ----------


def a1_entity_facts(entity: str, pk: str = LIVE) -> Pipeline:
    return [
        {"$match": {"pk": pk, "sk": f"ENTITY#{entity}"}},
        {"$unwind": "$facts"},
        {
            "$group": {
                "_id": _local("$facts.predicate"),
                "values": {"$push": {"$ifNull": ["$facts.object.id", "$facts.object.value"]}},
            }
        },
        {"$sort": {"_id": 1}},
        {
            "$group": {
                "_id": None,
                "facts": {"$sum": {"$size": "$values"}},
                "by_predicate": {"$push": {"k": "$_id", "v": "$values"}},
            }
        },
        {
            "$project": {
                "_id": 0,
                "entity": {"$literal": entity},
                "facts": 1,
                "by_predicate": {"$arrayToObject": "$by_predicate"},
            }
        },
    ]


def a2_pointing_at(object_id: str, pk: str = LIVE) -> Pipeline:
    return [
        {"$match": {"pk": pk, "facts.object.id": object_id}},
        {"$unwind": "$facts"},
        {"$match": {"facts.object.id": object_id}},
        {"$project": {"_id": 0, "subject": "$id", "predicate": _local("$facts.predicate")}},
        {"$sort": {"subject": 1, "predicate": 1}},
        {
            "$facet": {
                "by_predicate": [{"$sortByCount": "$predicate"}],
                "rows": [],
            }
        },
        {
            "$project": {
                "object": {"$literal": object_id},
                "facts_pointing_here": {"$size": "$rows"},
                "distinct_subjects": {"$size": {"$setUnion": ["$rows.subject"]}},
                "by_predicate": _counts_object("$by_predicate"),
                "rows": 1,
            }
        },
    ]  # fmt: skip


def _facts_ending(name: str) -> dict[str, Any]:
    return {
        "$filter": {
            "input": {"$ifNull": ["$facts", []]},
            "cond": {"$eq": [_local("$$this.predicate"), name]},
        }
    }


def a3_reified_about(subject: str, pk: str = LIVE) -> Pipeline:
    return [
        {"$match": {"pk": pk, "reifies.triple.subject.id": subject}},
        {"$sort": {"id": 1}},
        {
            "$project": {
                "_id": 0,
                "reifier": "$id",
                "graph": "$reifies.graph",
                "triple": [
                    "$reifies.triple.subject.id",
                    _local("$reifies.triple.predicate"),
                    _term_value("$reifies.triple.object"),
                ],
                "confidence": {
                    "$let": {
                        "vars": {"c": {"$first": _facts_ending("confidence")}},
                        "in": {"$ifNull": [_local("$$c.object.id"), None]},
                    }
                },
                "evidence": {"$size": _facts_ending("evidence")},
            }
        },
        {"$group": {"_id": None, "rows": {"$push": "$$ROOT"}}},
        {
            "$project": {
                "_id": 0,
                "subject": {"$literal": subject},
                "reifiers": {"$size": "$rows"},
                "rows": 1,
            }
        },
    ]


def a4_claims() -> Pipeline:
    return [
        {"$match": {"kind": "claim", "sk": {"$regex": "^CLAIM#"}}},
        {"$sort": {"pk": 1, "id": 1}},
        {
            "$project": {
                "_id": 0,
                "id": 1,
                "pk": 1,
                "triple": [
                    "$triple.subject.id",
                    _local("$triple.predicate"),
                    _term_value("$triple.object"),
                ],
                "statedBy": {"$ifNull": ["$statedBy", []]},
                "agreedBy": {"$ifNull": ["$agreedBy", []]},
                "contestedBy": {"$ifNull": ["$contestedBy", []]},
                "resolutionState": 1,
            }
        },
        {"$group": {"_id": None, "rows": {"$push": "$$ROOT"}}},
        {"$project": {"_id": 0, "claims": {"$size": "$rows"}, "rows": 1}},
    ]


def _simplify(expr: str) -> dict[str, Any]:
    """HIST before/after values: IRI terms -> local name; lists and scalars unchanged."""
    return {
        "$cond": [
            {"$eq": [{"$type": expr}, "object"]},
            _term_value(expr),
            expr,
        ]
    }


def a5_snapshot_diff(base: str = "v1.02", live: str = "LIVE") -> Pipeline:
    base_pk, live_pk = f"QUADS#{base}", f"QUADS#{live}"
    return [
        {"$match": {"pk": live_pk, "sk": {"$regex": "^ENTITY#"}, "itemVersion": {"$gt": 0}}},
        {"$sort": {"id": 1}},
        {
            "$lookup": {
                "from": AICP,
                "let": {"sk": "$sk"},
                "pipeline": [
                    {
                        "$match": {
                            "$expr": {"$and": [{"$eq": ["$pk", base_pk]}, {"$eq": ["$sk", "$$sk"]}]}
                        }
                    },
                    {"$project": {"_id": 0, "n": {"$size": {"$ifNull": ["$facts", []]}}}},
                ],
                "as": "base",
            }
        },  # fmt: skip
        {
            "$lookup": {
                "from": AICP,
                "let": {"id": "$id"},
                "pipeline": [
                    {
                        "$match": {
                            "$expr": {
                                "$and": [
                                    {"$eq": ["$pk", live_pk]},
                                    {"$eq": ["$kind", "history"]},
                                    {"$eq": ["$entityId", "$$id"]},
                                ]
                            }
                        }
                    },
                    {"$sort": {"sk": 1}},
                    {
                        "$project": {
                            "_id": 0,
                            "history": {"$arrayElemAt": [{"$split": ["$sk", "#"]}, -1]},
                            "changes": {"$objectToArray": "$changes"},
                        }
                    },
                    {"$unwind": "$changes"},
                    {
                        "$project": {
                            "history": 1,
                            "field": "$changes.k",
                            "op": "$changes.v.op",
                            "before": _simplify("$changes.v.before"),
                            "after": _simplify("$changes.v.after"),
                        }
                    },
                ],
                "as": "changes",
            }
        },  # fmt: skip
        {
            "$project": {
                "_id": 0,
                "entity": "$id",
                "itemVersion": 1,
                "liveRevision": 1,
                "facts_base": {"$first": "$base.n"},
                "facts_live": {"$size": {"$ifNull": ["$facts", []]}},
                "changes": 1,
            }
        },
        {"$group": {"_id": None, "rows": {"$push": "$$ROOT"}}},
        {
            "$project": {
                "_id": 0,
                "base": {"$literal": base},
                "live": {"$literal": live},
                "changed_entities": {"$size": "$rows"},
                "rows": 1,
            }
        },
    ]


def semantic_search(query_vector: list[float], limit: int = 5) -> Pipeline:
    return [
        {
            "$vectorSearch": {
                "index": AICP_VECTOR,
                "path": "embedding",
                "queryVector": query_vector,
                "numCandidates": limit * 20,
                "limit": limit,
                "filter": {"pk": LIVE, "kind": "entity"},
            }
        },
        {
            "$project": {
                "_id": 0,
                "id": 1,
                "label": 1,
                "types": 1,
                "score": {"$meta": "vectorSearchScore"},
            }
        },
    ]

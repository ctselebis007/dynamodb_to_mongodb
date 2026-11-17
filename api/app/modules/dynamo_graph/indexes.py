from __future__ import annotations

from app.core.registry import RegularIndex, SearchIndex
from app.modules.dynamo_graph.seed import AICP, TALENT

TALENT_SEARCH = "talent_labels"
AICP_VECTOR = "aicp_semantic"


def regular() -> list[RegularIndex]:
    return [
        # Quad identity; prefix {graph, predicate} also serves T7 and per-graph reloads.
        {
            "collection": TALENT,
            "name": "graph_predicate_object_subject",
            "keys": [("graph", 1), ("predicate", 1), ("object", 1), ("subject", 1)],
            "unique": True,
        },
        {
            "collection": TALENT,
            "name": "subject_predicate_object",
            "keys": [("subject", 1), ("predicate", 1), ("object", 1)],
        },
        {
            "collection": TALENT,
            "name": "object_predicate",
            "keys": [("object", 1), ("predicate", 1)],
        },
        {
            "collection": AICP,
            "name": "pk_sk",
            "keys": [("pk", 1), ("sk", 1)],
            "unique": True,
        },
        {
            "collection": AICP,
            "name": "pk_facts_object_id",
            "keys": [("pk", 1), ("facts.object.id", 1)],
        },
        {
            "collection": AICP,
            "name": "pk_reifies_subject",
            "keys": [("pk", 1), ("reifies.triple.subject.id", 1)],
        },
    ]


def search() -> list[SearchIndex]:
    return [
        {
            "collection": TALENT,
            "name": TALENT_SEARCH,
            "definition": {
                "mappings": {
                    "dynamic": False,
                    "fields": {
                        "subject_label": {"type": "string", "analyzer": "lucene.standard"},
                        "object_label": {"type": "string", "analyzer": "lucene.standard"},
                        "object_kind": {"type": "token"},
                    },
                }
            },
        }
    ]


def vector(dims: int) -> list[SearchIndex]:
    return [
        {
            "collection": AICP,
            "name": AICP_VECTOR,
            "definition": {
                "fields": [
                    {
                        "type": "vector",
                        "path": "embedding",
                        "numDimensions": dims,
                        "similarity": "cosine",
                    },
                    {"type": "filter", "path": "pk"},
                    {"type": "filter", "path": "kind"},
                ]
            },
        }
    ]

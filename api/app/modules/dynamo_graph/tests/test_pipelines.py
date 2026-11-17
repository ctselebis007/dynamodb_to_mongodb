import pytest

from app.modules.dynamo_graph import pipelines as p
from app.modules.dynamo_graph.catalog import QUERIES, Check, evaluate
from app.modules.dynamo_graph.seed import scale_from_env, scale_talent


def test_t3_restricts_hops_by_predicate_not_graph():
    stage = p.t3_subtree("business:X", max_depth=3)[2]["$graphLookup"]
    assert stage["restrictSearchWithMatch"] == {"predicate": {"$in": p.T3_PREDICATES}}
    assert stage["connectFromField"] == "object" and stage["connectToField"] == "subject"
    assert stage["maxDepth"] == 2


def test_reverse_lookups_lead_with_indexed_equality():
    assert p.t2_reverse("belongsToArea", "area:X")[0] == {
        "$match": {"object": "area:X", "predicate": "belongsToArea"}
    }
    assert p.a2_pointing_at("Y")[0] == {"$match": {"pk": p.LIVE, "facts.object.id": "Y"}}
    assert p.a3_reified_about("K06")[0] == {
        "$match": {"pk": p.LIVE, "reifies.triple.subject.id": "K06"}
    }


def test_t6_counts_object_side_only_for_iri_objects():
    union = p.t6_label_search("LAGOON")[2]["$unionWith"]["pipeline"][0]["$search"]
    assert union["compound"]["filter"] == [{"equals": {"path": "object_kind", "value": "iri"}}]


def test_evaluate_includes_matches_dict_subsets():
    doc = {"rows": [{"line": "a", "github": "g", "extra": 1}], "n": 3}
    assert evaluate(Check("rows", [{"line": "a", "github": "g"}], "includes"), doc)[0]
    assert not evaluate(Check("rows", [{"line": "b"}], "includes"), doc)[0]
    assert evaluate(Check("n", 3), doc) == (True, 3)
    assert evaluate(Check("missing.path", 1), doc) == (False, None)


def test_every_query_has_checks():
    assert sorted(QUERIES) == [*(f"A{i}" for i in range(1, 6)), *(f"T{i}" for i in range(1, 8))]
    assert all(q.checks for q in QUERIES.values())


def test_scale_talent_suffixes_entities_but_not_classes_or_literals():
    quads = [
        {"subject": "line:L", "predicate": "rdf:type", "object": "talent:Line",
         "object_kind": "iri"},
        {"subject": "line:L", "predicate": "rdfs:label", "object": "area:like text",
         "object_kind": "literal"},
        {"subject": "area:A", "predicate": "hasLine", "object": "line:L", "object_kind": "iri"},
    ]  # fmt: skip
    out = scale_talent(quads, 3)
    assert len(out) == 9
    assert out[3]["subject"] == "line:L~01" and out[3]["object"] == "talent:Line"
    assert out[4]["object"] == "area:like text"
    assert out[8] == quads[2] | {"subject": "area:A~02", "object": "line:L~02"}


def test_scale_from_env_validates(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DYNAMO_GRAPH_SCALE", "20")
    assert scale_from_env() == 20
    monkeypatch.setenv("DYNAMO_GRAPH_SCALE", "0")
    with pytest.raises(ValueError, match="between 1 and"):
        scale_from_env()

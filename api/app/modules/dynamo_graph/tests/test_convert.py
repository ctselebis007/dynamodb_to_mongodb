from pathlib import Path

import pytest

from app.modules.dynamo_graph import convert

SOURCE = convert.DEFAULT_SOURCE
needs_workbook = pytest.mark.skipif(
    not (SOURCE / "talent-rdf-quads.html").exists(), reason="workbook HTML not present"
)


def test_object_kind_tags_prefixed_names_as_iri():
    assert convert.object_kind("area:WADI_MARBLE") == "iri"
    assert convert.object_kind("talent:Line") == "iri"
    assert convert.object_kind("9940406347") == "literal"
    assert convert.object_kind("LAGOON") == "literal"
    assert convert.object_kind("HEMATITE: BASIN LAGOON") == "literal"


def test_parse_cell_unmarshals_dynamodb_types():
    assert convert.parse_cell("(null)", {"S", "NULL"}) is None
    assert convert.parse_cell("3", {"N"}) == 3
    assert convert.parse_cell("TRUE", {"BOOL"}) is True
    assert convert.parse_cell('["a"]', {"L"}) == ["a"]
    assert convert.parse_cell('{"a": "1"}', {"M"}) == {"a": "1"}
    assert convert.parse_cell("007", {"S"}) == "007"


def test_build_fact_nests_triple_terms():
    row = dict.fromkeys(
        [
            "graph", "predicate", "object.kind", "object.id", "object.value", "object.datatype",
            "object.lang", "triple.subject", "triple.predicate", "triple.object.kind",
            "triple.object.id", "triple.object.value", "triple.object.datatype", "reifiedBy",
        ],
        "",
    )  # fmt: skip
    row |= {
        "graph": "inferred",
        "predicate": "p",
        "object.kind": "triple",
        "triple.subject": "K06",
        "triple.predicate": "blocks",
        "triple.object.kind": "iri",
        "triple.object.id": "GoogleSignIn",
    }
    assert convert.build_fact(row)["object"] == {
        "kind": "triple",
        "subject": {"kind": "iri", "id": "K06"},
        "predicate": "blocks",
        "object": {"kind": "iri", "id": "GoogleSignIn"},
    }


@needs_workbook
def test_convert_workbook_counts_and_shapes(tmp_path: Path):
    data = convert.convert(SOURCE)
    talent, aicp = data["talent_quads"], data["aicp_items"]
    assert len(talent) == 15651 and len(aicp) == 818
    assert {d["object_kind"] for d in talent if d["predicate"] == "rdfs:label"} == {"literal"}
    assert {d["object_kind"] for d in talent if d["predicate"] == "hasLine"} == {"iri"}

    by_id = {d["_id"]: d for d in aicp}
    a1 = by_id["QUADS#LIVE|ENTITY#S-sso_claude_ai_enforced"]
    assert len(a1["facts"]) == 21
    assert by_id["QUADS#LIVE|ENTITY#A4"]["itemVersion"] == 2
    assert len(by_id["QUADS#v1.02|META"]["terms"]) == 145
    assert all(isinstance(d.get("isReifier", False), bool) for d in aicp)
    assert all(d["search_text"] for d in aicp)
    literal_langs = {
        f["object"].get("lang", "absent")
        for d in aicp
        for f in d.get("facts", [])
        if f["object"]["kind"] == "literal"
    }
    assert "(null)" not in literal_langs

    convert.write_fixtures(data, tmp_path)
    assert (tmp_path / "talent_quads.json.gz").stat().st_size > 0


def test_check_raises_on_count_drift():
    with pytest.raises(convert.ConversionError, match="expected 818"):
        convert.check("aicp_items", 817)

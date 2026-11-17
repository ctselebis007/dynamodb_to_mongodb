"""One-time converter: workbook HTML sheets -> gzipped JSON fixtures for seed.py.

Run from api/:  uv run python -m app.modules.dynamo_graph.convert [../design_resources]

The items sheet holds placeholders for the nested `facts` list and the META `terms` list
("7 facts (see sheet aicp-quads facts)"), so both are rebuilt from their own sheets.
Top-level DynamoDB types come from the Attribute dictionary sheet.
"""

from __future__ import annotations

import gzip
import html
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).parent / "fixtures"
DEFAULT_SOURCE = Path(__file__).resolve().parents[4] / "design_resources"

EXPECTED = {"talent_quads": 15651, "aicp_items": 818, "facts": 4974, "rdf12": 239, "terms": 145}

TALENT_FIELDS = ["graph", "subject", "predicate", "object", "subject_label", "object_label"]
PREFIXED_NAME = re.compile(r"^[A-Za-z][\w.-]*:\S+$")
ROW_RE = re.compile(r"<tr.*?</tr>", re.S)
CELL_RE = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S)
TAG_RE = re.compile(r"<[^>]+>")
NULL = "(null)"


class ConversionError(Exception):
    pass


def read_sheet(path: Path) -> list[dict[str, str]]:
    """Rows of an exported sheet. Row 1 is column letters, row 2 the header, row 3 a spacer."""
    text = path.read_text(encoding="utf-8")
    rows = [
        [html.unescape(TAG_RE.sub("", c)) for c in CELL_RE.findall(tr)]
        for tr in ROW_RE.findall(text)
    ]
    header = rows[1]
    return [dict(zip(header, r, strict=True)) for r in rows[2:] if len(r) == len(header) and r[1]]


def object_kind(value: str) -> str:
    return "iri" if PREFIXED_NAME.match(value) else "literal"


def convert_talent(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        doc: dict[str, Any] = {f: r[f] for f in TALENT_FIELDS}
        doc["object_kind"] = object_kind(r["object"])
        out.append(doc)
    return out


def attribute_types(rows: list[dict[str, str]], table: str) -> dict[str, set[str]]:
    """'S (508) / NULL (275)' -> {'S', 'NULL'}"""
    return {
        r["attribute"]: set(re.findall(r"\b([A-Z]+) \(", r["DynamoDB type (items)"]))
        for r in rows
        if r["table"] == table
    }


def parse_number(value: str) -> int | float:
    return int(value) if re.fullmatch(r"-?\d+", value) else float(value)


def parse_cell(value: str, types: set[str]) -> Any:
    """Blank cell = attribute absent (caller skips it); '(null)' = DynamoDB NULL."""
    if value == NULL:
        return None
    if types & {"L", "M"}:
        return json.loads(value)
    if "BOOL" in types:
        return value.upper() == "TRUE"
    if "N" in types:
        return parse_number(value)
    return value


def build_fact(r: dict[str, str]) -> dict[str, Any]:
    kind = r["object.kind"]
    if kind == "triple":
        obj: dict[str, Any] = {
            "kind": "triple",
            "subject": {"kind": "iri", "id": r["triple.subject"]},
            "predicate": r["triple.predicate"],
            "object": _term(
                r["triple.object.kind"],
                r["triple.object.id"],
                r["triple.object.value"],
                r["triple.object.datatype"],
                "",
            ),
        }
    else:
        obj = _term(kind, r["object.id"], r["object.value"], r["object.datatype"], r["object.lang"])
    fact: dict[str, Any] = {"graph": r["graph"], "predicate": r["predicate"], "object": obj}
    if r["reifiedBy"]:
        fact["reifiedBy"] = r["reifiedBy"]
    return fact


def _term(kind: str, id_: str, value: str, datatype: str, lang: str) -> dict[str, Any]:
    if kind == "iri":
        return {"kind": "iri", "id": id_}
    term: dict[str, Any] = {"kind": kind, "value": value}
    if datatype:
        term["datatype"] = datatype
    if lang == NULL:
        term["lang"] = None
    elif lang:
        term["lang"] = lang
    return term


def build_term(r: dict[str, str]) -> dict[str, Any]:
    types = [t.strip() for t in r["types"].split(",") if t.strip()]
    return {"curie": r["curie"], "label": r["label"], "id": r["id"], "types": types}


def local_name(iri: str) -> str:
    return re.split(r"[/#]", iri)[-1]


def search_text(doc: dict[str, Any]) -> str:
    """Text embedded for the bonus semantic search: label + rdfs:comment facts."""
    parts = [doc["label"]] if doc.get("label") else []
    for f in doc.get("facts", []):
        if local_name(f["predicate"]) == "comment" and f["object"].get("value"):
            parts.append(f["object"]["value"])
    return " \n".join(parts) or f"{doc.get('kind', '')} {doc.get('id') or doc['sk']}".strip()


def convert_aicp(
    items: list[dict[str, str]],
    facts: list[dict[str, str]],
    vocabulary: list[dict[str, str]],
    types: dict[str, set[str]],
) -> list[dict[str, Any]]:
    facts_by_item: dict[tuple[str, str], list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    for r in facts:
        facts_by_item[(r["pk"], r["sk"])].append((int(r["fact #"]), build_fact(r)))
    terms_by_item: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in vocabulary:
        terms_by_item[(r["pk"], r["sk"])].append(build_term(r))

    out = []
    for r in items:
        key = (r["pk"], r["sk"])
        doc: dict[str, Any] = {"_id": f"{r['pk']}|{r['sk']}"}
        for attr, value in r.items():
            if attr not in types or value == "":
                continue
            if attr == "facts":
                doc["facts"] = [f for _, f in sorted(facts_by_item.pop(key, []))]
            elif attr == "terms":
                doc["terms"] = terms_by_item.pop(key, [])
            else:
                doc[attr] = parse_cell(value, types[attr])
        doc["search_text"] = search_text(doc)
        out.append(doc)
    if facts_by_item or terms_by_item:
        raise ConversionError(
            f"Orphan facts/terms for {sorted(facts_by_item) + sorted(terms_by_item)}"
        )
    return out


def check(name: str, actual: int) -> None:
    if actual != EXPECTED[name]:
        raise ConversionError(f"{name}: expected {EXPECTED[name]} rows, found {actual}")


def convert(source: Path) -> dict[str, list[dict[str, Any]]]:
    talent = convert_talent(read_sheet(source / "talent-rdf-quads.html"))
    check("talent_quads", len(talent))

    facts = read_sheet(source / "aicp-quads facts.html")
    check("facts", len(facts))
    vocabulary = read_sheet(source / "aicp-quads vocabulary.html")
    check("terms", len(vocabulary))
    types = attribute_types(read_sheet(source / "Attribute dictionary.html"), "aicp-quads")
    aicp = convert_aicp(read_sheet(source / "aicp-quads items.html"), facts, vocabulary, types)
    check("aicp_items", len(aicp))
    check("rdf12", sum(1 for d in aicp if "reifies" in d or "triple" in d))
    check("facts", sum(len(d.get("facts", [])) for d in aicp))
    return {"talent_quads": talent, "aicp_items": aicp}


def write_fixtures(data: dict[str, list[dict[str, Any]]], target: Path = FIXTURES) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for name, docs in data.items():
        with gzip.open(target / f"{name}.json.gz", "wt", encoding="utf-8") as fh:
            json.dump(docs, fh, ensure_ascii=False, separators=(",", ":"))


def main(argv: list[str]) -> None:
    source = Path(argv[1]) if len(argv) > 1 else DEFAULT_SOURCE
    data = convert(source)
    write_fixtures(data)
    for name, docs in data.items():
        print(f"{name}: {len(docs)} docs -> {FIXTURES / (name + '.json.gz')}")


if __name__ == "__main__":
    main(sys.argv)

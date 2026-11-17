"""Seed data: the converted workbook fixtures, optionally scaled up for timing at ~300K quads.

Scale comes from the DYNAMO_GRAPH_SCALE env var (default 1). At scale N the talent graph is
cloned N-1 times with suffixed entity ids (business:X~01), so shape and fan-out stay realistic.
"""

from __future__ import annotations

import gzip
import json
import os
import random
from functools import cache
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).parent / "fixtures"
TALENT = "talent_quads"
AICP = "aicp_items"
META = "dynamo_graph_meta"
SCALE_ENV = "DYNAMO_GRAPH_SCALE"
MAX_SCALE = 50
ENTITY_PREFIXES = ("business:", "area:", "line:", "costcenter:", "ghcostcenter:")

embed_fields = {AICP: ["search_text"]}


def collections() -> list[str]:
    return [TALENT, AICP, META]


@cache
def _load(name: str) -> tuple[dict[str, Any], ...]:
    with gzip.open(FIXTURES / f"{name}.json.gz", "rt", encoding="utf-8") as fh:
        return tuple(json.load(fh))


def load_fixture(name: str) -> list[dict[str, Any]]:
    """Fresh copies, so callers (and insert_many's _id injection) never mutate the cache."""
    return [dict(d) for d in _load(name)]


def scale_from_env() -> int:
    raw = os.environ.get(SCALE_ENV, "1")
    try:
        scale = int(raw)
    except ValueError:
        raise ValueError(f"{SCALE_ENV} must be an integer, got {raw!r}") from None
    if not 1 <= scale <= MAX_SCALE:
        raise ValueError(f"{SCALE_ENV} must be between 1 and {MAX_SCALE}, got {scale}")
    return scale


def _suffixed(value: str, copy: int) -> str:
    return f"{value}~{copy:02d}" if value.startswith(ENTITY_PREFIXES) else value


def scale_talent(quads: list[dict[str, Any]], scale: int) -> list[dict[str, Any]]:
    out = list(quads)
    for copy in range(1, scale):
        for q in quads:
            out.append(
                q
                | {
                    "subject": _suffixed(q["subject"], copy),
                    "object": _suffixed(q["object"], copy)
                    if q["object_kind"] == "iri"
                    else q["object"],
                }
            )
    return out


def generate(rng: random.Random) -> dict[str, list[dict[str, Any]]]:
    del rng  # fixtures are already deterministic
    scale = scale_from_env()
    return {
        TALENT: scale_talent(load_fixture(TALENT), scale),
        AICP: load_fixture(AICP),
        META: [{"_id": "scale", "scale": scale}],
    }

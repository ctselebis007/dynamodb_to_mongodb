"""Feature-module contract and discovery.

A module is a package under `app/modules/<name>/` with:
  router.py   `router: APIRouter` (prefix `/api/<name-with-dashes>`)
  seed.py     `collections() -> list[str]`, `generate(rng) -> dict[str, list[dict]]`,
              `embed_fields: dict[str, list[str]]` (embedded into the `embedding` field)
  indexes.py  `regular() -> list[RegularIndex]`, `search() -> list[SearchIndex]`,
              `vector(dims) -> list[SearchIndex]`
seed.py and indexes.py are optional.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import pkgutil
from dataclasses import dataclass
from types import ModuleType
from typing import Any, NotRequired, TypedDict

from fastapi import APIRouter

log = logging.getLogger("demokit.modules")


class RegularIndex(TypedDict):
    collection: str
    name: str
    keys: list[tuple[str, int]]
    unique: NotRequired[bool]


class SearchIndex(TypedDict):
    collection: str
    name: str
    definition: dict[str, Any]


@dataclass
class ModuleInfo:
    name: str
    router: APIRouter
    seed: ModuleType | None = None
    indexes: ModuleType | None = None

    @property
    def slug(self) -> str:
        return self.name.replace("_", "-")


def _optional(qualname: str) -> ModuleType | None:
    return importlib.import_module(qualname) if importlib.util.find_spec(qualname) else None


def discover(package: str = "app.modules") -> list[ModuleInfo]:
    pkg = importlib.import_module(package)
    found: list[ModuleInfo] = []
    for info in sorted(pkgutil.iter_modules(pkg.__path__), key=lambda i: i.name):
        if not info.ispkg or info.name.startswith("_"):
            continue
        base = f"{package}.{info.name}"
        if importlib.util.find_spec(f"{base}.router") is None:
            log.warning("Skipping module '%s': no router.py", info.name)
            continue
        router = getattr(importlib.import_module(f"{base}.router"), "router", None)
        if not isinstance(router, APIRouter):
            log.warning("Skipping module '%s': router.py has no `router`", info.name)
            continue
        found.append(
            ModuleInfo(info.name, router, _optional(f"{base}.seed"), _optional(f"{base}.indexes"))
        )
    return found

from __future__ import annotations

import os
import sys
import time
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pymongo.errors import OperationFailure

from app.core import settings as settings_mod

ENV_KEYS = [
    "MONGODB_URI",
    "DB_NAME",
    "EMBEDDING_PROVIDER",
    "EMBEDDING_MODEL",
    "EMBEDDING_API_KEY",
    "VOYAGE_BASE_URL",
]


@pytest.fixture(autouse=True)
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> settings_mod.SettingsStore:
    """Every test gets an empty config dir and no .env / env-var leakage."""
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(settings_mod, "API_DIR", tmp_path / "api")
    s = settings_mod.SettingsStore(tmp_path / "config")
    monkeypatch.setattr(settings_mod, "_store", s)
    return s


@pytest.fixture
def client() -> Iterator[TestClient]:
    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def fake_modules(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """A throwaway `fakemods` package with one complete module and one without router.py."""
    root = tmp_path / "pkgs" / "fakemods"
    (root / "widgets").mkdir(parents=True)
    (root / "broken").mkdir()
    (root / "__init__.py").write_text("")
    (root / "broken" / "__init__.py").write_text("")
    (root / "widgets" / "__init__.py").write_text("")
    (root / "widgets" / "router.py").write_text(
        "from fastapi import APIRouter\n"
        "router = APIRouter(prefix='/api/widgets')\n"
        "@router.get('/ping')\n"
        "async def ping() -> dict[str, bool]:\n"
        "    return {'pong': True}\n"
    )
    (root / "widgets" / "seed.py").write_text(
        "def collections():\n"
        "    return ['widgets']\n"
        "embed_fields = {'widgets': ['name']}\n"
        "def generate(rng):\n"
        "    return {'widgets': [{'_id': f'w{i}', 'name': f'widget {rng.randint(0, 999)}',\n"
        "                         'kind': rng.choice(['a', 'b'])} for i in range(20)]}\n"
    )
    (root / "widgets" / "indexes.py").write_text(
        "def regular():\n"
        "    return [{'collection': 'widgets', 'name': 'kind_1', 'keys': [('kind', 1)]}]\n"
        "def search():\n"
        "    return [{'collection': 'widgets', 'name': 'widgets_search',\n"
        "             'definition': {'mappings': {'dynamic': True}}}]\n"
        "def vector(dims):\n"
        "    return [{'collection': 'widgets', 'name': 'widgets_vector', 'definition': {\n"
        "        'fields': [{'type': 'vector', 'path': 'embedding', 'numDimensions': dims,\n"
        "                    'similarity': 'cosine'}]}}]\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path / "pkgs"))
    yield "fakemods"
    for name in [m for m in sys.modules if m.startswith("fakemods")]:
        del sys.modules[name]


@pytest.fixture
def atlas_uri() -> str:
    uri = os.environ.get("MONGODB_URI_TEST")
    if not uri:
        pytest.skip("MONGODB_URI_TEST not set")
    return uri


@pytest.fixture
async def atlas_db(atlas_uri: str) -> AsyncIterator:
    from app.core.db import make_client

    client = make_client(atlas_uri)
    db = client[f"demokit_test_{int(time.time() * 1000)}"]
    yield db
    try:
        await client.drop_database(db.name)
    except OperationFailure:
        # Users with readWrite but no dropDatabase privilege: an empty database disappears.
        for name in await db.list_collection_names():
            await db.drop_collection(name)
    await client.close()

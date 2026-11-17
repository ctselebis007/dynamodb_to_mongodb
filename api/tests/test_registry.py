import logging

import pytest
from fastapi.testclient import TestClient

from app.core.registry import discover
from app.main import create_app


def test_discovers_module_and_skips_missing_router(
    fake_modules: str, caplog: pytest.LogCaptureFixture
):
    with caplog.at_level(logging.WARNING):
        mods = discover(fake_modules)
    assert [m.name for m in mods] == ["widgets"]
    assert mods[0].seed is not None and mods[0].indexes is not None
    assert mods[0].seed.collections() == ["widgets"]
    assert "broken" in caplog.text


def test_router_is_mounted(fake_modules: str):
    with TestClient(create_app(fake_modules)) as c:
        assert c.get("/api/widgets/ping").json() == {"pong": True}


def test_openapi_without_settings_or_atlas(client: TestClient):
    assert client.get("/api/health").json() == {"ok": True}
    spec = client.get("/openapi.json").json()
    assert "/api/setup" in spec["paths"]

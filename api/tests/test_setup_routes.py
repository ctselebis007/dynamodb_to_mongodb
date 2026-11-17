import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.settings import Settings, SettingsStore

URI = "mongodb://alice:topsecretpw@127.0.0.1:1/?directConnection=true"
KEY = "pa-route-test-key-98765"  # gitleaks:allow


def test_no_response_contains_a_secret(client: TestClient):
    r = client.put("/api/setup", json={"mongo_uri": URI, "api_key": KEY, "db_name": "demo"})
    assert r.status_code == 200
    bodies = [r.text, client.get("/api/setup").text, client.get("/api/setup/status").text]
    for body in bodies:
        assert "topsecretpw" not in body
        assert KEY not in body
    assert r.json()["key_last4"] == "8765"
    assert r.json()["mongo_uri"].startswith("mongodb://alice:••••@")


def test_put_blank_secret_keeps_existing(client: TestClient, store: SettingsStore):
    client.put("/api/setup", json={"mongo_uri": URI, "api_key": KEY})
    client.put("/api/setup", json={"mongo_uri": "", "api_key": "", "db_name": "other"})
    s = store.load()
    assert (s.mongo_uri, s.api_key, s.db_name) == (URI, KEY, "other")


def test_put_invalid_returns_envelope(client: TestClient):
    r = client.put("/api/setup", json={"db_name": "has space"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_bad_scheme_fails_first_row(client: TestClient):
    r = client.post("/api/setup/test", json={"mongo_uri": "http://example.com"})
    rows = r.json()["rows"]
    assert rows[0]["id"] == "uri" and rows[0]["status"] == "fail"
    assert all(row["status"] == "skip" for row in rows[1:5])
    assert rows[-1]["id"] == "embedding" and rows[-1]["status"] == "fail"


def test_unreachable_host_fails_fast_with_hint(client: TestClient):
    t = time.monotonic()
    r = client.post("/api/setup/test", json={"mongo_uri": URI})
    elapsed = time.monotonic() - t
    rows = {row["id"]: row for row in r.json()["rows"]}
    assert rows["uri"]["status"] == "ok"
    assert rows["ping"]["status"] == "fail"
    assert "access list" in rows["ping"]["hint"]
    assert elapsed < 7.5
    assert "topsecretpw" not in r.text


def test_seed_requires_confirm(client: TestClient):
    client.put("/api/setup", json={"mongo_uri": URI, "api_key": KEY})
    r = client.post("/api/setup/seed", json={})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "CONFIRM_REQUIRED"


def test_status_unconfigured(client: TestClient):
    s = client.get("/api/setup/status").json()
    assert s["configured"] is False and s["seeded"] is False


class FakeProvider:
    name = "fake"
    supports_rerank = False

    def __init__(self, settings: Settings):
        self.model, self.dims = settings.model, settings.dims

    async def embed(self, texts: list[str], input_type: str) -> list[list[float]]:
        return [[(hash(t) % 97) / 97.0 + 0.01] * self.dims for t in texts]


def _wait_job(client: TestClient, job_id: str, timeout: float = 600) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/setup/jobs/{job_id}").json()
        if job["status"] != "running":
            return job
        time.sleep(1)
    raise AssertionError("job timed out")


@pytest.mark.atlas
def test_seed_and_index_fake_module(
    atlas_uri: str, fake_modules: str, monkeypatch: pytest.MonkeyPatch
):
    from app.main import create_app

    monkeypatch.setattr("app.core.setup.make_provider", FakeProvider)
    db_name = f"demokit_test_{int(time.time() * 1000)}"
    with TestClient(create_app(fake_modules)) as client:
        client.put(
            "/api/setup",
            json={"mongo_uri": atlas_uri, "db_name": db_name, "provider": "voyage", "api_key": KEY},
        )
        try:
            job = _wait_job(
                client, client.post("/api/setup/seed", json={"confirm": True}).json()["id"]
            )
            assert job["status"] == "done", job
            status = client.get("/api/setup/status").json()
            assert status["seeded"] and not status["indexed"]
            assert status["meta"]["dims"] == 1024

            job = _wait_job(client, client.post("/api/setup/indexes").json()["id"])
            assert job["status"] == "done", job
            assert client.get("/api/setup/status").json()["indexed"] is True

            client.put("/api/setup", json={"provider": "openai"})
            assert client.get("/api/setup/status").json()["reseed_required"] is True
        finally:
            import certifi
            from pymongo import MongoClient

            MongoClient(atlas_uri, tlsCAFile=certifi.where()).drop_database(db_name)

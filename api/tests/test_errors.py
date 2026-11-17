import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pymongo.errors import OperationFailure, ServerSelectionTimeoutError

from app.core.embeddings import EmbeddingAuthError, EmbeddingUnavailableError
from app.core.errors import AppError, install_log_masking, register_error_handlers, to_app_error
from app.core.settings import SettingsStore, SettingsUpdate

URI = "mongodb+srv://alice:hunter2pass@cluster0.x.mongodb.net/"
KEY = "pa-supersecretkey123456"


@pytest.mark.parametrize(
    ("exc", "code", "hint_word"),
    [
        (ServerSelectionTimeoutError("timeout"), "ATLAS_UNREACHABLE", "access list"),
        (OperationFailure("bad auth", code=8000), "AUTH_FAILED", "password"),
        (EmbeddingAuthError("401"), "EMBEDDING_AUTH", "API key"),
        (EmbeddingUnavailableError("503"), "EMBEDDING_UNAVAILABLE", "network"),
        (RuntimeError("boom"), "INTERNAL", "log"),
    ],
)
def test_mapping(exc: Exception, code: str, hint_word: str):
    err = to_app_error(exc)
    assert err.code == code
    assert hint_word in err.hint


def test_envelope_from_route():
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/x")
    async def x():
        raise ServerSelectionTimeoutError(f"cannot reach {URI}")

    @app.get("/y")
    async def y():
        raise AppError("NOT_SEEDED", "nope", "Run Seed", 409)

    c = TestClient(app, raise_server_exceptions=False)
    r = c.get("/x")
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "ATLAS_UNREACHABLE"
    assert "hunter2pass" not in r.text
    r = c.get("/y")
    assert r.status_code == 409
    assert r.json() == {"error": {"code": "NOT_SEEDED", "message": "nope", "hint": "Run Seed"}}


def test_logs_mask_settings_and_driver_errors(
    store: SettingsStore, caplog: pytest.LogCaptureFixture
):
    settings = store.save(SettingsUpdate(mongo_uri=URI, api_key=KEY))
    install_log_masking(lambda: settings.secrets())
    log = logging.getLogger("demokit.test")
    with caplog.at_level(logging.INFO):
        log.info("settings: %s", settings.model_dump())
        log.info("repr: %r", settings)
        log.info("Authorization: Bearer %s", KEY)
        try:
            raise OperationFailure(f"auth failed for {URI}", code=18)
        except OperationFailure:
            log.exception("driver error")
    text = caplog.text + "".join(r.exc_text or "" for r in caplog.records)
    assert "hunter2pass" not in text
    assert KEY not in text
    assert "••••" in text

import stat

import pytest
from pydantic import ValidationError

from app.core.settings import MASK, Settings, SettingsStore, SettingsUpdate, mask_uri

SRV = "mongodb+srv://alice:s3cretPass@cluster0.abcd.mongodb.net/?retryWrites=true"


def test_round_trip(store: SettingsStore):
    key = "pa-1234567890abcd"  # gitleaks:allow
    saved = store.save(SettingsUpdate(mongo_uri=SRV, db_name="shop", api_key=key))
    loaded = store.load()
    assert loaded == saved
    assert loaded.mongo_uri == SRV
    assert loaded.db_name == "shop"


@pytest.mark.parametrize(
    ("uri", "expected"),
    [
        (SRV, f"mongodb+srv://alice:{MASK}@cluster0.abcd.mongodb.net/?retryWrites=true"),
        (
            "mongodb://bob:p%40ss%2Fw0rd@localhost:27017/db",
            f"mongodb://bob:{MASK}@localhost:27017/db",
        ),
        ("mongodb+srv://cluster0.abcd.mongodb.net/", "mongodb+srv://cluster0.abcd.mongodb.net/"),
        ("mongodb://localhost:27017", "mongodb://localhost:27017"),
    ],
)
def test_mask_uri(uri: str, expected: str):
    assert mask_uri(uri) == expected


def test_masked_view_hides_secrets(store: SettingsStore):
    s = store.save(SettingsUpdate(mongo_uri=SRV, api_key="pa-abcdefghijkl9876"))  # gitleaks:allow
    view = s.masked().model_dump_json()
    assert "s3cretPass" not in view
    assert "pa-abcdefghijkl9876" not in view
    m = s.masked()
    assert m.has_key and m.key_last4 == "9876"
    assert "s3cretPass" not in repr(s) and "s3cretPass" not in str(s)


def test_blank_secret_keeps_existing(store: SettingsStore):
    store.save(SettingsUpdate(mongo_uri=SRV, api_key="pa-original-key-0001"))
    s = store.save(SettingsUpdate(mongo_uri="", api_key="  ", db_name="other"))
    assert s.mongo_uri == SRV
    assert s.api_key == "pa-original-key-0001"
    assert s.db_name == "other"


def test_invalid_db_name_rejected(store: SettingsStore):
    with pytest.raises(ValidationError):
        store.save(SettingsUpdate(db_name="bad name/with.dots"))


def test_provider_switch_defaults_model_and_dims(store: SettingsStore):
    s = store.save(SettingsUpdate(provider="openai"))
    assert (s.model, s.dims) == ("text-embedding-3-small", 1536)
    s = store.save(SettingsUpdate(provider="voyage"))
    assert (s.model, s.dims) == ("voyage-4", 1024)


def test_unknown_model_rejected():
    with pytest.raises(ValidationError):
        Settings(provider="voyage", model="text-embedding-3-small")


def test_file_mode_0600(store: SettingsStore):
    store.save(SettingsUpdate(db_name="x"))
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600


def test_first_run_prefills_from_env(store: SettingsStore, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MONGODB_URI", SRV)
    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
    s = store.load()
    assert s.mongo_uri == SRV
    assert s.model == "text-embedding-3-small"

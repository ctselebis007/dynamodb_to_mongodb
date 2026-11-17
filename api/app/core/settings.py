"""Demo settings: persisted server-side in api/config/settings.json, never returned unmasked."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Literal

from dotenv import dotenv_values
from pydantic import BaseModel, Field, field_validator, model_validator

Provider = Literal["voyage", "openai"]

MODELS: dict[str, dict[str, int]] = {
    "voyage": {"voyage-4": 1024, "voyage-4-large": 1024, "voyage-4-lite": 1024},
    "openai": {"text-embedding-3-small": 1536, "text-embedding-3-large": 3072},
}
DEFAULT_MODEL: dict[str, str] = {"voyage": "voyage-4", "openai": "text-embedding-3-small"}
RERANK_MODEL = "rerank-3"
DEFAULT_VOYAGE_BASE_URL = "https://ai.mongodb.com"
MASK = "••••"

API_DIR = Path(__file__).resolve().parents[2]
DB_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,63}$")
URI_CREDS_RE = re.compile(r"^(mongodb(?:\+srv)?://)([^:@/]+):([^@/]*)@")


def dims_for(provider: str, model: str) -> int:
    return MODELS[provider][model]


def mask_uri(uri: str) -> str:
    return URI_CREDS_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}:{MASK}@", uri)


class Settings(BaseModel):
    mongo_uri: str = ""
    db_name: str = "demo"
    provider: Provider = "voyage"
    model: str = DEFAULT_MODEL["voyage"]
    api_key: str = ""
    voyage_base_url: str = DEFAULT_VOYAGE_BASE_URL

    @field_validator("db_name")
    @classmethod
    def _valid_db_name(cls, v: str) -> str:
        if not DB_NAME_RE.match(v):
            raise ValueError("db_name must be 1-63 chars of letters, digits, '_' or '-'")
        return v

    @field_validator("voyage_base_url")
    @classmethod
    def _valid_base_url(cls, v: str) -> str:
        v = v.strip().rstrip("/") or DEFAULT_VOYAGE_BASE_URL
        if not v.startswith("https://"):
            raise ValueError("voyage_base_url must start with https://")
        return v

    @model_validator(mode="after")
    def _valid_model(self) -> Settings:
        if self.model not in MODELS[self.provider]:
            raise ValueError(
                f"model '{self.model}' is not available for provider '{self.provider}'"
            )
        return self

    @property
    def dims(self) -> int:
        return dims_for(self.provider, self.model)

    def secrets(self) -> list[str]:
        out = [self.api_key] if self.api_key else []
        m = URI_CREDS_RE.match(self.mongo_uri)
        if m and m.group(3):
            out.append(m.group(3))
        return out

    def masked(self) -> MaskedSettings:
        return MaskedSettings(
            mongo_uri=mask_uri(self.mongo_uri),
            db_name=self.db_name,
            provider=self.provider,
            model=self.model,
            dims=self.dims,
            has_uri=bool(self.mongo_uri),
            has_key=bool(self.api_key),
            key_last4=self.api_key[-4:] if len(self.api_key) >= 8 else None,
            voyage_base_url=self.voyage_base_url,
            models=MODELS,
        )

    def __repr__(self) -> str:
        return f"Settings({self.masked().model_dump(exclude={'models'})})"

    __str__ = __repr__


class MaskedSettings(BaseModel):
    mongo_uri: str
    db_name: str
    provider: Provider
    model: str
    dims: int
    has_uri: bool
    has_key: bool
    key_last4: str | None
    voyage_base_url: str
    models: dict[str, dict[str, int]]


class SettingsUpdate(BaseModel):
    """Partial update. Blank or missing secrets keep the stored value."""

    mongo_uri: str | None = Field(default=None, json_schema_extra={"format": "password"})
    db_name: str | None = None
    provider: Provider | None = None
    model: str | None = None
    api_key: str | None = Field(default=None, json_schema_extra={"format": "password"})
    voyage_base_url: str | None = None


def _env_defaults() -> dict[str, str]:
    values: dict[str, str] = {}
    for path in (API_DIR.parent / ".env", API_DIR / ".env"):
        if path.is_file():
            values.update({k: v for k, v in dotenv_values(path).items() if v})
    values.update({k: v for k, v in os.environ.items() if v})
    mapping = {
        "MONGODB_URI": "mongo_uri",
        "DB_NAME": "db_name",
        "EMBEDDING_PROVIDER": "provider",
        "EMBEDDING_MODEL": "model",
        "EMBEDDING_API_KEY": "api_key",
        "VOYAGE_BASE_URL": "voyage_base_url",
    }
    return {field: values[env] for env, field in mapping.items() if env in values}


class SettingsStore:
    def __init__(self, config_dir: Path):
        self.path = config_dir / "settings.json"

    def load(self) -> Settings:
        if self.path.is_file():
            return Settings.model_validate_json(self.path.read_text())
        env = _env_defaults()
        if "provider" in env and "model" not in env:
            env["model"] = DEFAULT_MODEL.get(env["provider"], "")
        return Settings.model_validate(env)

    def merged(self, update: SettingsUpdate) -> Settings:
        """Apply an update on top of the stored settings without saving."""
        data = self.load().model_dump()
        patch = update.model_dump(exclude_none=True)
        for secret in ("mongo_uri", "api_key"):
            if not (patch.get(secret) or "").strip():
                patch.pop(secret, None)
        if "provider" in patch and patch["provider"] != data["provider"] and "model" not in patch:
            patch["model"] = DEFAULT_MODEL[patch["provider"]]
        data.update({k: v.strip() if isinstance(v, str) else v for k, v in patch.items()})
        return Settings.model_validate(data)

    def save(self, update: SettingsUpdate) -> Settings:
        settings = self.merged(update)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".settings-", suffix=".json")
        try:
            os.chmod(tmp, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(settings.model_dump_json(indent=2))
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        return settings


_store = SettingsStore(Path(os.environ.get("DEMOKIT_CONFIG_DIR") or API_DIR / "config"))


def get_store() -> SettingsStore:
    return _store


def set_store(store: SettingsStore) -> None:
    global _store
    _store = store


def get_settings() -> Settings:
    return _store.load()

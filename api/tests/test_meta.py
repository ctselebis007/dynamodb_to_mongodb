from typing import Any

import pytest

from app.core.errors import AppError
from app.core.meta import DemoMeta, now, require_ready
from app.core.settings import SettingsStore, SettingsUpdate


class FakeColl:
    def __init__(self, doc: dict[str, Any] | None):
        self.doc = doc

    async def find_one(self, *_: Any, **__: Any) -> dict[str, Any] | None:
        return self.doc


class FakeDb(dict):
    def __init__(self, doc: dict[str, Any] | None):
        super().__init__(_demo_meta=FakeColl(doc))


def meta(**kw: Any) -> dict[str, Any]:
    base = DemoMeta(
        provider="voyage", model="voyage-4", dims=1024, seeded_at=now(), indexed_at=now()
    ).model_dump()
    base.update(kw)
    return base


@pytest.mark.parametrize(
    ("doc", "code"),
    [
        (None, "NOT_SEEDED"),
        (meta(seeded_at=None), "NOT_SEEDED"),
        (meta(provider="openai", model="text-embedding-3-small"), "RESEED_REQUIRED"),
        (meta(indexed_at=None), "INDEX_NOT_READY"),
    ],
)
async def test_not_ready_states(store: SettingsStore, doc: dict | None, code: str):
    store.save(SettingsUpdate(provider="voyage"))
    with pytest.raises(AppError) as e:
        await require_ready(FakeDb(doc))  # type: ignore[arg-type]
    assert (e.value.code, e.value.status) == (code, 409)


async def test_ready_passes(store: SettingsStore):
    store.save(SettingsUpdate(provider="voyage"))
    m = await require_ready(FakeDb(meta()))  # type: ignore[arg-type]
    assert m.dims == 1024

import pytest

from app.core.db import ClientCache, get_db, make_client
from app.core.errors import AppError
from app.core.settings import SettingsStore, SettingsUpdate


async def test_saving_settings_invalidates_cached_client(
    store: SettingsStore, monkeypatch: pytest.MonkeyPatch
):
    cache = ClientCache()
    monkeypatch.setattr("app.core.db.clients", cache)
    store.save(SettingsUpdate(mongo_uri="mongodb://localhost:1/?directConnection=true"))
    first = await get_db()
    again = await get_db()
    assert first.client is again.client

    store.save(SettingsUpdate(mongo_uri="mongodb://localhost:2/?directConnection=true"))
    second = await get_db()
    assert second.client is not first.client
    await cache.close()


async def test_get_db_requires_uri():
    with pytest.raises(AppError) as e:
        await get_db()
    assert e.value.code == "NOT_CONFIGURED"


async def test_client_options():
    client = make_client("mongodb://localhost:1/?directConnection=true")
    assert client.options.pool_options.metadata["application"]["name"] == "mongodb-demo-kit"
    await client.close()


@pytest.mark.atlas
async def test_atlas_ping(atlas_uri: str):
    client = make_client(atlas_uri)
    assert (await client.admin.command("ping"))["ok"] == 1
    await client.close()

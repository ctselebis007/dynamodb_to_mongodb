from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core import jobs, setup
from app.core.db import clients
from app.core.errors import install_log_masking, register_error_handlers
from app.core.registry import discover
from app.core.settings import get_settings


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await clients.close()


def create_app(modules_package: str = "app.modules") -> FastAPI:
    install_log_masking(lambda: get_settings().secrets())
    app = FastAPI(title="MongoDB Demo Kit API", version="0.1.0", lifespan=lifespan)
    register_error_handlers(app)

    @app.get("/api/health", tags=["health"])
    async def health() -> dict[str, bool]:
        return {"ok": True}

    app.include_router(setup.router)
    app.include_router(jobs.router)
    app.state.modules = discover(modules_package)
    for module in app.state.modules:
        app.include_router(module.router)
    return app


app = create_app()

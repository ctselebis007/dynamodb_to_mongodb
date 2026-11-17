"""Embedding + rerank providers (Voyage AI, OpenAI) over plain httpx."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Literal, Protocol

import httpx

if TYPE_CHECKING:
    from app.core.settings import Settings

InputType = Literal["document", "query"]
RETRY_STATUS = {429, 500, 502, 503, 504}


class EmbeddingError(Exception):
    pass


class EmbeddingAuthError(EmbeddingError):
    pass


class EmbeddingRateLimitError(EmbeddingError):
    pass


class EmbeddingUnavailableError(EmbeddingError):
    pass


class EmbeddingProvider(Protocol):
    name: str
    model: str
    dims: int
    supports_rerank: bool

    async def embed(self, texts: list[str], input_type: InputType) -> list[list[float]]: ...


class _HttpProvider:
    name = ""
    max_batch = 128
    supports_rerank = False

    def __init__(
        self,
        api_key: str,
        model: str,
        dims: int,
        base_url: str,
        *,
        timeout: float = 15.0,
        retries: int = 3,
        backoff: float = 1.0,
    ):
        self.api_key = api_key
        self.model = model
        self.dims = dims
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        last: Exception | None = None
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            for attempt in range(self.retries + 1):
                if attempt:
                    await asyncio.sleep(self.backoff * 2 ** (attempt - 1))
                try:
                    resp = await client.post(path, json=payload, headers=headers)
                except httpx.TimeoutException:
                    last = EmbeddingUnavailableError(f"{self.name} request timed out")
                    continue
                except httpx.TransportError as exc:
                    last = EmbeddingUnavailableError(
                        f"{self.name} unreachable: {type(exc).__name__}"
                    )
                    continue
                if resp.status_code in (401, 403):
                    raise EmbeddingAuthError(
                        f"{self.name} rejected the API key ({resp.status_code})"
                    )
                if resp.status_code == 429:
                    last = EmbeddingRateLimitError(f"{self.name} rate limit (429)")
                    continue
                if resp.status_code in RETRY_STATUS:
                    last = EmbeddingUnavailableError(f"{self.name} error {resp.status_code}")
                    continue
                if resp.status_code >= 400:
                    raise EmbeddingError(f"{self.name} error {resp.status_code}: {_detail(resp)}")
                return resp.json()
        assert last is not None
        raise last

    async def embed(self, texts: list[str], input_type: InputType) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), self.max_batch):
            out.extend(await self._embed_batch(texts[i : i + self.max_batch], input_type))
        return out

    async def _embed_batch(self, texts: list[str], input_type: InputType) -> list[list[float]]:
        raise NotImplementedError


class VoyageProvider(_HttpProvider):
    name = "Voyage AI"
    # API max is 1,000 texts / 320K tokens per request for voyage-4.
    max_batch = 128
    supports_rerank = True

    async def _embed_batch(self, texts: list[str], input_type: InputType) -> list[list[float]]:
        data = await self._post(
            "/v1/embeddings", {"input": texts, "model": self.model, "input_type": input_type}
        )
        return [d["embedding"] for d in sorted(data["data"], key=lambda d: d["index"])]

    async def rerank(
        self, query: str, documents: list[str], top_k: int | None = None, model: str = "rerank-3"
    ) -> list[dict[str, Any]]:
        """Returns `[{index, relevance_score}]` sorted by relevance."""
        payload: dict[str, Any] = {"query": query, "documents": documents, "model": model}
        if top_k:
            payload["top_k"] = top_k
        data = await self._post("/v1/rerank", payload)
        return [
            {"index": r["index"], "relevance_score": r["relevance_score"]} for r in data["data"]
        ]


class OpenAIProvider(_HttpProvider):
    name = "OpenAI"
    max_batch = 256

    async def _embed_batch(self, texts: list[str], input_type: InputType) -> list[list[float]]:
        data = await self._post("/v1/embeddings", {"input": texts, "model": self.model})
        return [d["embedding"] for d in sorted(data["data"], key=lambda d: d["index"])]


def make_provider(settings: Settings) -> VoyageProvider | OpenAIProvider:
    if not settings.api_key:
        raise EmbeddingAuthError("No embedding API key configured")
    if settings.provider == "voyage":
        return VoyageProvider(
            settings.api_key, settings.model, settings.dims, settings.voyage_base_url
        )
    return OpenAIProvider(settings.api_key, settings.model, settings.dims, "https://api.openai.com")


def _detail(resp: httpx.Response) -> str:
    try:
        body = resp.json()
    except ValueError:
        return resp.text[:200]
    if isinstance(body, dict):
        err = body.get("detail") or body.get("error") or body
        if isinstance(err, dict):
            err = err.get("message", err)
        return str(err)[:200]
    return str(body)[:200]

import json
import os

import httpx
import pytest
import respx

from app.core.embeddings import (
    EmbeddingAuthError,
    EmbeddingUnavailableError,
    OpenAIProvider,
    VoyageProvider,
)
from app.core.settings import DEFAULT_VOYAGE_BASE_URL, dims_for

BASE = "https://voyage.test"


def _vectors(n: int, offset: int = 0) -> dict:
    return {"data": [{"index": i, "embedding": [float(offset + i)]} for i in range(n)]}


def voyage(**kw) -> VoyageProvider:
    return VoyageProvider("pa-test-key-1234", "voyage-4", 1024, BASE, backoff=0, **kw)


@respx.mock
async def test_retries_429_then_succeeds():
    route = respx.post(f"{BASE}/v1/embeddings").mock(
        side_effect=[httpx.Response(429), httpx.Response(200, json=_vectors(2))]
    )
    assert await voyage().embed(["a", "b"], "document") == [[0.0], [1.0]]
    assert route.call_count == 2


@respx.mock
async def test_401_raises_auth_error_without_retry():
    route = respx.post(f"{BASE}/v1/embeddings").mock(return_value=httpx.Response(401))
    with pytest.raises(EmbeddingAuthError):
        await voyage().embed(["a"], "query")
    assert route.call_count == 1


@respx.mock
async def test_batching_splits_requests():
    def reply(request: httpx.Request) -> httpx.Response:
        texts = json.loads(request.content)["input"]
        return httpx.Response(200, json=_vectors(len(texts)))

    route = respx.post(f"{BASE}/v1/embeddings").mock(side_effect=reply)
    p = voyage()
    p.max_batch = 3
    out = await p.embed([str(i) for i in range(7)], "document")
    assert len(out) == 7
    assert [len(json.loads(c.request.content)["input"]) for c in route.calls] == [3, 3, 1]


@respx.mock
async def test_timeout_raises_unavailable_after_retries():
    route = respx.post(f"{BASE}/v1/embeddings").mock(side_effect=httpx.ConnectTimeout("slow"))
    with pytest.raises(EmbeddingUnavailableError):
        await voyage(retries=2).embed(["a"], "query")
    assert route.call_count == 3


@respx.mock
async def test_payload_shape_and_auth_header():
    route = respx.post(f"{BASE}/v1/embeddings").mock(
        return_value=httpx.Response(200, json=_vectors(1))
    )
    await voyage().embed(["hello"], "query")
    req = route.calls[0].request
    assert req.headers["authorization"] == "Bearer pa-test-key-1234"
    body = json.loads(req.content)
    assert body == {"input": ["hello"], "model": "voyage-4", "input_type": "query"}


@respx.mock
async def test_rerank_parses_results():
    respx.post(f"{BASE}/v1/rerank").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [{"index": 1, "relevance_score": 0.9}, {"index": 0, "relevance_score": 0.1}]
            },
        )
    )
    out = await voyage().rerank("q", ["a", "b"], top_k=2)
    assert out[0] == {"index": 1, "relevance_score": 0.9}


@pytest.mark.atlas
async def test_voyage_live_dims_and_rerank():
    key = os.environ.get("TEST_VOYAGE_KEY") or pytest.skip("TEST_VOYAGE_KEY not set")
    base = os.environ.get("TEST_VOYAGE_BASE_URL", DEFAULT_VOYAGE_BASE_URL)
    p = VoyageProvider(key, "voyage-4", dims_for("voyage", "voyage-4"), base)
    vec = (await p.embed(["hello world"], "document"))[0]
    assert len(vec) == p.dims
    docs = ["Bananas are yellow fruit.", "MongoDB Atlas Vector Search stores embeddings."]
    ranked = await p.rerank("Which database supports vector search?", docs)
    assert ranked[0]["index"] == 1


@pytest.mark.atlas
async def test_openai_live_dims():
    key = os.environ.get("TEST_OPENAI_KEY") or pytest.skip("TEST_OPENAI_KEY not set")
    model = "text-embedding-3-small"
    p = OpenAIProvider(key, model, dims_for("openai", model), "https://api.openai.com")
    assert len((await p.embed(["hello"], "document"))[0]) == p.dims

from datetime import UTC, datetime

from app.core.meta import DemoMeta
from app.modules.dynamo_graph.router import _has_answer, module_seeded


def _meta(modules: list[str]) -> DemoMeta:
    now = datetime.now(UTC)
    return DemoMeta(provider="voyage", model="m", dims=8, seeded_at=now, indexed_at=now,
                    modules=modules)  # fmt: skip


def test_module_seeded_requires_this_module_in_meta():
    assert module_seeded(_meta(["dynamo-graph", "search-lab"]))
    assert not module_seeded(_meta(["graph-view", "search-lab"]))
    assert not module_seeded(None)


def test_facet_summaries_with_zero_counts_are_no_match():
    assert not _has_answer("T3", [{"total_nodes": 0, "nodes": []}])
    assert _has_answer("T3", [{"total_nodes": 197}])
    assert not _has_answer("T1", [])
    assert _has_answer("T1", [{"count": 18}])

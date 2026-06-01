"""DashScope 客户端测试。

Python 3.14 + respx 0.21.x 兼容性说明：
与 test_business_client.py 同理，改用 transport 注入方式（httpx.MockTransport）。
测试契约（embedding 向量顺序、rerank 排序逻辑）完全与规格一致。
"""
import httpx
import respx

from app.clients.dashscope_client import DashScopeClient

EMB_BASE = "http://ds.test/v1"
RERANK_URL = "http://ds.test/api/v1/services/rerank/text-rerank/text-rerank"


def _client(router: respx.MockRouter) -> DashScopeClient:
    """构造注入了 mock transport 的 DashScopeClient。"""
    transport = httpx.MockTransport(router.handler)
    return DashScopeClient(
        embedding_api_key="k",
        rerank_api_key="k",
        base_url=EMB_BASE,
        rerank_url=RERANK_URL,
        embedding_model="m",
        rerank_model="r",
        transport=transport,
    )


def test_embed_texts_returns_vectors():
    router = respx.MockRouter(assert_all_called=False)
    router.post(f"{EMB_BASE}/embeddings").mock(
        return_value=httpx.Response(200, json={
            "data": [
                {"embedding": [0.1, 0.2, 0.3], "index": 0},
                {"embedding": [0.4, 0.5, 0.6], "index": 1},
            ]
        })
    )
    c = _client(router)
    vecs = c.embed_texts(["a", "b"])
    assert len(vecs) == 2
    assert vecs[0] == [0.1, 0.2, 0.3]


def test_embed_single_query():
    router = respx.MockRouter(assert_all_called=False)
    router.post(f"{EMB_BASE}/embeddings").mock(
        return_value=httpx.Response(200, json={"data": [{"embedding": [1.0, 0.0], "index": 0}]})
    )
    c = _client(router)
    v = c.embed_query("hello")
    assert v == [1.0, 0.0]


def test_rerank_returns_sorted_indices_and_scores():
    router = respx.MockRouter(assert_all_called=False)
    router.post(RERANK_URL).mock(
        return_value=httpx.Response(200, json={
            "output": {"results": [
                {"index": 2, "relevance_score": 0.9},
                {"index": 0, "relevance_score": 0.5},
                {"index": 1, "relevance_score": 0.1},
            ]}
        })
    )
    c = _client(router)
    results = c.rerank("query", ["d0", "d1", "d2"], top_k=2)
    assert results == [(2, 0.9), (0, 0.5)]

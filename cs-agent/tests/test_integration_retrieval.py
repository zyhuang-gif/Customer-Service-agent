import pytest

from app.config import settings

pytestmark = pytest.mark.integration

skip_no_key = pytest.mark.skipif(
    not settings.dashscope_api_key,
    reason="需要 DASHSCOPE_API_KEY 才能跑真实检索集成测试",
)


@skip_no_key
def test_real_retrieve_logistics_question(tmp_path):
    """真实 embedding + rerank：问物流问题应召回物流催办政策。"""
    from app.clients.dashscope_client import DashScopeClient
    from app.retrieval.chunking import chunk_markdown
    from app.retrieval.retriever import Retriever
    from app.retrieval.store import VectorStore

    client = DashScopeClient()
    store = VectorStore(embed_fn=client.embed_texts, persist_dir=str(tmp_path), collection="it_test")
    text = open(f"{settings.knowledge_dir}/aftersale_policy.md", encoding="utf-8").read()
    store.add_chunks(chunk_markdown(text, source="aftersale_policy.md"))

    retriever = Retriever(store=store, rerank_fn=client.rerank, top_n=5, top_k=2)
    results = retriever.retrieve("我的快递好几天没动了怎么办")
    assert len(results) >= 1
    titles = [r["title"] for r in results]
    assert any("物流" in t for t in titles)

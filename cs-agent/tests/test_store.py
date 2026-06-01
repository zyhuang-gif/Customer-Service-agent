from app.retrieval.store import VectorStore


def _fake_embed(texts):
    vecs = []
    for t in texts:
        if "物流" in t:
            vecs.append([1.0, 0.0])
        elif "退款" in t:
            vecs.append([0.0, 1.0])
        else:
            vecs.append([0.5, 0.5])
    return vecs


def test_add_and_query(tmp_path):
    store = VectorStore(embed_fn=_fake_embed, persist_dir=str(tmp_path), collection="test")
    store.add_chunks([
        {"title": "物流催办", "source": "x.md", "text": "物流超过72小时未更新可催办"},
        {"title": "退款时效", "source": "x.md", "text": "退款1-7个工作日到账"},
    ])
    hits = store.query("我的物流怎么还没动", top_n=1)
    assert len(hits) == 1
    assert hits[0]["title"] == "物流催办"
    assert "source" in hits[0] and "text" in hits[0]


def test_query_empty_store_returns_empty(tmp_path):
    store = VectorStore(embed_fn=_fake_embed, persist_dir=str(tmp_path), collection="empty")
    assert store.query("任意", top_n=3) == []

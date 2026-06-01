from app.retrieval.retriever import Retriever


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


def _fake_rerank(query, documents, top_k):
    scored = []
    for i, d in enumerate(documents):
        score = 1.0 if "物流" in d else 0.1
        scored.append((i, score))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]


def _build(tmp_path):
    from app.retrieval.store import VectorStore
    store = VectorStore(embed_fn=_fake_embed, persist_dir=str(tmp_path), collection="ret")
    store.add_chunks([
        {"title": "物流催办", "source": "x.md", "text": "物流超过72小时未更新可催办"},
        {"title": "退款时效", "source": "x.md", "text": "退款1-7个工作日到账"},
        {"title": "发票", "source": "x.md", "text": "电子发票1-3个工作日开具"},
    ])
    return Retriever(store=store, rerank_fn=_fake_rerank, top_n=3, top_k=2)


def test_retrieve_returns_reranked_with_citation(tmp_path):
    r = _build(tmp_path)
    results = r.retrieve("物流停了怎么办")
    assert len(results) == 2
    assert results[0]["title"] == "物流催办"
    assert results[0]["source"] == "x.md"
    assert "text" in results[0]
    assert "score" in results[0]


def test_retrieve_empty_store_returns_empty(tmp_path):
    from app.retrieval.store import VectorStore
    store = VectorStore(embed_fn=_fake_embed, persist_dir=str(tmp_path), collection="emp")
    r = Retriever(store=store, rerank_fn=_fake_rerank, top_n=3, top_k=2)
    assert r.retrieve("任意问题") == []

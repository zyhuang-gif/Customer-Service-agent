"""检索编排：向量召回 top_n → rerank 精排 top_k → 带引用出处返回。"""
from __future__ import annotations

from typing import Callable

from app.retrieval.store import VectorStore

RerankFn = Callable[[str, list[str], int], list[tuple[int, float]]]


class Retriever:
    def __init__(self, store: VectorStore, rerank_fn: RerankFn, top_n: int, top_k: int):
        self.store = store
        self.rerank_fn = rerank_fn
        self.top_n = top_n
        self.top_k = top_k

    def retrieve(self, query: str) -> list[dict]:
        candidates = self.store.query(query, top_n=self.top_n)
        if not candidates:
            return []
        docs = [c["text"] for c in candidates]
        ranked = self.rerank_fn(query, docs, self.top_k)
        results: list[dict] = []
        for idx, score in ranked:
            c = candidates[idx]
            results.append({
                "title": c["title"],
                "source": c["source"],
                "text": c["text"],
                "score": score,
            })
        return results

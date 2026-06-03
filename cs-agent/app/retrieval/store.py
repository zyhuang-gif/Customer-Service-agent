"""Chroma 向量库封装。embedding 函数注入，便于单测不连网。"""
from __future__ import annotations

from typing import Callable

import chromadb

EmbedFn = Callable[[list[str]], list[list[float]]]


class VectorStore:
    def __init__(self, embed_fn: EmbedFn, persist_dir: str, collection: str = "knowledge"):
        self.embed_fn = embed_fn
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.collection_name = collection
        self.collection = self.client.get_or_create_collection(
            name=collection, metadata={"hnsw:space": "cosine"}
        )

    def reset(self) -> None:
        try:
            self.client.delete_collection(self.collection_name)
        except Exception:  # noqa: BLE001 - Chroma raises if the collection is absent.
            pass
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name, metadata={"hnsw:space": "cosine"}
        )

    def add_chunks(self, chunks: list[dict]) -> None:
        if not chunks:
            return
        texts = [c["text"] for c in chunks]
        embeddings = self.embed_fn(texts)
        start = self.collection.count()
        ids = [f"chunk-{start + i}" for i in range(len(chunks))]
        metadatas = [{"title": c["title"], "source": c["source"]} for c in chunks]
        self.collection.add(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)

    def count(self) -> int:
        return self.collection.count()

    def query(self, query_text: str, top_n: int) -> list[dict]:
        if self.collection.count() == 0:
            return []
        qvec = self.embed_fn([query_text])[0]
        res = self.collection.query(query_embeddings=[qvec], n_results=top_n)
        hits: list[dict] = []
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        dists = res.get("distances", [[]])[0]
        for doc, meta, dist in zip(docs, metas, dists):
            hits.append({
                "title": meta.get("title", ""),
                "source": meta.get("source", ""),
                "text": doc,
                "distance": dist,
            })
        return hits

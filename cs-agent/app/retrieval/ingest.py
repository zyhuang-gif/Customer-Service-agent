"""把 knowledge/ 下的文档切块并灌入 Chroma。用真实 DashScope embedding。"""
from __future__ import annotations

import pathlib

from app.clients.dashscope_client import DashScopeClient
from app.config import settings
from app.retrieval.chunking import chunk_markdown, chunk_text
from app.retrieval.store import VectorStore


def build_store() -> VectorStore:
    """构造一个使用真实 DashScope embedding 的 VectorStore。"""
    client = DashScopeClient()
    return VectorStore(
        embed_fn=client.embed_texts,
        persist_dir=settings.chroma_dir,
        collection="knowledge",
    )


def _chunks_for_file(path: pathlib.Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".md":
        chunks = chunk_markdown(text, source=path.name)
        return chunks or chunk_text(text, source=path.name)
    if path.suffix.lower() == ".txt":
        return chunk_text(text, source=path.name)
    return []


def ingest(force: bool = False) -> int:
    """读取知识目录、切块、灌库。返回灌入的 chunk 数。"""
    store = build_store()
    if force:
        store.reset()
    if store.count() > 0:
        print(f"知识库已有 {store.count()} 个 chunk，跳过灌入。")
        return store.count()

    kdir = pathlib.Path(settings.knowledge_dir)
    all_chunks: list[dict] = []
    for doc_file in sorted([*kdir.glob("*.md"), *kdir.glob("*.txt")]):
        all_chunks.extend(_chunks_for_file(doc_file))

    store.add_chunks(all_chunks)
    print(f"灌入 {len(all_chunks)} 个 chunk。")
    return len(all_chunks)


if __name__ == "__main__":
    ingest()

"""把 knowledge/ 下的文档切块并灌入 Chroma。用真实 DashScope embedding。"""
from __future__ import annotations

import pathlib

from app.clients.dashscope_client import DashScopeClient
from app.config import settings
from app.retrieval.chunking import chunk_markdown
from app.retrieval.store import VectorStore


def build_store() -> VectorStore:
    """构造一个使用真实 DashScope embedding 的 VectorStore。"""
    client = DashScopeClient()
    return VectorStore(
        embed_fn=client.embed_texts,
        persist_dir=settings.chroma_dir,
        collection="knowledge",
    )


def ingest() -> int:
    """读取知识目录、切块、灌库。返回灌入的 chunk 数。"""
    store = build_store()
    if store.count() > 0:
        print(f"知识库已有 {store.count()} 个 chunk，跳过灌入。")
        return store.count()

    kdir = pathlib.Path(settings.knowledge_dir)
    all_chunks: list[dict] = []
    for md_file in kdir.glob("*.md"):
        text = md_file.read_text(encoding="utf-8")
        all_chunks.extend(chunk_markdown(text, source=md_file.name))

    store.add_chunks(all_chunks)
    print(f"灌入 {len(all_chunks)} 个 chunk。")
    return len(all_chunks)


if __name__ == "__main__":
    ingest()

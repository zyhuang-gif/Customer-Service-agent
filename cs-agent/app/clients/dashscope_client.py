"""DashScope（百炼）embedding + rerank 客户端。封装云端调用，单测用 respx mock。

transport 参数仅供测试注入（httpx.MockTransport），生产环境传 None 使用默认传输。
"""
from __future__ import annotations

import httpx

from app.config import settings

DEFAULT_RERANK_URL = "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"


class DashScopeClient:
    def __init__(
        self,
        embedding_api_key: str | None = None,
        rerank_api_key: str | None = None,
        base_url: str | None = None,
        rerank_url: str | None = None,
        embedding_model: str | None = None,
        rerank_model: str | None = None,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ):
        # embedding 与 rerank 可用不同的 key（百炼分模型授权）；缺省回落到默认 key
        self.embedding_api_key = embedding_api_key if embedding_api_key is not None else settings.key_for_embedding()
        self.rerank_api_key = rerank_api_key if rerank_api_key is not None else settings.key_for_rerank()
        self.base_url = (base_url or settings.dashscope_base_url).rstrip("/")
        self.rerank_url = rerank_url or DEFAULT_RERANK_URL
        self.embedding_model = embedding_model or settings.embedding_model
        self.rerank_model = rerank_model or settings.rerank_model
        self.timeout = timeout
        # transport 仅供测试注入；生产环境为 None（使用 httpx 默认传输）
        self._transport = transport

    def _make_client(self) -> httpx.Client:
        if self._transport is not None:
            return httpx.Client(transport=self._transport, timeout=self.timeout)
        return httpx.Client(timeout=self.timeout)

    @staticmethod
    def _headers(api_key: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        with self._make_client() as client:
            resp = client.post(
                f"{self.base_url}/embeddings",
                headers=self._headers(self.embedding_api_key),
                json={"model": self.embedding_model, "input": texts},
            )
        resp.raise_for_status()
        data = sorted(resp.json()["data"], key=lambda d: d["index"])
        return [d["embedding"] for d in data]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def rerank(self, query: str, documents: list[str], top_k: int) -> list[tuple[int, float]]:
        with self._make_client() as client:
            resp = client.post(
                self.rerank_url,
                headers=self._headers(self.rerank_api_key),
                json={
                    "model": self.rerank_model,
                    "input": {"query": query, "documents": documents},
                    "parameters": {"top_n": top_k, "return_documents": False},
                },
            )
        resp.raise_for_status()
        results = resp.json()["output"]["results"]
        ranked = sorted(results, key=lambda r: r["relevance_score"], reverse=True)
        return [(r["index"], r["relevance_score"]) for r in ranked[:top_k]]

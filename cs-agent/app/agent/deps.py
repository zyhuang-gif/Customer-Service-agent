"""生产依赖装配：构造带 PostgresSaver 的对话服务。测试会 monkeypatch build_service 注入 mock。"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.agent.graph import build_graph
from app.agent.llm import build_llm
from app.agent.service import ConversationService
from app.clients.business_client import BusinessClient
from app.clients.dashscope_client import DashScopeClient
from app.config import settings
from app.retrieval.ingest import build_store
from app.retrieval.retriever import Retriever
from app.tools.registry import ToolRegistry

_checkpointer = None


def _get_checkpointer():
    global _checkpointer
    if _checkpointer is None:
        from langgraph.checkpoint.postgres import PostgresSaver
        conn = settings.database_url.replace("+psycopg", "")
        cm = PostgresSaver.from_conn_string(conn)
        _checkpointer = cm.__enter__()
        _checkpointer.setup()
    return _checkpointer


def build_service(db: Session) -> ConversationService:
    business = BusinessClient()
    ds = DashScopeClient()
    retriever = Retriever(store=build_store(), rerank_fn=ds.rerank,
                          top_n=settings.retrieve_top_n, top_k=settings.retrieve_top_k)
    registry = ToolRegistry(business=business, retriever=retriever)
    graph = build_graph(llm=build_llm(), registry=registry, checkpointer=_get_checkpointer())
    return ConversationService(db=db, graph=graph, business=business)

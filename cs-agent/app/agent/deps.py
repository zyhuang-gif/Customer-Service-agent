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
_checkpointer_cm = None  # 持有 contextmanager，保证应用生命周期内连接不被回收


def _get_checkpointer():
    global _checkpointer, _checkpointer_cm
    if _checkpointer is None:
        from langgraph.checkpoint.postgres import PostgresSaver
        conn = settings.database_url.replace("+psycopg", "")
        # from_conn_string 是 contextmanager：必须持有 cm 引用，否则连接被 GC 关闭。
        # 单例存活于整个应用生命周期；进程退出时由 OS 回收连接。
        _checkpointer_cm = PostgresSaver.from_conn_string(conn)
        _checkpointer = _checkpointer_cm.__enter__()
        _checkpointer.setup()
    return _checkpointer


_graph = None
_business = None
_registry = None


def _get_graph_and_business():
    """重组件（图/检索/Chroma/LLM/业务客户端）构造一次，进程级复用。

    首次调用会灌知识库 + PostgresSaver.setup，较慢；之后秒级。
    db 是请求级的，不在此缓存，由 build_service 每次传入。
    """
    global _graph, _business, _registry
    if _graph is None:
        _business = BusinessClient()
        ds = DashScopeClient()
        retriever = Retriever(store=build_store(), rerank_fn=ds.rerank,
                              top_n=settings.retrieve_top_n, top_k=settings.retrieve_top_k)
        _registry = ToolRegistry(business=_business, retriever=retriever)
        _graph = build_graph(llm=build_llm(), registry=_registry, checkpointer=_get_checkpointer())
    return _graph, _business, _registry


def build_service(db: Session) -> ConversationService:
    graph, business, registry = _get_graph_and_business()
    return ConversationService(db=db, graph=graph, business=business, registry=registry)


def warmup() -> None:
    """启动时预热：提前灌知识库 + setup checkpointer，避免首个请求超时。"""
    _get_graph_and_business()

"""构造连 qwen3-max 的 ChatOpenAI（OpenAI 兼容）。"""
from __future__ import annotations

from langchain_openai import ChatOpenAI

from app.config import settings


def build_llm(temperature: float = 0.0) -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.chat_model,
        api_key=settings.key_for_chat(),
        base_url=settings.dashscope_base_url,
        temperature=temperature,
    )

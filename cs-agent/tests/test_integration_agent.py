import pytest

from app.config import settings

pytestmark = pytest.mark.integration

skip_no_key = pytest.mark.skipif(not settings.key_for_chat(), reason="需要 chat key")


@skip_no_key
def test_llm_decides_to_call_get_order():
    """真实 qwen3-max：问订单状态/物流应触发 get_order 或 get_logistics 工具调用。

    "帮我查一下订单 xxx 到哪了" 语义偏物流，LLM 可能选 get_logistics（查轨迹）
    或 get_order（查订单状态）——两者都属正确的工具路由。
    """
    from app.agent.llm import build_llm
    from app.agent.tools_bind import ALL_TOOLS

    llm = build_llm().bind_tools(ALL_TOOLS)
    resp = llm.invoke([{"role": "user", "content": "帮我查一下订单 20260531002 到哪了"}])
    names = [tc["name"] for tc in (resp.tool_calls or [])]
    assert any(n in names for n in ("get_order", "get_logistics")), (
        f"期望 get_order 或 get_logistics，实际工具调用：{names}"
    )

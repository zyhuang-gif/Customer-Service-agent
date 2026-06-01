"""业务系统 HTTP 客户端。所有对业务系统的调用经此唯一出口。

约定：
- 2xx → 返回解析后的 dict / list
- 404 → 返回 None（资源不存在，不是异常）
- 超时 / 连接失败 / 5xx → 重试 retries 次后抛 BusinessUnavailable
"""
from __future__ import annotations

from typing import Any

import httpx

from app.config import settings
from app.errors import BusinessUnavailable


class BusinessClient:
    def __init__(
        self,
        base_url: str | None = None,
        timeout: float | None = None,
        retries: int | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        self.base_url = (base_url or settings.business_base_url).rstrip("/")
        self.timeout = timeout if timeout is not None else settings.business_timeout
        self.retries = retries if retries is not None else settings.business_retries
        # transport 仅供测试注入（如 respx MockTransport）；生产环境使用默认传输
        self._transport = transport

    def _make_client(self) -> httpx.Client:
        if self._transport is not None:
            return httpx.Client(transport=self._transport, timeout=self.timeout)
        return httpx.Client(timeout=self.timeout)

    def _request(self, method: str, path: str, **kwargs) -> Any | None:
        url = f"{self.base_url}{path}"
        last_exc: Exception | None = None
        attempts = self.retries + 1
        with self._make_client() as client:
            for _ in range(attempts):
                try:
                    resp = client.request(method, url, **kwargs)
                except (httpx.TimeoutException, httpx.TransportError) as exc:
                    last_exc = exc
                    continue
                if resp.status_code == 404:
                    return None
                if resp.status_code >= 500:
                    last_exc = BusinessUnavailable(
                        f"业务系统返回 {resp.status_code}", {"status": resp.status_code, "url": url}
                    )
                    continue
                if resp.status_code >= 400:
                    raise BusinessUnavailable(
                        f"业务系统请求错误 {resp.status_code}", {"status": resp.status_code, "url": url}
                    )
                return resp.json()
        raise BusinessUnavailable(
            "业务系统暂时不可用", {"url": url, "cause": str(last_exc)}
        )

    # ---- 只读 ----
    def get_customer(self, customer_id: str) -> dict | None:
        return self._request("GET", f"/customers/{customer_id}")

    def get_customer_by_phone(self, phone: str) -> dict | None:
        return self._request("GET", "/customers", params={"phone": phone})

    def get_order(self, order_id: str) -> dict | None:
        return self._request("GET", f"/orders/{order_id}")

    def list_orders(self, customer_id: str) -> list | None:
        return self._request("GET", "/orders", params={"customer_id": customer_id})

    def get_logistics(self, order_id: str) -> dict | None:
        return self._request("GET", "/logistics", params={"order_id": order_id})

    def get_refund_status(self, order_id: str) -> dict | None:
        return self._request("GET", "/refunds", params={"order_id": order_id})

    def list_customer_tickets(self, customer_id: str) -> list | None:
        return self._request("GET", "/tickets", params={"customer_id": customer_id})

    # ---- 低风险写 ----
    def create_ticket(self, customer_id: str, order_id: str | None, category: str, summary: str, priority: str) -> dict | None:
        return self._request("POST", "/tickets", json={
            "customer_id": customer_id, "order_id": order_id,
            "category": category, "summary": summary, "priority": priority,
        })

    def update_ticket(self, ticket_id: str, note: str | None = None, status: str | None = None, assignee: str | None = None) -> dict | None:
        return self._request("PATCH", f"/tickets/{ticket_id}", json={
            "note": note, "status": status, "assignee": assignee,
        })

    # ---- 高风险写（仅在编排层确认后才调用）----
    def apply_refund(self, order_id: str, amount: float, reason: str = "", channel: str = "原路退回") -> dict | None:
        return self._request("POST", "/refunds", json={
            "order_id": order_id, "amount": amount, "reason": reason, "channel": channel,
        })

    def change_address(self, order_id: str, new_address: str) -> dict | None:
        return self._request("PATCH", f"/orders/{order_id}/address", json={"new_address": new_address})

    def issue_coupon(self, customer_id: str, value: float, reason: str = "") -> dict | None:
        return self._request("POST", "/coupons", json={
            "customer_id": customer_id, "value": value, "reason": reason,
        })

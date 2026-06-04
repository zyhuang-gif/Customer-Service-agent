from datetime import datetime, timedelta, timezone

from app.auth import (
    create_access_token,
    create_customer_access_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.config import settings


def test_password_hash_roundtrip():
    h = hash_password("secret123")
    assert h != "secret123"
    assert verify_password("secret123", h) is True
    assert verify_password("wrong", h) is False


def test_jwt_roundtrip():
    token = create_access_token(subject="agent1", role="agent", user_id=5)
    payload = decode_token(token)
    assert payload["sub"] == "agent1"
    assert payload["role"] == "agent"
    assert payload["uid"] == 5


def test_decode_invalid_token_returns_none():
    assert decode_token("not-a-token") is None


def test_customer_access_token_contains_customer_claims_and_expires_in_seven_days():
    before = datetime.now(timezone.utc)

    token, expires_at = create_customer_access_token("C1001")

    after = datetime.now(timezone.utc)
    payload = decode_token(token)
    assert payload["sub"] == "C1001"
    assert payload["customer_ref"] == "C1001"
    assert payload["role"] == "customer"
    assert before + timedelta(days=7) - timedelta(seconds=1) <= expires_at <= after + timedelta(days=7)
    assert datetime.fromtimestamp(payload["exp"], timezone.utc) == expires_at
    assert settings.customer_jwt_expire_days == 7
    assert settings.customer_resume_hours == 2

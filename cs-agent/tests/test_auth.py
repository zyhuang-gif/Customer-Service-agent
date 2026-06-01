from app.auth import create_access_token, decode_token, hash_password, verify_password


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

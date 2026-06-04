"""轻量登录：密码哈希 + JWT 签发/校验。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
_ALGO = "HS256"


def hash_password(plain: str) -> str:
    return _pwd.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd.verify(plain, hashed)


def create_access_token(subject: str, role: str, user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": subject, "role": role, "uid": user_id, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=_ALGO)


def create_customer_access_token(customer_ref: str) -> tuple[str, datetime]:
    expire = (datetime.now(timezone.utc) + timedelta(days=settings.customer_jwt_expire_days)).replace(
        microsecond=0
    )
    payload = {
        "sub": customer_ref,
        "role": "customer",
        "customer_ref": customer_ref,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=_ALGO), expire


def decode_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[_ALGO])
    except JWTError:
        return None

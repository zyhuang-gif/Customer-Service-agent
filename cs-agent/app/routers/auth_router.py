from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth import create_access_token, decode_token, verify_password
from app.db import get_db
from app.models import User
from app.schemas_api import LoginIn, LoginOut

router = APIRouter(tags=["auth"])
_bearer = HTTPBearer(auto_error=False)


@router.post("/auth/login", response_model=LoginOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(username=body.username).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_access_token(subject=user.username, role=user.role, user_id=user.id)
    return LoginOut(access_token=token, role=user.role, display_name=user.display_name)


def current_user(cred: HTTPAuthorizationCredentials | None = Depends(_bearer), db: Session = Depends(get_db)) -> User:
    if cred is None:
        raise HTTPException(status_code=401, detail="未登录")
    payload = decode_token(cred.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="登录已失效")
    uid = payload.get("uid")
    if payload.get("role") not in {"agent", "admin"} or uid is None:
        raise HTTPException(status_code=401, detail="无坐席访问权限")
    user = db.get(User, uid)
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    if user.role not in {"agent", "admin"}:
        raise HTTPException(status_code=401, detail="无坐席访问权限")
    return user

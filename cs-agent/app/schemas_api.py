from pydantic import BaseModel


class LoginIn(BaseModel):
    username: str
    password: str


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    display_name: str


class ChatIn(BaseModel):
    conversation_id: str | None = None
    customer_ref: str
    message: str


class ConfirmIn(BaseModel):
    approved: bool

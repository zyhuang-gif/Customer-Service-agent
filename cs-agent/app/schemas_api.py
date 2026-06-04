from datetime import datetime

from pydantic import BaseModel, field_validator


class LoginIn(BaseModel):
    username: str
    password: str


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    display_name: str


class CustomerAuthIn(BaseModel):
    phone: str
    recent_order_id: str

    @field_validator("phone", "recent_order_id", mode="before")
    @classmethod
    def trim_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class CustomerAuthOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    masked_phone: str
    expires_at: datetime


class ChatIn(BaseModel):
    conversation_id: str | None = None
    customer_ref: str
    message: str


class ConfirmIn(BaseModel):
    approved: bool


class AgentReplyIn(BaseModel):
    content: str

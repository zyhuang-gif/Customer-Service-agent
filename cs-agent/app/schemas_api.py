from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class LoginIn(BaseModel):
    username: str
    password: str


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    display_name: str


class CustomerAuthIn(BaseModel):
    phone: str = Field(min_length=6, max_length=32)
    recent_order_id: str = Field(min_length=1, max_length=64)

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

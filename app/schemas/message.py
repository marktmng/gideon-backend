"""Pydantic schemas for Message."""
import uuid
from datetime import datetime
from typing import List, Literal
from pydantic import BaseModel, ConfigDict, Field

RoleType = Literal["user", "assistant", "system"]


class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=10000, description="Message content")


class MessageRead(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    role: RoleType
    content: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MessageListResponse(BaseModel):
    items: List[MessageRead]
    total: int
    page: int
    limit: int


class MessageExchangeResponse(BaseModel):
    user_message: MessageRead
    assistant_message: MessageRead

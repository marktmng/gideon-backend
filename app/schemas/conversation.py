"""Pydantic schemas for Conversation."""
import uuid
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field


class ConversationBase(BaseModel):
    title: Optional[str] = Field(None, max_length=255, description="Optional title for the conversation")


class ConversationCreate(ConversationBase):
    pass


class ConversationUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=255, description="Updated conversation title")


class ConversationRead(ConversationBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    message_count: Optional[int] = 0

    model_config = ConfigDict(from_attributes=True)


class ConversationListResponse(BaseModel):
    items: List[ConversationRead]
    total: int
    page: int
    limit: int

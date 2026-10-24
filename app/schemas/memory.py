"""Pydantic schemas for Persistent Memory entities."""
import uuid
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class MemoryBase(BaseModel):
    key: str = Field(..., min_length=1, max_length=255, description="Memory key or summary title")
    content: str = Field(..., min_length=1, max_length=10000, description="Detailed memory content")
    category: str = Field("general", min_length=1, max_length=64, description="Category or topic")


class MemoryCreate(MemoryBase):
    pass


class MemoryUpdate(BaseModel):
    key: Optional[str] = Field(None, min_length=1, max_length=255)
    content: Optional[str] = Field(None, min_length=1, max_length=10000)
    category: Optional[str] = Field(None, min_length=1, max_length=64)


class MemoryRead(MemoryBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MemoryListResponse(BaseModel):
    items: List[MemoryRead]
    total: int
    page: int
    limit: int

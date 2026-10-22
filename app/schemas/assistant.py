"""Pydantic schemas for Assistant status and system capabilities."""
from typing import List, Optional
from pydantic import BaseModel


class AssistantStatus(BaseModel):
    name: str = "Gideon"
    version: str = "1.0.0 (Phase 1)"
    provider: str
    is_demo: bool
    model: Optional[str] = None
    status: str = "online"
    capabilities: List[str]
    unconfigured_features: List[str]

"""Pydantic schemas for Assistant status and system capabilities."""
from typing import List, Optional
from pydantic import BaseModel


class AssistantStatus(BaseModel):
    name: str = "Gideon"
    version: str = "2.0.0 (Phase 2)"
    provider: str
    is_demo: bool
    model: Optional[str] = None
    status: str = "online"
    has_provider_credentials: bool = False
    streaming_supported: bool = True
    memory_enabled: bool = True
    database_connected: bool = True
    provider_initialized: bool = True
    capabilities: List[str]
    unconfigured_features: List[str]

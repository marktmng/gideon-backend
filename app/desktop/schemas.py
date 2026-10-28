"""Pydantic schemas for Windows Desktop Control and Task Lifecycle."""
import uuid
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field, ConfigDict, field_validator


class DesktopActionType(str, Enum):
    open_application = "open_application"
    activate_application = "activate_application"
    open_url = "open_url"
    open_directory = "open_directory"
    open_file_explorer = "open_file_explorer"
    inspect_active_window = "inspect_active_window"
    type_text = "type_text"
    press_shortcut = "press_shortcut"
    capture_screenshot = "capture_screenshot"
    click_accessible_element = "click_accessible_element"
    cancel_task = "cancel_task"


class TaskLifecycleStatus(str, Enum):
    idle = "idle"
    planning = "planning"
    awaiting_confirmation = "awaiting_confirmation"
    executing = "executing"
    completed = "completed"
    cancelled = "cancelled"
    error = "error"


class RiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


# ============================================================================
# Action Parameter Schemas
# ============================================================================

class EmptyParams(BaseModel):
    """Empty parameter model for parameterless actions."""
    pass


class OpenApplicationParams(BaseModel):
    app_name: str = Field(..., min_length=1, max_length=100, description="Application identifier (e.g. 'notepad', 'calculator')")
    args: Optional[List[str]] = Field(default=None, description="Optional safe command arguments")


class ActivateApplicationParams(BaseModel):
    target: str = Field(..., min_length=1, max_length=255, description="Target window title or application name")


class OpenUrlParams(BaseModel):
    url: str = Field(..., min_length=8, max_length=2048, description="Target HTTP/HTTPS URL")

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        trimmed = v.strip()
        lower = trimmed.lower()
        if not (lower.startswith("http://") or lower.startswith("https://")):
            raise ValueError("Only http:// and https:// URL schemes are permitted.")
        disallowed_chars = ["\n", "\r", "\t", '"', "'", ";", "|", "&", "<", ">"]
        if any(c in trimmed for c in disallowed_chars):
            raise ValueError("URL contains disallowed control characters.")
        return trimmed


class OpenDirectoryParams(BaseModel):
    path: str = Field(..., min_length=1, max_length=1024, description="Target filesystem path")

    @field_validator("path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        trimmed = v.strip()
        if ".." in trimmed:
            raise ValueError("Path traversal ('..') is strictly prohibited.")
        return trimmed


class TypeTextParams(BaseModel):
    target_window: str = Field(..., min_length=1, max_length=255, description="Target window title to type into")
    text: str = Field(..., min_length=1, max_length=1000, description="Text to type into active target")


class PressShortcutParams(BaseModel):
    target_window: str = Field(..., min_length=1, max_length=255, description="Target window title")
    shortcut: str = Field(..., min_length=1, max_length=50, description="Allowlisted shortcut key combination (e.g. 'Ctrl+C', 'Ctrl+V', 'Enter')")


class CaptureScreenshotParams(BaseModel):
    local_only: bool = Field(default=True, description="Enforce 100% local processing; never transmit externally")
    target: Optional[str] = Field(default=None, description="Optional target window title; defaults to full desktop")


class ClickAccessibleElementParams(BaseModel):
    target_window: str = Field(..., min_length=1, max_length=255, description="Target window title")
    element_name: str = Field(..., min_length=1, max_length=100, description="Accessible name or control ID")
    control_type: Optional[str] = Field(default=None, description="Accessible control type (e.g. 'Button', 'MenuItem')")


# Generic Action Request
class DesktopTaskCreate(BaseModel):
    action: DesktopActionType = Field(..., description="Action to perform")
    params: Dict[str, Any] = Field(default_factory=dict, description="Action-specific parameters")
    requires_confirmation: Optional[bool] = Field(default=None, description="Explicit override for confirmation requirement")


class DesktopTaskConfirmation(BaseModel):
    confirmed: bool = Field(..., description="True to approve execution, False to cancel")
    action: Optional[DesktopActionType] = Field(default=None, description="Action expected to be authorized")
    target: Optional[str] = Field(default=None, description="Target window/app expected to be authorized")
    reason: Optional[str] = Field(default=None, description="Optional note or cancellation rationale")


# ============================================================================
# Task Read & Telemetry Models
# ============================================================================

class ActiveWindowInfo(BaseModel):
    hwnd: int = Field(..., description="Window handle (HWND)")
    title: str = Field(..., description="Window title bar text")
    process_name: str = Field(..., description="Executable process name")
    pid: int = Field(..., description="Process identifier")
    is_elevated: bool = Field(default=False, description="Whether process runs with elevated administrative privileges")
    is_sensitive: bool = Field(default=False, description="Whether window is classified as sensitive (e.g. credentials, system security)")


class DesktopTaskRead(BaseModel):
    id: uuid.UUID = Field(..., description="Unique task identifier")
    action: DesktopActionType = Field(..., description="Action type")
    status: TaskLifecycleStatus = Field(..., description="Current lifecycle state")
    risk_level: RiskLevel = Field(..., description="Evaluated risk classification")
    requires_confirmation: bool = Field(..., description="Whether user confirmation is required prior to execution")
    target_app: Optional[str] = Field(default=None, description="Target application or window title")
    params: Dict[str, Any] = Field(default_factory=dict, description="Sanitized task parameters (secrets omitted)")
    result: Optional[Dict[str, Any]] = Field(default=None, description="Structured verified execution result")
    error: Optional[str] = Field(default=None, description="Error or diagnostic explanation if task failed")
    created_at: datetime = Field(..., description="Creation timestamp")
    started_at: Optional[datetime] = Field(default=None, description="Execution start timestamp")
    completed_at: Optional[datetime] = Field(default=None, description="Completion timestamp")

    model_config = ConfigDict(from_attributes=True)


class DesktopTaskListResponse(BaseModel):
    items: List[DesktopTaskRead]
    total: int


class ActionRegistryItem(BaseModel):
    action: DesktopActionType
    name: str
    description: str
    risk_level: RiskLevel
    requires_confirmation: bool
    parameter_schema: Dict[str, Any]


class GlobalStopResponse(BaseModel):
    stopped: bool
    message: str
    tasks_cancelled: int
    timestamp: datetime

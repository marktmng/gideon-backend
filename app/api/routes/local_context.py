"""Routes for local PC context tools: window inspection, native OCR, file exploration, and monitoring."""
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.dependencies import get_local_context_service, get_local_monitoring_service
from app.services.local_context_service import LocalContextService
from app.services.local_monitoring_service import LocalMonitoringService

router = APIRouter(prefix="/local-context", tags=["Local PC Context"])


class ToggleMonitoringRequest(BaseModel):
    enabled: Optional[bool] = Field(None, description="Explicit enable/disable state; if omitted, toggles.")


class ScreenOcrRequest(BaseModel):
    reason: Optional[str] = Field("api_request", description="Reason for screen capture and OCR audit log")


@router.get("/windows", summary="Enumerate open visible top-level application windows")
def get_open_windows(
    service: LocalContextService = Depends(get_local_context_service)
) -> Dict[str, Any]:
    windows = service.get_open_windows()
    active_win = next((w for w in windows if w.get("is_active")), None)
    return {
        "count": len(windows),
        "active_window": active_win,
        "windows": windows,
    }


@router.get("/active-window", summary="Inspect the current foreground active window")
def get_active_window(
    service: LocalContextService = Depends(get_local_context_service)
) -> Dict[str, Any]:
    return service.get_active_window()


@router.post("/ocr", summary="Capture desktop screen and extract text locally via Windows Native WinRT OCR")
def capture_screen_and_ocr(
    payload: Optional[ScreenOcrRequest] = None,
    service: LocalContextService = Depends(get_local_context_service)
) -> Dict[str, Any]:
    reason = payload.reason if payload else "api_request"
    result = service.capture_screen_with_ocr(reason=reason)
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("error", "Failed to capture or OCR screen."),
        )
    return result


@router.get("/tasks", summary="Query Gideon's persisted agent tasks, pending approvals, and failures")
def get_tasks_summary(
    db: Session = Depends(get_db),
    service: LocalContextService = Depends(get_local_context_service)
) -> Dict[str, Any]:
    return service.get_pending_tasks_and_approvals(db)


@router.get("/directory", summary="Safely summarize authorized workspace files and directories")
def summarize_directory(
    path: Optional[str] = Query(None, description="Optional relative subpath within authorized workspace root"),
    service: LocalContextService = Depends(get_local_context_service)
) -> Dict[str, Any]:
    summary = service.summarize_directory(target_path_str=path)
    if not summary.get("success"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN if "Access denied" in summary.get("error", "") else status.HTTP_400_BAD_REQUEST,
            detail=summary.get("error", "Failed to summarize directory."),
        )
    return summary


@router.get("/changes", summary="Summarize activities, completed tasks, and file changes since yesterday")
def get_changes_since_yesterday(
    db: Session = Depends(get_db),
    service: LocalContextService = Depends(get_local_context_service)
) -> Dict[str, Any]:
    return service.get_changes_since_yesterday(db)


@router.get("/errors", summary="Inspect and explain recent task or execution errors")
def explain_recent_errors(
    db: Session = Depends(get_db),
    service: LocalContextService = Depends(get_local_context_service)
) -> Dict[str, Any]:
    return service.explain_recent_errors(db)


@router.get("/monitoring", summary="Get status of opt-in local PC change monitoring and recent event log")
def get_monitoring_status(
    monitoring: LocalMonitoringService = Depends(get_local_monitoring_service),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    # Run an on-demand check if enabled
    monitoring.check_changes(db=db)
    return monitoring.get_status()


@router.post("/monitoring/toggle", summary="Toggle or set opt-in local PC change monitoring")
def toggle_monitoring(
    payload: Optional[ToggleMonitoringRequest] = None,
    monitoring: LocalMonitoringService = Depends(get_local_monitoring_service)
) -> Dict[str, Any]:
    enabled = payload.enabled if payload else None
    new_state = monitoring.toggle(enable=enabled)
    return {
        "is_enabled": new_state,
        "message": f"Local PC monitoring is now {'enabled' if new_state else 'disabled'}.",
    }


"""FastAPI routes for Windows Desktop Automation and Task Lifecycle."""
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, status, HTTPException, Query
from app.api.dependencies import get_desktop_service
from app.desktop.service import DesktopTaskService
from app.desktop.schemas import (
    DesktopTaskCreate,
    DesktopTaskRead,
    DesktopTaskListResponse,
    DesktopTaskConfirmation,
    ActiveWindowInfo,
    GlobalStopResponse,
    ActionRegistryItem,
    CaptureScreenshotParams,
)

router = APIRouter(prefix="/desktop", tags=["Desktop Automation"])


@router.get(
    "/actions",
    response_model=List[ActionRegistryItem],
    summary="List all registered and allowlisted desktop actions with schemas"
)
def list_supported_actions(
    service: DesktopTaskService = Depends(get_desktop_service)
):
    return service.get_supported_actions()


@router.get(
    "/active-window",
    response_model=ActiveWindowInfo,
    summary="Inspect current active foreground window"
)
def get_active_window(
    service: DesktopTaskService = Depends(get_desktop_service)
):
    return service.get_active_window()


@router.post(
    "/tasks",
    response_model=DesktopTaskRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create and execute or queue a desktop automation task"
)
def create_desktop_task(
    payload: DesktopTaskCreate,
    service: DesktopTaskService = Depends(get_desktop_service)
):
    try:
        task = service.create_task(
            action=payload.action,
            params=payload.params,
            requires_confirmation=payload.requires_confirmation
        )
        return task
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create desktop task: {e}")


@router.get(
    "/tasks",
    response_model=DesktopTaskListResponse,
    summary="List recent desktop automation tasks"
)
def list_desktop_tasks(
    limit: int = Query(50, ge=1, le=100),
    service: DesktopTaskService = Depends(get_desktop_service)
):
    tasks = service.list_tasks(limit=limit)
    return DesktopTaskListResponse(items=tasks, total=len(tasks))


@router.get(
    "/tasks/{task_id}",
    response_model=DesktopTaskRead,
    summary="Get details and verified status of a desktop task"
)
def get_desktop_task(
    task_id: uuid.UUID,
    service: DesktopTaskService = Depends(get_desktop_service)
):
    task = service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Desktop task '{task_id}' not found.")
    return task


@router.post(
    "/tasks/{task_id}/confirm",
    response_model=DesktopTaskRead,
    summary="Confirm or reject a task awaiting user approval"
)
def confirm_desktop_task(
    task_id: uuid.UUID,
    payload: DesktopTaskConfirmation,
    service: DesktopTaskService = Depends(get_desktop_service)
):
    try:
        task = service.confirm_task(
            task_id=task_id,
            confirmed=payload.confirmed,
            reason=payload.reason,
            expected_action=payload.action,
            expected_target=payload.target,
        )
        return task
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Execution error: {e}")


@router.post(
    "/tasks/{task_id}/cancel",
    response_model=DesktopTaskRead,
    summary="Cancel a pending or executing desktop task"
)
def cancel_desktop_task(
    task_id: uuid.UUID,
    service: DesktopTaskService = Depends(get_desktop_service)
):
    try:
        return service.cancel_task(task_id)
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post(
    "/stop",
    response_model=GlobalStopResponse,
    summary="Global Stop Control: Immediately halt all active desktop directives"
)
def global_stop(
    service: DesktopTaskService = Depends(get_desktop_service)
):
    return service.stop_all()


@router.post(
    "/screenshot",
    response_model=DesktopTaskRead,
    summary="Capture an on-demand desktop screenshot (strictly local)"
)
def capture_screenshot(
    payload: Optional[CaptureScreenshotParams] = None,
    service: DesktopTaskService = Depends(get_desktop_service)
):
    local_only = payload.local_only if payload else True
    target = payload.target if payload else None
    task = service.create_task(
        action=DesktopActionType.capture_screenshot,  # type: ignore
        params={"local_only": local_only, "target": target},
    )
    return task

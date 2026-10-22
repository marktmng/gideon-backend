"""Task API routes."""
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, status, Query, HTTPException
from app.api.dependencies import get_task_service
from app.core.exceptions import EntityNotFoundError
from app.schemas.task import (
    TaskCreate,
    TaskUpdate,
    TaskRead,
    TaskListResponse,
    TaskStatus,
)
from app.services.task_service import TaskService

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.post(
    "",
    response_model=TaskRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new task"
)
def create_task(
    payload: TaskCreate,
    service: TaskService = Depends(get_task_service)
):
    try:
        task = service.create_task(
            title=payload.title,
            description=payload.description,
            priority=payload.priority.value
        )
        return TaskRead.model_validate(task)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "",
    response_model=TaskListResponse,
    summary="List tasks with pagination and optional status filter"
)
def list_tasks(
    status_filter: Optional[TaskStatus] = Query(None, alias="status", description="Filter by status"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(50, ge=1, le=100, description="Tasks per page"),
    service: TaskService = Depends(get_task_service)
):
    skip = (page - 1) * limit
    status_val = status_filter.value if status_filter else None
    items, total = service.list_tasks(status=status_val, skip=skip, limit=limit)
    return TaskListResponse(
        items=[TaskRead.model_validate(t) for t in items],
        total=total,
        page=page,
        limit=limit
    )


@router.get(
    "/{task_id}",
    response_model=TaskRead,
    summary="Get task details by ID"
)
def get_task(
    task_id: uuid.UUID,
    service: TaskService = Depends(get_task_service)
):
    try:
        task = service.get_task(task_id)
        return TaskRead.model_validate(task)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.patch(
    "/{task_id}",
    response_model=TaskRead,
    summary="Update task fields or status"
)
def update_task(
    task_id: uuid.UUID,
    payload: TaskUpdate,
    service: TaskService = Depends(get_task_service)
):
    try:
        status_val = payload.status.value if payload.status else None
        priority_val = payload.priority.value if payload.priority else None
        task = service.update_task(
            task_id=task_id,
            title=payload.title,
            description=payload.description,
            status=status_val,
            priority=priority_val
        )
        return TaskRead.model_validate(task)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a task"
)
def delete_task(
    task_id: uuid.UUID,
    service: TaskService = Depends(get_task_service)
):
    try:
        service.delete_task(task_id)
        return None
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

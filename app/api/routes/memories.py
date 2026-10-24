"""Persistent Memory management API routes."""
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, status, Query, HTTPException
from app.api.dependencies import get_memory_service
from app.core.exceptions import EntityNotFoundError
from app.schemas.memory import (
    MemoryCreate,
    MemoryUpdate,
    MemoryRead,
    MemoryListResponse,
)
from app.services.memory_service import MemoryService

router = APIRouter(prefix="/memories", tags=["Memories"])


@router.post(
    "",
    response_model=MemoryRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a persistent memory"
)
def create_memory(
    payload: MemoryCreate,
    service: MemoryService = Depends(get_memory_service)
):
    try:
        memory = service.create_memory(
            key=payload.key,
            content=payload.content,
            category=payload.category
        )
        return MemoryRead.model_validate(memory)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "",
    response_model=MemoryListResponse,
    summary="List persistent memories with optional filtering and pagination"
)
def list_memories(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(50, ge=1, le=100, description="Items per page"),
    category: Optional[str] = Query(None, description="Filter by category"),
    search: Optional[str] = Query(None, description="Search term in key or content"),
    service: MemoryService = Depends(get_memory_service)
):
    items, total = service.list_memories(
        page=page,
        limit=limit,
        category=category,
        search=search
    )
    return MemoryListResponse(
        items=[MemoryRead.model_validate(m) for m in items],
        total=total,
        page=page,
        limit=limit
    )


@router.get(
    "/{memory_id}",
    response_model=MemoryRead,
    summary="Retrieve a persistent memory by ID"
)
def get_memory(
    memory_id: uuid.UUID,
    service: MemoryService = Depends(get_memory_service)
):
    try:
        memory = service.get_memory(memory_id)
        return MemoryRead.model_validate(memory)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.patch(
    "/{memory_id}",
    response_model=MemoryRead,
    summary="Update a persistent memory"
)
def update_memory(
    memory_id: uuid.UUID,
    payload: MemoryUpdate,
    service: MemoryService = Depends(get_memory_service)
):
    try:
        memory = service.update_memory(
            memory_id=memory_id,
            key=payload.key,
            content=payload.content,
            category=payload.category
        )
        return MemoryRead.model_validate(memory)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete(
    "/{memory_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a persistent memory"
)
def delete_memory(
    memory_id: uuid.UUID,
    service: MemoryService = Depends(get_memory_service)
):
    try:
        service.delete_memory(memory_id)
        return None
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

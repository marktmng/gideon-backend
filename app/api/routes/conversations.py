"""Conversation API routes."""
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, status, Query, HTTPException
from app.api.dependencies import get_conversation_service
from app.core.exceptions import EntityNotFoundError
from app.schemas.conversation import (
    ConversationCreate,
    ConversationUpdate,
    ConversationRead,
    ConversationListResponse,
)
from app.services.conversation_service import ConversationService

router = APIRouter(prefix="/conversations", tags=["Conversations"])


@router.post(
    "",
    response_model=ConversationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new conversation"
)
def create_conversation(
    payload: Optional[ConversationCreate] = None,
    service: ConversationService = Depends(get_conversation_service)
):
    title = payload.title if payload else None
    conversation = service.create_conversation(title=title)
    return conversation


@router.get(
    "",
    response_model=ConversationListResponse,
    summary="List conversations with pagination"
)
def list_conversations(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(50, ge=1, le=100, description="Items per page"),
    service: ConversationService = Depends(get_conversation_service)
):
    skip = (page - 1) * limit
    items, total = service.list_conversations(skip=skip, limit=limit)
    return ConversationListResponse(
        items=items,
        total=total,
        page=page,
        limit=limit
    )


@router.get(
    "/{conversation_id}",
    response_model=ConversationRead,
    summary="Get conversation by ID"
)
def get_conversation(
    conversation_id: uuid.UUID,
    service: ConversationService = Depends(get_conversation_service)
):
    try:
        return service.get_conversation(conversation_id)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.patch(
    "/{conversation_id}",
    response_model=ConversationRead,
    summary="Update conversation title"
)
def update_conversation(
    conversation_id: uuid.UUID,
    payload: ConversationUpdate,
    service: ConversationService = Depends(get_conversation_service)
):
    try:
        return service.update_conversation(conversation_id, title=payload.title)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete(
    "/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete conversation and associated messages"
)
def delete_conversation(
    conversation_id: uuid.UUID,
    service: ConversationService = Depends(get_conversation_service)
):
    try:
        service.delete_conversation(conversation_id)
        return None
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

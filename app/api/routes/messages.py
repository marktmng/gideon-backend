"""Message API routes."""
import uuid
from fastapi import APIRouter, Depends, status, Query, HTTPException
from app.api.dependencies import get_message_service
from app.core.exceptions import EntityNotFoundError, AIProviderError
from app.schemas.message import (
    MessageCreate,
    MessageListResponse,
    MessageExchangeResponse,
    MessageRead,
)
from app.services.message_service import MessageService

router = APIRouter(prefix="/conversations/{conversation_id}/messages", tags=["Messages"])


@router.post(
    "",
    response_model=MessageExchangeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit user message and receive assistant reply"
)
def submit_message(
    conversation_id: uuid.UUID,
    payload: MessageCreate,
    service: MessageService = Depends(get_message_service)
):
    try:
        user_msg, assistant_msg = service.submit_user_message(
            conversation_id=conversation_id,
            content=payload.content
        )
        return MessageExchangeResponse(
            user_message=MessageRead.model_validate(user_msg),
            assistant_message=MessageRead.model_validate(assistant_msg)
        )
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except AIProviderError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))


@router.get(
    "",
    response_model=MessageListResponse,
    summary="Retrieve conversation messages"
)
def list_messages(
    conversation_id: uuid.UUID,
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(100, ge=1, le=200, description="Messages per page"),
    service: MessageService = Depends(get_message_service)
):
    try:
        skip = (page - 1) * limit
        items, total = service.list_messages(
            conversation_id=conversation_id,
            skip=skip,
            limit=limit
        )
        return MessageListResponse(
            items=[MessageRead.model_validate(m) for m in items],
            total=total,
            page=page,
            limit=limit
        )
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

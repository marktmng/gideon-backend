"""Message API routes with synchronous and SSE streaming response support."""
import json
import uuid
from fastapi import APIRouter, Depends, status, Query, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.api.dependencies import get_message_service
from app.core.exceptions import (
    EntityNotFoundError,
    AIProviderError,
    AIConfigurationError,
    AIRateLimitError,
    AIProviderTimeoutError,
)
from app.core.logging import get_logger
from app.db.session import get_db, SessionLocal
from app.repositories.message_repository import MessageRepository
from app.schemas.message import (
    MessageCreate,
    MessageListResponse,
    MessageExchangeResponse,
    MessageRead,
)
from app.services.message_service import MessageService

logger = get_logger(__name__)

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
    except AIRateLimitError as e:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(e))
    except AIProviderTimeoutError as e:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(e))
    except AIConfigurationError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))
    except AIProviderError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))


@router.post(
    "/stream",
    summary="Submit user message and stream assistant response via Server-Sent Events (SSE)"
)
async def submit_message_stream(
    conversation_id: uuid.UUID,
    payload: MessageCreate,
    service: MessageService = Depends(get_message_service),
    db: Session = Depends(get_db)
):
    # 1. Validate conversation and persist user message before streaming begins
    try:
        user_msg, context_messages, relevant_memories = service.prepare_user_message(
            conversation_id=conversation_id,
            content=payload.content
        )
        db.commit()
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except AIConfigurationError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))
    except Exception as e:
        logger.error("Unexpected error preparing streaming message: %s", str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to initialize message session.")

    user_msg_data = {
        "id": str(user_msg.id),
        "conversation_id": str(user_msg.conversation_id),
        "role": user_msg.role,
        "content": user_msg.content,
        "created_at": user_msg.created_at.isoformat() if user_msg.created_at else None,
    }

    # 2. SSE event generator
    async def event_generator():
        # Start event
        start_payload = {
            "conversation_id": str(conversation_id),
            "user_message": user_msg_data,
            "relevant_memories_count": len(relevant_memories),
        }
        yield f"event: start\ndata: {json.dumps(start_payload)}\n\n"

        accumulated_chunks = []
        try:
            async for chunk in service.assistant_service.generate_stream(
                context_messages=context_messages,
                memories=relevant_memories
            ):
                if chunk:
                    accumulated_chunks.append(chunk)
                    delta_payload = {"delta": chunk}
                    yield f"event: delta\ndata: {json.dumps(delta_payload)}\n\n"

            final_text = "".join(accumulated_chunks).strip()
            if not final_text:
                raise AIProviderError("Provider response completed without text output.")

            # Persist the complete assistant response
            asst_msg = service.save_assistant_message(
                conversation_id=conversation_id,
                content=final_text
            )
            asst_msg_data = {
                "id": str(asst_msg.id),
                "conversation_id": str(asst_msg.conversation_id),
                "role": asst_msg.role,
                "content": asst_msg.content,
                "created_at": asst_msg.created_at.isoformat() if asst_msg.created_at else None,
            }

            # Complete event
            complete_payload = {
                "conversation_id": str(conversation_id),
                "assistant_message": asst_msg_data,
            }
            yield f"event: complete\ndata: {json.dumps(complete_payload)}\n\n"

        except Exception as err:
            logger.error("Error encountered during SSE streaming: %s", str(err))
            error_type = type(err).__name__
            clean_msg = str(err)
            error_payload = {
                "detail": clean_msg,
                "error_type": error_type
            }
            yield f"event: error\ndata: {json.dumps(error_payload)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


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

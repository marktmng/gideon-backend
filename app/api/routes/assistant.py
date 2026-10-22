"""Assistant capabilities and status routes."""
from fastapi import APIRouter, Depends
from app.api.dependencies import get_assistant_service
from app.schemas.assistant import AssistantStatus
from app.services.assistant_service import AssistantService

router = APIRouter(prefix="/assistant", tags=["Assistant"])


@router.get("/status", response_model=AssistantStatus, summary="Assistant runtime status and capabilities")
def get_assistant_status(
    service: AssistantService = Depends(get_assistant_service)
):
    return service.get_status()

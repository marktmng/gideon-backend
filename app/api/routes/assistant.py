"""Assistant capabilities and status routes."""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.api.dependencies import get_assistant_service
from app.db.session import get_db
from app.schemas.assistant import AssistantStatus
from app.services.assistant_service import AssistantService

router = APIRouter(prefix="/assistant", tags=["Assistant"])


@router.get("/status", response_model=AssistantStatus, summary="Assistant runtime status and capabilities")
def get_assistant_status(
    service: AssistantService = Depends(get_assistant_service),
    db: Session = Depends(get_db)
):
    db_connected = True
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_connected = False
    return service.get_status(db_connected=db_connected)

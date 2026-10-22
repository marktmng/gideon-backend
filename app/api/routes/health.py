"""Health check route endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import get_db

logger = get_logger(__name__)
router = APIRouter(tags=["Health"])


@router.get("/health", summary="Application health status")
def get_health(db: Session = Depends(get_db)):
    db_status = "connected"
    try:
        db.execute(text("SELECT 1"))
    except Exception as err:
        logger.error("Health check database probe failed: %s", str(err))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "unhealthy", "database": "disconnected"}
        )

    return {
        "status": "healthy",
        "app_name": settings.app_name,
        "environment": settings.app_env,
        "database": db_status,
        "database_type": "sqlite" if settings.is_sqlite else "postgresql",
        "ai_provider": settings.ai_provider,
        "demo_mode": settings.ai_provider.lower() == "demo"
    }

"""Assistant capabilities, provider switching, and Ollama status routes."""
import os
import re
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.dependencies import get_assistant_service
from app.db.session import get_db
from app.schemas.assistant import AssistantStatus
from app.services.assistant_service import AssistantService
from app.ai.ollama_provider import OllamaAIProvider
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/assistant", tags=["Assistant"])


class ProviderSwitchRequest(BaseModel):
    provider: str = Field(..., description="Target AI provider: 'ollama', 'gemini', or 'demo'")
    model: Optional[str] = Field(None, description="Model identifier (e.g. 'qwen2.5:3b', 'gemini-2.5-flash')")
    ollama_base_url: Optional[str] = Field(None, description="Optional custom base URL for Ollama")
    api_key: Optional[str] = Field(None, description="Optional API key for Gemini")
    validate_connection: Optional[bool] = Field(False, description="Whether to reject switch if service or model is unavailable")


def _persist_env_key(key: str, value: str):
    """Safely update or append a key in .env file."""
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env")
    if not os.path.exists(env_path):
        env_path = ".env"
    
    try:
        content = ""
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                content = f.read()

        pattern = rf"^{re.escape(key)}=.*$"
        replacement = f"{key}={value}"
        if re.search(pattern, content, flags=re.MULTILINE):
            new_content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
        else:
            new_content = content.rstrip() + f"\n{key}={value}\n"

        with open(env_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        logger.info("Persisted %s to %s", key, env_path)
    except Exception as exc:
        logger.warning("Could not persist %s to .env: %s", key, exc)


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
    return service.get_status(db_connected=db_connected, check_live=True)


@router.get("/ollama/status", summary="Check local Ollama runtime connection and available models")
def check_ollama_status(
    base_url: Optional[str] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    effective_url = base_url or settings.ollama_base_url
    effective_model = model or settings.ollama_model
    provider = OllamaAIProvider(base_url=effective_url, model=effective_model)
    return provider.check_connection()


@router.post("/provider", summary="Switch active AI provider and model at runtime")
def switch_ai_provider(
    payload: ProviderSwitchRequest,
    service: AssistantService = Depends(get_assistant_service),
) -> Dict[str, Any]:
    if payload.ollama_base_url:
        settings.ollama_base_url = payload.ollama_base_url
    
    if payload.api_key and payload.api_key.strip():
        clean_key = payload.api_key.strip()
        settings.gemini_api_key = clean_key
        settings.ai_api_key = clean_key
        _persist_env_key("GEMINI_API_KEY", clean_key)

    try:
        new_provider = service.switch_provider(
            provider_name=payload.provider,
            model=payload.model,
            validate_connection=bool(payload.validate_connection),
        )
        
        # Persist provider choice to .env
        _persist_env_key("AI_PROVIDER", new_provider.name)
        if payload.model:
            _persist_env_key("AI_MODEL", payload.model)

        return {
            "success": True,
            "provider": new_provider.name,
            "is_demo": new_provider.is_demo,
            "model": settings.ollama_model if new_provider.name == "ollama" else settings.ai_model,
            "message": f"Active AI provider successfully switched to '{new_provider.name}'.",
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

"""Root API router combining all route endpoints."""
from fastapi import APIRouter
from app.api.routes import health, conversations, messages, tasks, assistant, memories

api_router = APIRouter()

# Health endpoints
api_router.include_router(health.router)

# Resource endpoints
api_router.include_router(conversations.router)
api_router.include_router(messages.router)
api_router.include_router(tasks.router)
api_router.include_router(assistant.router)
api_router.include_router(memories.router)

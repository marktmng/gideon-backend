from fastapi import APIRouter
from app.api.routes import (
    health,
    conversations,
    messages,
    tasks,
    assistant,
    memories,
    desktop,
    agents,
    local_context,
    voice,
)

api_router = APIRouter()

# Health endpoints
api_router.include_router(health.router)

# Resource endpoints
api_router.include_router(conversations.router)
api_router.include_router(messages.router)
api_router.include_router(tasks.router)
api_router.include_router(assistant.router)
api_router.include_router(memories.router)
api_router.include_router(desktop.router)
api_router.include_router(agents.router)
api_router.include_router(local_context.router)
api_router.include_router(voice.router)

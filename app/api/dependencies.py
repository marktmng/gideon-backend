"""FastAPI dependencies for injecting repositories and services."""
from fastapi import Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.task_repository import TaskRepository
from app.repositories.memory_repository import MemoryRepository
from app.services.assistant_service import AssistantService
from app.services.conversation_service import ConversationService
from app.services.message_service import MessageService
from app.services.task_service import TaskService
from app.services.memory_service import MemoryService
from app.desktop.service import DesktopTaskService
from app.desktop.ai_tool_bridge import DesktopIntentBridge
from typing import Optional

_desktop_service_instance: Optional[DesktopTaskService] = None


def get_desktop_service() -> DesktopTaskService:
    global _desktop_service_instance
    if _desktop_service_instance is None:
        _desktop_service_instance = DesktopTaskService()
    return _desktop_service_instance


def get_desktop_intent_bridge(
    desktop_service: DesktopTaskService = Depends(get_desktop_service)
) -> DesktopIntentBridge:
    return DesktopIntentBridge(desktop_service=desktop_service)


def get_conversation_repository(db: Session = Depends(get_db)) -> ConversationRepository:
    return ConversationRepository(db)


def get_message_repository(db: Session = Depends(get_db)) -> MessageRepository:
    return MessageRepository(db)


def get_task_repository(db: Session = Depends(get_db)) -> TaskRepository:
    return TaskRepository(db)


def get_memory_repository(db: Session = Depends(get_db)) -> MemoryRepository:
    return MemoryRepository(db)


def get_assistant_service() -> AssistantService:
    return AssistantService()


def get_conversation_service(
    repo: ConversationRepository = Depends(get_conversation_repository)
) -> ConversationService:
    return ConversationService(repository=repo)


def get_memory_service(
    repo: MemoryRepository = Depends(get_memory_repository)
) -> MemoryService:
    return MemoryService(repository=repo)


def get_message_service(
    message_repo: MessageRepository = Depends(get_message_repository),
    conversation_repo: ConversationRepository = Depends(get_conversation_repository),
    assistant_service: AssistantService = Depends(get_assistant_service),
    memory_service: MemoryService = Depends(get_memory_service),
    desktop_bridge: DesktopIntentBridge = Depends(get_desktop_intent_bridge)
) -> MessageService:
    return MessageService(
        message_repo=message_repo,
        conversation_repo=conversation_repo,
        assistant_service=assistant_service,
        memory_service=memory_service,
        desktop_intent_bridge=desktop_bridge
    )


def get_task_service(
    repo: TaskRepository = Depends(get_task_repository)
) -> TaskService:
    return TaskService(repository=repo)


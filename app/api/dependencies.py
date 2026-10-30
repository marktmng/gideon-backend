"""FastAPI dependencies for injecting repositories and services."""
from typing import Optional, Any, TYPE_CHECKING
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
from app.services.daily_summary_service import DailySummaryService
from app.services.local_context_service import LocalContextService
from app.services.local_monitoring_service import LocalMonitoringService

if TYPE_CHECKING:
    from app.services.agent_service import AgentService

_desktop_service_instance: Optional[DesktopTaskService] = None
_agent_service_instance: Optional[Any] = None
_summary_service_instance: Optional[DailySummaryService] = None
_local_context_instance: Optional[LocalContextService] = None
_local_monitoring_instance: Optional[LocalMonitoringService] = None


def get_desktop_service() -> DesktopTaskService:
    global _desktop_service_instance
    if _desktop_service_instance is None:
        _desktop_service_instance = DesktopTaskService()
    return _desktop_service_instance


def get_local_context_service(
    desktop_service: DesktopTaskService = Depends(get_desktop_service)
) -> LocalContextService:
    global _local_context_instance
    if _local_context_instance is None:
        _local_context_instance = LocalContextService(desktop_adapter=desktop_service.adapter)
    return _local_context_instance


def get_local_monitoring_service(
    context_service: LocalContextService = Depends(get_local_context_service)
) -> LocalMonitoringService:
    global _local_monitoring_instance
    if _local_monitoring_instance is None:
        _local_monitoring_instance = LocalMonitoringService(context_service=context_service)
    return _local_monitoring_instance


def get_agent_service(
    desktop_service: DesktopTaskService = Depends(get_desktop_service)
) -> "AgentService":
    global _agent_service_instance
    if _agent_service_instance is None:
        from app.services.agent_service import AgentService
        _agent_service_instance = AgentService(desktop_service=desktop_service)
    return _agent_service_instance


def get_desktop_intent_bridge(
    desktop_service: DesktopTaskService = Depends(get_desktop_service),
    context_service: LocalContextService = Depends(get_local_context_service),
    agent_service: "AgentService" = Depends(get_agent_service),
    db: Session = Depends(get_db),
) -> DesktopIntentBridge:
    # Resolve fallback if called outside FastAPI dependency injection container
    ds = get_desktop_service() if hasattr(desktop_service, "dependency") or desktop_service is None else desktop_service
    cs = get_local_context_service(ds) if hasattr(context_service, "dependency") or context_service is None else context_service
    asvc = get_agent_service(ds) if hasattr(agent_service, "dependency") or agent_service is None else agent_service
    active_db = None if hasattr(db, "dependency") else db

    return DesktopIntentBridge(
        desktop_service=ds,
        context_service=cs,
        agent_service=asvc,
        db=active_db,
    )


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


def get_daily_summary_service() -> DailySummaryService:
    global _summary_service_instance
    if _summary_service_instance is None:
        _summary_service_instance = DailySummaryService()
    return _summary_service_instance

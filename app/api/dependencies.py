"""FastAPI dependencies for injecting repositories and services."""
from fastapi import Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.task_repository import TaskRepository
from app.services.assistant_service import AssistantService
from app.services.conversation_service import ConversationService
from app.services.message_service import MessageService
from app.services.task_service import TaskService


def get_conversation_repository(db: Session = Depends(get_db)) -> ConversationRepository:
    return ConversationRepository(db)


def get_message_repository(db: Session = Depends(get_db)) -> MessageRepository:
    return MessageRepository(db)


def get_task_repository(db: Session = Depends(get_db)) -> TaskRepository:
    return TaskRepository(db)


def get_assistant_service() -> AssistantService:
    return AssistantService()


def get_conversation_service(
    repo: ConversationRepository = Depends(get_conversation_repository)
) -> ConversationService:
    return ConversationService(repository=repo)


def get_message_service(
    message_repo: MessageRepository = Depends(get_message_repository),
    conversation_repo: ConversationRepository = Depends(get_conversation_repository),
    assistant_service: AssistantService = Depends(get_assistant_service)
) -> MessageService:
    return MessageService(
        message_repo=message_repo,
        conversation_repo=conversation_repo,
        assistant_service=assistant_service
    )


def get_task_service(
    repo: TaskRepository = Depends(get_task_repository)
) -> TaskService:
    return TaskService(repository=repo)

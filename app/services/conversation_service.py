"""Service for conversation management operations."""
import uuid
from typing import Optional, List, Tuple
from app.core.exceptions import EntityNotFoundError
from app.models.conversation import Conversation
from app.repositories.conversation_repository import ConversationRepository


class ConversationService:
    def __init__(self, repository: ConversationRepository):
        self.repository = repository

    def get_conversation(self, conversation_id: uuid.UUID) -> Conversation:
        conversation = self.repository.get_by_id(conversation_id)
        if not conversation:
            raise EntityNotFoundError("Conversation", str(conversation_id))
        return conversation

    def list_conversations(
        self,
        skip: int = 0,
        limit: int = 50
    ) -> Tuple[List[Conversation], int]:
        return self.repository.list_conversations(skip=skip, limit=limit)

    def create_conversation(self, title: Optional[str] = None) -> Conversation:
        clean_title = title.strip() if title else None
        return self.repository.create(title=clean_title)

    def update_conversation(
        self,
        conversation_id: uuid.UUID,
        title: Optional[str] = None
    ) -> Conversation:
        conversation = self.get_conversation(conversation_id)
        clean_title = title.strip() if title is not None else None
        return self.repository.update(conversation, title=clean_title)

    def delete_conversation(self, conversation_id: uuid.UUID) -> None:
        conversation = self.get_conversation(conversation_id)
        self.repository.delete(conversation)

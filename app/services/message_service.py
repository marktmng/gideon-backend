"""Service for message submission, context retrieval, and AI generation."""
import uuid
from typing import List, Tuple, Optional, Dict, Any
from app.core.config import settings
from app.core.exceptions import EntityNotFoundError, AIProviderError
from app.core.logging import get_logger
from app.models.message import Message
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.services.assistant_service import AssistantService
from app.services.memory_service import MemoryService

logger = get_logger(__name__)


class MessageService:
    def __init__(
        self,
        message_repo: MessageRepository,
        conversation_repo: ConversationRepository,
        assistant_service: AssistantService,
        memory_service: Optional[MemoryService] = None
    ):
        self.message_repo = message_repo
        self.conversation_repo = conversation_repo
        self.assistant_service = assistant_service
        self.memory_service = memory_service

    def list_messages(
        self,
        conversation_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100
    ) -> Tuple[List[Message], int]:
        conversation = self.conversation_repo.get_by_id(conversation_id)
        if not conversation:
            raise EntityNotFoundError("Conversation", str(conversation_id))

        return self.message_repo.list_by_conversation(
            conversation_id=conversation_id,
            skip=skip,
            limit=limit
        )

    def prepare_user_message(
        self,
        conversation_id: uuid.UUID,
        content: str
    ) -> Tuple[Message, List[Message], List[Dict[str, Any]]]:
        """
        Validate conversation, persist the user message, retrieve bounded chronological context
        and relevant reference memories.
        """
        conversation = self.conversation_repo.get_by_id(conversation_id)
        if not conversation:
            raise EntityNotFoundError("Conversation", str(conversation_id))

        clean_content = content.strip()
        if not clean_content:
            raise ValueError("Message content cannot be empty.")

        # Update conversation title if this is the first message
        if not conversation.title:
            auto_title = clean_content[:40] + ("..." if len(clean_content) > 40 else "")
            self.conversation_repo.update(conversation, title=auto_title)

        # Persist and commit user message so it is never lost if downstream generation fails
        user_message = self.message_repo.create(
            conversation_id=conversation_id,
            role="user",
            content=clean_content
        )
        self.message_repo.db.commit()

        # Retrieve bounded recent messages in chronological order
        context_limit = settings.ai_max_context_messages or 20
        context_messages = self.message_repo.get_recent_messages_for_context(
            conversation_id=conversation_id,
            limit=context_limit
        )

        # Retrieve bounded relevant memories for the prompt
        relevant_memories = []
        if self.memory_service:
            try:
                relevant_memories = self.memory_service.get_relevant_memories(
                    query=clean_content,
                    limit=settings.memory_max_retrieval_count
                )
            except Exception as mem_err:
                logger.warning("Memory retrieval encountered an issue (ignoring): %s", str(mem_err))

        return user_message, context_messages, relevant_memories

    def save_assistant_message(
        self,
        conversation_id: uuid.UUID,
        content: str
    ) -> Message:
        """Persist and commit assistant message."""
        clean_content = content.strip()
        if not clean_content:
            raise ValueError("Assistant response content cannot be empty.")

        msg = self.message_repo.create(
            conversation_id=conversation_id,
            role="assistant",
            content=clean_content
        )
        self.message_repo.db.commit()
        return msg

    def submit_user_message(
        self,
        conversation_id: uuid.UUID,
        content: str
    ) -> Tuple[Message, Message]:
        """
        Synchronous exchange: persist user message, invoke provider, persist assistant message.
        If provider generation fails, the user message remains safely persisted in the database
        without fabricating an assistant message.
        """
        user_message, context_messages, relevant_memories = self.prepare_user_message(
            conversation_id=conversation_id,
            content=content
        )

        # Generate assistant response
        try:
            assistant_reply_text = self.assistant_service.generate_response(
                context_messages=context_messages,
                memories=relevant_memories
            )
        except Exception as err:
            logger.error("Error generating assistant response: %s", str(err))
            raise

        # Persist assistant message
        assistant_message = self.save_assistant_message(
            conversation_id=conversation_id,
            content=assistant_reply_text
        )

        return user_message, assistant_message

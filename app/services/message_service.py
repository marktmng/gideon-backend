"""Service for message submission and retrieval."""
import uuid
from typing import List, Tuple
from app.core.exceptions import EntityNotFoundError, AIProviderError
from app.core.logging import get_logger
from app.models.message import Message
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.services.assistant_service import AssistantService

logger = get_logger(__name__)


class MessageService:
    def __init__(
        self,
        message_repo: MessageRepository,
        conversation_repo: ConversationRepository,
        assistant_service: AssistantService
    ):
        self.message_repo = message_repo
        self.conversation_repo = conversation_repo
        self.assistant_service = assistant_service

    def list_messages(
        self,
        conversation_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100
    ) -> Tuple[List[Message], int]:
        # Validate conversation exists
        conversation = self.conversation_repo.get_by_id(conversation_id)
        if not conversation:
            raise EntityNotFoundError("Conversation", str(conversation_id))

        return self.message_repo.list_by_conversation(
            conversation_id=conversation_id,
            skip=skip,
            limit=limit
        )

    def submit_user_message(
        self,
        conversation_id: uuid.UUID,
        content: str
    ) -> Tuple[Message, Message]:
        # 1. Validate conversation exists
        conversation = self.conversation_repo.get_by_id(conversation_id)
        if not conversation:
            raise EntityNotFoundError("Conversation", str(conversation_id))

        clean_content = content.strip()
        if not clean_content:
            raise ValueError("Message content cannot be empty.")

        # If conversation has no title, generate one from the first message
        if not conversation.title:
            auto_title = clean_content[:40] + ("..." if len(clean_content) > 40 else "")
            self.conversation_repo.update(conversation, title=auto_title)

        # 2. Persist user message
        user_message = self.message_repo.create(
            conversation_id=conversation_id,
            role="user",
            content=clean_content
        )

        # 3. Retrieve conversation context
        context_messages = self.message_repo.get_recent_messages_for_context(
            conversation_id=conversation_id,
            limit=20
        )

        # 4. Generate assistant response
        try:
            assistant_reply_text = self.assistant_service.generate_response(context_messages)
        except Exception as err:
            logger.error("Error generating assistant response: %s", str(err))
            raise AIProviderError(f"Assistant generation failed: {err}") from err

        # 5. Persist assistant message
        assistant_message = self.message_repo.create(
            conversation_id=conversation_id,
            role="assistant",
            content=assistant_reply_text
        )

        # 6. Return both saved messages
        return user_message, assistant_message

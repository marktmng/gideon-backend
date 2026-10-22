"""Repository for Conversation persistence operations."""
import uuid
from typing import Optional, List, Tuple
from sqlalchemy import select, func, desc
from sqlalchemy.orm import Session
from app.models.conversation import Conversation
from app.models.message import Message


class ConversationRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, conversation_id: uuid.UUID) -> Optional[Conversation]:
        stmt = select(Conversation).where(Conversation.id == conversation_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def list_conversations(
        self,
        skip: int = 0,
        limit: int = 50
    ) -> Tuple[List[Conversation], int]:
        total_stmt = select(func.count(Conversation.id))
        total = self.db.execute(total_stmt).scalar() or 0

        stmt = (
            select(Conversation)
            .order_by(desc(Conversation.updated_at))
            .offset(skip)
            .limit(limit)
        )
        items = list(self.db.execute(stmt).scalars().all())
        return items, total

    def create(self, title: Optional[str] = None) -> Conversation:
        conversation = Conversation(title=title)
        self.db.add(conversation)
        self.db.flush()
        self.db.refresh(conversation)
        return conversation

    def update(self, conversation: Conversation, title: Optional[str] = None) -> Conversation:
        if title is not None:
            conversation.title = title
        self.db.add(conversation)
        self.db.flush()
        self.db.refresh(conversation)
        return conversation

    def delete(self, conversation: Conversation) -> None:
        self.db.delete(conversation)
        self.db.flush()

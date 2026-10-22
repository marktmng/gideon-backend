"""Repository for Message persistence operations."""
import uuid
from typing import List, Tuple, Optional
from sqlalchemy import select, func, asc
from sqlalchemy.orm import Session
from app.models.message import Message


class MessageRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, message_id: uuid.UUID) -> Optional[Message]:
        stmt = select(Message).where(Message.id == message_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def list_by_conversation(
        self,
        conversation_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100
    ) -> Tuple[List[Message], int]:
        total_stmt = (
            select(func.count(Message.id))
            .where(Message.conversation_id == conversation_id)
        )
        total = self.db.execute(total_stmt).scalar() or 0

        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(asc(Message.created_at))
            .offset(skip)
            .limit(limit)
        )
        items = list(self.db.execute(stmt).scalars().all())
        return items, total

    def create(
        self,
        conversation_id: uuid.UUID,
        role: str,
        content: str
    ) -> Message:
        message = Message(
            conversation_id=conversation_id,
            role=role,
            content=content
        )
        self.db.add(message)
        self.db.flush()
        self.db.refresh(message)
        return message

    def get_recent_messages_for_context(
        self,
        conversation_id: uuid.UUID,
        limit: int = 20
    ) -> List[Message]:
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(asc(Message.created_at))
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars().all())

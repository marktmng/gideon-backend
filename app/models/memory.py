"""Memory database model for persistent long-term knowledge."""
import uuid
from datetime import datetime
from sqlalchemy import String, Text, DateTime, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, utc_now


class Memory(Base):
    __tablename__ = "memories"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4
    )
    key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )
    category: Mapped[str] = mapped_column(
        String(64),
        default="general",
        nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False
    )

    def __repr__(self) -> str:
        return f"<Memory id={self.id} key={self.key} category={self.category}>"

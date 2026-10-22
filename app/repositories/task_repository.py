"""Repository for Task persistence operations."""
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Tuple
from sqlalchemy import select, func, desc
from sqlalchemy.orm import Session
from app.models.task import Task


class TaskRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, task_id: uuid.UUID) -> Optional[Task]:
        stmt = select(Task).where(Task.id == task_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def list_tasks(
        self,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 50
    ) -> Tuple[List[Task], int]:
        total_stmt = select(func.count(Task.id))
        if status:
            total_stmt = total_stmt.where(Task.status == status)
        total = self.db.execute(total_stmt).scalar() or 0

        stmt = select(Task)
        if status:
            stmt = stmt.where(Task.status == status)

        stmt = stmt.order_by(desc(Task.created_at)).offset(skip).limit(limit)
        items = list(self.db.execute(stmt).scalars().all())
        return items, total

    def create(
        self,
        title: str,
        description: Optional[str] = None,
        priority: str = "medium"
    ) -> Task:
        task = Task(
            title=title,
            description=description,
            priority=priority,
            status="pending"
        )
        self.db.add(task)
        self.db.flush()
        self.db.refresh(task)
        return task

    def update(
        self,
        task: Task,
        title: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[str] = None,
        priority: Optional[str] = None
    ) -> Task:
        if title is not None:
            task.title = title
        if description is not None:
            task.description = description
        if priority is not None:
            task.priority = priority
        if status is not None:
            task.status = status
            if status == "completed":
                task.completed_at = datetime.now(timezone.utc)
            elif task.status != "completed":
                task.completed_at = None

        self.db.add(task)
        self.db.flush()
        self.db.refresh(task)
        return task

    def delete(self, task: Task) -> None:
        self.db.delete(task)
        self.db.flush()

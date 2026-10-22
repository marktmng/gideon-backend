"""Service for task management operations."""
import uuid
from typing import Optional, List, Tuple
from app.core.exceptions import EntityNotFoundError
from app.models.task import Task
from app.repositories.task_repository import TaskRepository


class TaskService:
    def __init__(self, repository: TaskRepository):
        self.repository = repository

    def get_task(self, task_id: uuid.UUID) -> Task:
        task = self.repository.get_by_id(task_id)
        if not task:
            raise EntityNotFoundError("Task", str(task_id))
        return task

    def list_tasks(
        self,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 50
    ) -> Tuple[List[Task], int]:
        return self.repository.list_tasks(status=status, skip=skip, limit=limit)

    def create_task(
        self,
        title: str,
        description: Optional[str] = None,
        priority: str = "medium"
    ) -> Task:
        clean_title = title.strip()
        if not clean_title:
            raise ValueError("Task title cannot be empty.")
        return self.repository.create(
            title=clean_title,
            description=description.strip() if description else None,
            priority=priority
        )

    def update_task(
        self,
        task_id: uuid.UUID,
        title: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[str] = None,
        priority: Optional[str] = None
    ) -> Task:
        task = self.get_task(task_id)
        clean_title = title.strip() if title is not None else None
        clean_desc = description.strip() if description is not None else None
        return self.repository.update(
            task=task,
            title=clean_title,
            description=clean_desc,
            status=status,
            priority=priority
        )

    def delete_task(self, task_id: uuid.UUID) -> None:
        task = self.get_task(task_id)
        self.repository.delete(task)

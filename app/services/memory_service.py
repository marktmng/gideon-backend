"""Service layer managing Memory business operations and contextual retrieval."""
import uuid
from typing import List, Tuple, Optional, Dict, Any
from app.core.config import settings
from app.core.exceptions import EntityNotFoundError
from app.models.memory import Memory
from app.repositories.memory_repository import MemoryRepository


class MemoryService:
    def __init__(self, repository: MemoryRepository):
        self.repository = repository

    def list_memories(
        self,
        page: int = 1,
        limit: int = 50,
        category: Optional[str] = None,
        search: Optional[str] = None
    ) -> Tuple[List[Memory], int]:
        skip = (page - 1) * limit
        return self.repository.list(
            skip=skip,
            limit=limit,
            category=category,
            search=search
        )

    def get_memory(self, memory_id: uuid.UUID) -> Memory:
        memory = self.repository.get_by_id(memory_id)
        if not memory:
            raise EntityNotFoundError("Memory", str(memory_id))
        return memory

    def create_memory(
        self,
        key: str,
        content: str,
        category: str = "general"
    ) -> Memory:
        clean_key = key.strip()
        clean_content = content.strip()
        clean_cat = (category or "general").strip().lower()

        if not clean_key:
            raise ValueError("Memory key/title cannot be empty.")
        if not clean_content:
            raise ValueError("Memory content cannot be empty.")

        return self.repository.create(
            key=clean_key,
            content=clean_content,
            category=clean_cat
        )

    def update_memory(
        self,
        memory_id: uuid.UUID,
        key: Optional[str] = None,
        content: Optional[str] = None,
        category: Optional[str] = None
    ) -> Memory:
        memory = self.get_memory(memory_id)

        update_data = {}
        if key is not None:
            clean_key = key.strip()
            if not clean_key:
                raise ValueError("Memory key cannot be empty.")
            update_data["key"] = clean_key

        if content is not None:
            clean_content = content.strip()
            if not clean_content:
                raise ValueError("Memory content cannot be empty.")
            update_data["content"] = clean_content

        if category is not None:
            update_data["category"] = category.strip().lower()

        return self.repository.update(memory, **update_data)

    def delete_memory(self, memory_id: uuid.UUID) -> None:
        memory = self.get_memory(memory_id)
        self.repository.delete(memory)

    def get_relevant_memories(
        self,
        query: str,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve bounded list of relevant memories formatted as untrusted reference context.
        """
        max_count = limit or settings.memory_max_retrieval_count or 5
        records = self.repository.search_relevant_memories(query=query, limit=max_count)
        return [
            {
                "id": str(m.id),
                "key": m.key,
                "content": m.content,
                "category": m.category,
            }
            for m in records
        ]

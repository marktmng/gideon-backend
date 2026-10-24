"""Repository for Memory persistence and keyword-based retrieval."""
import re
import uuid
from typing import List, Tuple, Optional
from sqlalchemy import select, func, desc, or_
from sqlalchemy.orm import Session
from app.models.memory import Memory

STOP_WORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are",
    "as", "at", "be", "because", "been", "before", "being", "below", "between", "both", "but",
    "by", "can", "did", "do", "does", "doing", "don", "down", "during", "each", "few", "for",
    "from", "further", "had", "has", "have", "having", "he", "her", "here", "hers", "herself",
    "him", "himself", "his", "how", "i", "if", "in", "into", "is", "it", "its", "itself", "just",
    "me", "more", "most", "my", "myself", "no", "nor", "not", "now", "of", "off", "on", "once",
    "only", "or", "other", "our", "ours", "ourselves", "out", "over", "own", "s", "same", "she",
    "should", "so", "some", "such", "t", "than", "that", "the", "their", "theirs", "them",
    "themselves", "then", "there", "these", "they", "this", "those", "through", "to", "too",
    "under", "until", "up", "very", "was", "we", "were", "what", "when", "where", "which", "while",
    "who", "whom", "why", "will", "with", "you", "your", "yours", "yourself", "yourselves",
    "gideon", "please", "remember", "tell", "show", "help"
}


class MemoryRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, memory_id: uuid.UUID) -> Optional[Memory]:
        stmt = select(Memory).where(Memory.id == memory_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def list(
        self,
        skip: int = 0,
        limit: int = 50,
        category: Optional[str] = None,
        search: Optional[str] = None
    ) -> Tuple[List[Memory], int]:
        base_query = select(Memory)
        count_query = select(func.count(Memory.id))

        if category and category.strip():
            cat_clean = category.strip().lower()
            base_query = base_query.where(func.lower(Memory.category) == cat_clean)
            count_query = count_query.where(func.lower(Memory.category) == cat_clean)

        if search and search.strip():
            pattern = f"%{search.strip().lower()}%"
            filter_expr = or_(
                func.lower(Memory.key).like(pattern),
                func.lower(Memory.content).like(pattern)
            )
            base_query = base_query.where(filter_expr)
            count_query = count_query.where(filter_expr)

        total = self.db.execute(count_query).scalar() or 0

        stmt = (
            base_query
            .order_by(desc(Memory.updated_at))
            .offset(skip)
            .limit(limit)
        )
        items = list(self.db.execute(stmt).scalars().all())
        return items, total

    def create(self, key: str, content: str, category: str = "general") -> Memory:
        clean_cat = (category or "general").strip().lower()
        memory = Memory(
            key=key.strip(),
            content=content.strip(),
            category=clean_cat
        )
        self.db.add(memory)
        self.db.flush()
        self.db.refresh(memory)
        return memory

    def update(self, memory: Memory, **kwargs) -> Memory:
        for field, value in kwargs.items():
            if value is not None and hasattr(memory, field):
                if isinstance(value, str):
                    value = value.strip()
                    if field == "category":
                        value = value.lower()
                setattr(memory, field, value)
        self.db.flush()
        self.db.refresh(memory)
        return memory

    def delete(self, memory: Memory) -> None:
        self.db.delete(memory)
        self.db.flush()

    def search_relevant_memories(self, query: str, limit: int = 5) -> List[Memory]:
        """
        Deterministic, bounded keyword-based memory retrieval.
        Extracts significant terms from the query, computes weighted match scores,
        and returns the top-ranked memories.
        """
        if not query or not query.strip():
            return []

        # Tokenize query into meaningful search keywords
        raw_tokens = re.findall(r"\b[a-zA-Z0-9_\-]{3,}\b", query.lower())
        tokens = [t for t in raw_tokens if t not in STOP_WORDS]

        if not tokens:
            return []

        # Fetch up to 100 recent candidate memories from database
        candidate_stmt = select(Memory).order_by(desc(Memory.updated_at)).limit(100)
        candidates = list(self.db.execute(candidate_stmt).scalars().all())

        scored_memories = []
        for mem in candidates:
            key_lower = mem.key.lower()
            content_lower = mem.content.lower()
            cat_lower = mem.category.lower()

            score = 0
            for token in tokens:
                # Key matches are weighted 3x
                if token in key_lower:
                    score += 3
                # Category matches are weighted 2x
                if token in cat_lower:
                    score += 2
                # Content matches are weighted 1x
                if token in content_lower:
                    score += 1

            if score > 0:
                scored_memories.append((score, mem.updated_at.timestamp() if mem.updated_at else 0, mem))

        # Sort descending by score, then by recency
        scored_memories.sort(key=lambda item: (item[0], item[1]), reverse=True)

        return [item[2] for item in scored_memories[:limit]]

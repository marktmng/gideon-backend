"""Event delivery and SSE subscription manager for Gideon Agent Engine."""
import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, AsyncIterator, Set, Optional
from app.core.logging import get_logger

logger = get_logger(__name__)


class ProgressEventPublisher:
    """Publishes real-time task progress events to SSE streams."""

    def __init__(self):
        # Mapping of task_id string -> Set of asyncio.Queue
        self._task_subscribers: Dict[str, Set[asyncio.Queue]] = {}
        # Global subscribers (all tasks)
        self._global_subscribers: Set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()

    async def subscribe(self, task_id: Optional[str] = None) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        async with self._lock:
            if task_id:
                if task_id not in self._task_subscribers:
                    self._task_subscribers[task_id] = set()
                self._task_subscribers[task_id].add(queue)
            else:
                self._global_subscribers.add(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue, task_id: Optional[str] = None):
        async with self._lock:
            if task_id and task_id in self._task_subscribers:
                self._task_subscribers[task_id].discard(queue)
                if not self._task_subscribers[task_id]:
                    del self._task_subscribers[task_id]
            else:
                self._global_subscribers.discard(queue)

    async def publish(
        self,
        event_type: str,
        task_id: uuid.UUID,
        payload: Dict[str, Any],
        step_key: Optional[str] = None,
    ):
        """Broadcast a validated event to task-specific and global subscribers."""
        event_data = {
            "event_type": event_type,
            "task_id": str(task_id),
            "step_key": step_key,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }
        task_id_str = str(task_id)

        async with self._lock:
            task_queues = list(self._task_subscribers.get(task_id_str, []))
            global_queues = list(self._global_subscribers)

        for q in task_queues + global_queues:
            try:
                q.put_nowait(event_data)
            except asyncio.QueueFull:
                logger.warning("Subscriber queue full; dropping event: %s", event_type)

    async def stream_events(self, task_id: Optional[str] = None) -> AsyncIterator[str]:
        """Async generator yielding Server-Sent Events (SSE) formatted text."""
        queue = await self.subscribe(task_id)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=25.0)
                    yield f"event: {event['event_type']}\ndata: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    # Keep-alive heartbeat ping every 25 seconds
                    yield "event: ping\ndata: {}\n\n"
        finally:
            await self.unsubscribe(queue, task_id)


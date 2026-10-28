"""Desktop task lifecycle service with validation, confirmation, and global stop controls."""
import uuid
import threading
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Tuple
from app.desktop.schemas import (
    DesktopActionType,
    TaskLifecycleStatus,
    RiskLevel,
    DesktopTaskRead,
    ActiveWindowInfo,
    GlobalStopResponse,
)
from app.desktop.security import DesktopSecurityPolicy
from app.desktop.adapter import BaseDesktopAdapter, WindowsDesktopAdapter
from app.desktop.registry import DesktopActionRegistry, ActionDefinition


class DesktopTaskService:
    """Manages the full lifecycle of Windows desktop automation directives."""

    def __init__(
        self,
        adapter: Optional[BaseDesktopAdapter] = None,
        security_policy: Optional[DesktopSecurityPolicy] = None,
        registry: Optional[DesktopActionRegistry] = None,
    ):
        self.security_policy = security_policy or DesktopSecurityPolicy()
        self.adapter = adapter or WindowsDesktopAdapter(self.security_policy)
        self.registry = registry or DesktopActionRegistry()

        # In-memory thread-safe task store
        self._tasks: Dict[uuid.UUID, DesktopTaskRead] = {}
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._max_history = 100

    def get_supported_actions(self) -> List[Dict[str, Any]]:
        """Return list of all registered actions and their schemas."""
        items = []
        for defn in self.registry.list_actions().values():
            items.append(defn.to_registry_item().model_dump())
        return items

    def get_active_window(self) -> ActiveWindowInfo:
        """Inspect current foreground window."""
        return self.adapter.inspect_active_window()

    def create_task(
        self,
        action: DesktopActionType,
        params: Dict[str, Any],
        requires_confirmation: Optional[bool] = None,
    ) -> DesktopTaskRead:
        """Create and validate a desktop task according to strict security policies."""
        self._stop_event.clear()
        action_def = self.registry.get(action)
        if not action_def:
            raise ValueError(f"Action '{action}' is not registered or supported by Gideon.")

        # Validate parameters against typed schema
        try:
            validated_params = action_def.param_schema.model_validate(params)
        except Exception as e:
            raise ValueError(f"Invalid parameters for action '{action}': {e}")

        # Determine risk and confirmation requirements
        risk_level, default_req_conf = self.security_policy.evaluate_risk(action, params)
        must_confirm = action_def.default_requires_confirmation or default_req_conf
        if requires_confirmation is not None:
            # User or system can require confirmation even if normally low-risk
            must_confirm = must_confirm or requires_confirmation

        # Sanitize parameters for storage and display
        sanitized_params = validated_params.model_dump()
        for k in list(sanitized_params.keys()):
            if "password" in k.lower() or "secret" in k.lower() or "token" in k.lower():
                sanitized_params[k] = "[REDACTED]"

        target_app = (
            params.get("target_window")
            or params.get("app_name")
            or params.get("target")
            or (params.get("url") if action == DesktopActionType.open_url else None)
        )

        task_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        initial_status = (
            TaskLifecycleStatus.awaiting_confirmation
            if must_confirm
            else TaskLifecycleStatus.planning
        )

        task = DesktopTaskRead(
            id=task_id,
            action=action,
            status=initial_status,
            risk_level=risk_level,
            requires_confirmation=must_confirm,
            target_app=str(target_app) if target_app else None,
            params=sanitized_params,
            result=None,
            error=None,
            created_at=now,
            started_at=None,
            completed_at=None,
        )

        with self._lock:
            self._tasks[task_id] = task
            # Enforce bounded history
            if len(self._tasks) > self._max_history:
                oldest_key = next(iter(self._tasks))
                del self._tasks[oldest_key]

        # If confirmation is not required, proceed directly with execution
        if not must_confirm:
            task = self._execute_task_internal(task_id, validated_params)

        return task

    def confirm_task(
        self,
        task_id: uuid.UUID,
        confirmed: bool,
        reason: Optional[str] = None,
        expected_action: Optional[DesktopActionType] = None,
        expected_target: Optional[str] = None,
    ) -> DesktopTaskRead:
        """Process user confirmation or rejection for a pending task with strict authorization binding."""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                raise KeyError(f"Task with ID '{task_id}' not found.")

            if task.status != TaskLifecycleStatus.awaiting_confirmation:
                raise ValueError(
                    f"Task '{task_id}' cannot be confirmed because it is in state '{task.status.value}'."
                )

            # Revalidate that the authorization is bound to the exact action and target being approved
            if expected_action and task.action != expected_action:
                raise ValueError(
                    f"Authorization mismatch: Expected action '{expected_action}' does not match task action '{task.action}'."
                )

            if expected_target and task.target_app:
                exp_t = expected_target.lower().strip()
                act_t = task.target_app.lower().strip()
                if exp_t not in act_t and act_t not in exp_t:
                    raise ValueError(
                        f"Authorization mismatch: Expected target '{expected_target}' does not match task target '{task.target_app}'."
                    )

            if not confirmed:
                updated_task = task.model_copy(
                    update={
                        "status": TaskLifecycleStatus.cancelled,
                        "error": reason or "Task cancelled by user confirmation rejection.",
                        "completed_at": datetime.now(timezone.utc),
                    }
                )
                self._tasks[task_id] = updated_task
                return updated_task

        # Re-validate params and execute
        action_def = self.registry.get(task.action)
        if not action_def:
            raise RuntimeError(f"Action '{task.action}' is no longer registered.")

        validated_params = action_def.param_schema.model_validate(task.params)
        return self._execute_task_internal(task_id, validated_params)

    def _execute_task_internal(self, task_id: uuid.UUID, validated_params: Any) -> DesktopTaskRead:
        """Execute action handler with robust exception handling and state transitions."""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                raise KeyError(f"Task with ID '{task_id}' not found.")

            # Ensure no queued action starts after cancellation or global stop
            if self._stop_event.is_set() or task.status == TaskLifecycleStatus.cancelled:
                cancelled_task = task.model_copy(
                    update={
                        "status": TaskLifecycleStatus.cancelled,
                        "error": "Emergency Global Stop initiated before execution started.",
                        "completed_at": datetime.now(timezone.utc),
                    }
                )
                self._tasks[task_id] = cancelled_task
                return cancelled_task

            action_def = self.registry.get(task.action)
            if not action_def:
                raise RuntimeError(f"Action '{task.action}' is no longer registered.")

            start_time = datetime.now(timezone.utc)
            executing_task = task.model_copy(
                update={
                    "status": TaskLifecycleStatus.executing,
                    "started_at": start_time,
                }
            )
            self._tasks[task_id] = executing_task

        # Perform execution outside lock so other calls are not blocked
        try:
            result = action_def.handler(self.adapter, validated_params)
            end_time = datetime.now(timezone.utc)

            with self._lock:
                # Check if task was cancelled while executing
                current = self._tasks.get(task_id)
                if current and current.status == TaskLifecycleStatus.cancelled:
                    return current

                completed_task = executing_task.model_copy(
                    update={
                        "status": TaskLifecycleStatus.completed,
                        "result": result,
                        "error": None,
                        "completed_at": end_time,
                    }
                )
                self._tasks[task_id] = completed_task
                return completed_task

        except Exception as e:
            end_time = datetime.now(timezone.utc)
            with self._lock:
                error_task = executing_task.model_copy(
                    update={
                        "status": TaskLifecycleStatus.error,
                        "result": None,
                        "error": str(e),
                        "completed_at": end_time,
                    }
                )
                self._tasks[task_id] = error_task
                return error_task

    def cancel_task(self, task_id: uuid.UUID) -> DesktopTaskRead:
        """Cancel an executing, planning, or awaiting desktop task."""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                raise KeyError(f"Task with ID '{task_id}' not found.")

            if task.status in (
                TaskLifecycleStatus.completed,
                TaskLifecycleStatus.cancelled,
                TaskLifecycleStatus.error,
            ):
                return task

            cancelled_task = task.model_copy(
                update={
                    "status": TaskLifecycleStatus.cancelled,
                    "error": "Task cancelled by user directive.",
                    "completed_at": datetime.now(timezone.utc),
                }
            )
            self._tasks[task_id] = cancelled_task
            return cancelled_task

    def stop_all(self) -> GlobalStopResponse:
        """Global Stop Control: Immediately halt and cancel all active desktop operations."""
        cancelled_count = 0
        now = datetime.now(timezone.utc)

        with self._lock:
            self._stop_event.set()
            for task_id, task in list(self._tasks.items()):
                if task.status in (
                    TaskLifecycleStatus.planning,
                    TaskLifecycleStatus.awaiting_confirmation,
                    TaskLifecycleStatus.executing,
                ):
                    self._tasks[task_id] = task.model_copy(
                        update={
                            "status": TaskLifecycleStatus.cancelled,
                            "error": "Emergency Global Stop initiated.",
                            "completed_at": now,
                        }
                    )
                    cancelled_count += 1

        return GlobalStopResponse(
            stopped=True,
            message=f"Global stop engaged. {cancelled_count} active desktop task(s) cancelled.",
            tasks_cancelled=cancelled_count,
            timestamp=now,
        )

    def get_task(self, task_id: uuid.UUID) -> Optional[DesktopTaskRead]:
        with self._lock:
            return self._tasks.get(task_id)

    def list_tasks(self, limit: int = 50) -> List[DesktopTaskRead]:
        with self._lock:
            tasks_list = list(self._tasks.values())
            tasks_list.sort(key=lambda t: t.created_at, reverse=True)
            return tasks_list[:limit]

"""Opt-in Local PC Monitoring Service for change detection with negligible CPU usage."""
import os
import sys
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
from collections import deque
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.services.local_context_service import LocalContextService
from app.models.agent import AgentTask, AgentApproval
from app.schemas.agent import TaskStatusEnum, ApprovalDecisionEnum

logger = get_logger(__name__)


class LocalMonitoringService:
    """
    Lightweight, opt-in local system monitor.
    Monitors:
    1. Active foreground application switches
    2. Agent task transitions and pending approval requests
    3. File modifications in the authorized workspace directory
    Designed for zero PC lag: low-frequency interval with cached state comparison.
    """

    def __init__(self, context_service: LocalContextService):
        self.context_service = context_service
        self.is_enabled: bool = settings.local_monitoring_enabled
        self.poll_interval: int = settings.local_monitoring_poll_interval_seconds
        
        # State caches
        self._last_active_window: Optional[str] = None
        self._last_task_counts: Dict[str, int] = {}
        self._file_mtimes: Dict[str, float] = {}
        
        # In-memory recent events ring buffer (last 50 events)
        self._recent_events: deque = deque(maxlen=50)

    def toggle(self, enable: Optional[bool] = None) -> bool:
        """Toggle or explicitly set monitoring state."""
        if enable is not None:
            self.is_enabled = enable
        else:
            self.is_enabled = not self.is_enabled
        
        logger.info("Local PC Monitoring status changed: is_enabled=%s", self.is_enabled)
        return self.is_enabled

    def get_status(self) -> Dict[str, Any]:
        """Get current monitoring status and recent event log."""
        return {
            "is_enabled": self.is_enabled,
            "poll_interval_seconds": self.poll_interval,
            "monitored_workspace": str(self.context_service.desktop_adapter.security_policy.workspace_root),
            "recent_events_count": len(self._recent_events),
            "recent_events": list(self._recent_events),
        }

    def check_changes(self, db: Optional[Session] = None) -> List[Dict[str, Any]]:
        """
        Perform a single, non-blocking check for local system changes.
        Returns a list of newly detected change events.
        """
        if not self.is_enabled:
            return []

        now_str = datetime.now(timezone.utc).isoformat()
        detected: List[Dict[str, Any]] = []

        # 1. Active Window switch check (sub-millisecond Win32 call)
        try:
            current_win = self.context_service.get_active_window()
            win_title = current_win.get("title", "")
            if self._last_active_window is not None and win_title != self._last_active_window:
                evt = {
                    "type": "foreground_app_switch",
                    "timestamp": now_str,
                    "details": f"Foreground window changed from '{self._last_active_window}' to '{win_title}'",
                    "process_name": current_win.get("process_name"),
                    "title": win_title,
                }
                detected.append(evt)
                self._recent_events.append(evt)
            self._last_active_window = win_title
        except Exception as e:
            logger.debug("Monitoring: active window check error: %s", str(e))

        # 2. Database Tasks & Approvals Check
        if db:
            try:
                active_statuses = [
                    TaskStatusEnum.queued.value,
                    TaskStatusEnum.planning.value,
                    TaskStatusEnum.running.value,
                    TaskStatusEnum.awaiting_approval.value,
                ]
                pending_count = db.query(AgentTask).filter(
                    AgentTask.status.in_(active_statuses)
                ).count()
                approval_count = db.query(AgentApproval).filter(
                    AgentApproval.status == ApprovalDecisionEnum.pending.value
                ).count()

                last_pending = self._last_task_counts.get("pending", 0)
                last_approvals = self._last_task_counts.get("approvals", 0)

                if self._last_task_counts and approval_count > last_approvals:
                    evt = {
                        "type": "approval_required",
                        "timestamp": now_str,
                        "details": f"New approval requested! Total pending approvals: {approval_count}",
                    }
                    detected.append(evt)
                    self._recent_events.append(evt)

                if self._last_task_counts and pending_count != last_pending:
                    evt = {
                        "type": "task_state_change",
                        "timestamp": now_str,
                        "details": f"Active/pending tasks changed from {last_pending} to {pending_count}",
                    }
                    detected.append(evt)
                    self._recent_events.append(evt)

                self._last_task_counts["pending"] = pending_count
                self._last_task_counts["approvals"] = approval_count
            except Exception as e:
                logger.debug("Monitoring: DB task check error: %s", str(e))

        # 3. Workspace File Modification Check (only checks top-level items for high performance)
        try:
            ws_root = Path(self.context_service.desktop_adapter.security_policy.workspace_root)
            if ws_root.exists() and ws_root.is_dir():
                for item in ws_root.iterdir():
                    if item.name.startswith((".", "__pycache__", "node_modules", ".venv")):
                        continue
                    try:
                        mtime = item.stat().st_mtime
                        last_mtime = self._file_mtimes.get(str(item))
                        if last_mtime is not None and mtime > last_mtime:
                            evt = {
                                "type": "file_modified",
                                "timestamp": now_str,
                                "filename": item.name,
                                "details": f"Workspace file or directory '{item.name}' was modified",
                            }
                            detected.append(evt)
                            self._recent_events.append(evt)
                        self._file_mtimes[str(item)] = mtime
                    except (OSError, PermissionError):
                        continue
        except Exception as e:
            logger.debug("Monitoring: workspace file check error: %s", str(e))

        return detected

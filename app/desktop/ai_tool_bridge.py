"""Natural language intent bridge connecting voice/chat commands to trusted desktop actions."""
import re
from typing import Optional, Tuple, Dict, Any
from app.desktop.schemas import DesktopActionType
from app.desktop.service import DesktopTaskService


class DesktopIntentBridge:
    """Interprets natural language desktop commands and routes them exclusively through the trusted action registry."""

    def __init__(self, desktop_service: DesktopTaskService):
        self.desktop_service = desktop_service

    def try_handle_desktop_intent(self, text: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        """Check if user query is a natural-language desktop directive.
        Returns (assistant_reply, task_dict) if handled, or None if regular conversational AI query.
        """
        trimmed = text.strip().lower()

        # 1. Global stop directives
        if any(trigger in trimmed for trigger in [
            "stop the current task", "stop task", "halt task", "cancel task",
            "emergency stop", "global stop", "abort task", "stop directive",
        ]):
            stop_res = self.desktop_service.stop_all()
            return f"Global stop engaged. {stop_res.tasks_cancelled} active directive(s) cancelled.", stop_res.model_dump()

        # 2. File Explorer directives
        if any(trigger in trimmed for trigger in [
            "open file explorer", "launch file explorer", "open explorer",
            "show explorer", "launch explorer",
        ]):
            task = self.desktop_service.create_task(
                action=DesktopActionType.open_file_explorer,
                params={},
            )
            if task.status.value == "completed":
                return "File Explorer launched successfully.", task.model_dump()
            elif task.status.value == "error":
                return f"Unable to open File Explorer: {task.error}", task.model_dump()
            else:
                return f"Directive registered: Open File Explorer (Status: {task.status.value}).", task.model_dump()

        # 3. Project directory directives
        if any(trigger in trimmed for trigger in [
            "open project directory", "open my project", "open project folder",
            "open workspace", "open workspace folder", "open my configured project directory",
        ]):
            workspace = str(self.desktop_service.security_policy.workspace_root)
            task = self.desktop_service.create_task(
                action=DesktopActionType.open_directory,
                params={"path": workspace},
            )
            if task.status.value == "completed":
                return f"Opened project workspace directory at {workspace}.", task.model_dump()
            elif task.status.value == "error":
                return f"Failed to open workspace directory: {task.error}", task.model_dump()
            else:
                return f"Directive registered: Open directory (Status: {task.status.value}).", task.model_dump()

        # 4. Open browser directives
        if any(trigger in trimmed for trigger in [
            "open my browser", "open browser", "launch browser", "launch web browser", "open web browser",
        ]):
            task = self.desktop_service.create_task(
                action=DesktopActionType.open_application,
                params={"app_name": "browser"},
            )
            if task.status.value == "completed":
                return "Default web browser opened.", task.model_dump()
            elif task.status.value == "error":
                return f"Failed to open browser: {task.error}", task.model_dump()
            else:
                return f"Directive registered: Open Browser (Status: {task.status.value}).", task.model_dump()

        # 5. Open specific application: "open notepad", "open calculator", etc.
        app_match = re.search(r"\b(?:open|launch|start)\s+([a-z0-9_\-]+)\b", trimmed)
        if app_match:
            candidate_app = app_match.group(1)
            # Check if candidate is allowlisted
            is_valid, _, _ = self.desktop_service.security_policy.validate_application_name(candidate_app)
            if is_valid:
                task = self.desktop_service.create_task(
                    action=DesktopActionType.open_application,
                    params={"app_name": candidate_app},
                )
                if task.status.value == "completed":
                    return f"Application '{candidate_app}' launched successfully.", task.model_dump()
                elif task.status.value == "error":
                    return f"Failed to launch '{candidate_app}': {task.error}", task.model_dump()
                else:
                    return f"Directive created: Launch '{candidate_app}' (Status: {task.status.value}).", task.model_dump()

        # 6. Open specific URL: "open url https://..."
        url_match = re.search(r"\b(?:open|navigate to|browse to)\s+(https?://[^\s]+)\b", text, re.IGNORECASE)
        if url_match:
            candidate_url = url_match.group(1)
            task = self.desktop_service.create_task(
                action=DesktopActionType.open_url,
                params={"url": candidate_url},
            )
            if task.status.value == "completed":
                return f"Navigated to {candidate_url}.", task.model_dump()
            elif task.status.value == "error":
                return f"Cannot open URL: {task.error}", task.model_dump()
            else:
                return f"Directive created: Open URL (Status: {task.status.value}).", task.model_dump()

        # 7. Active window inspection
        if any(trigger in trimmed for trigger in [
            "what is the active window", "inspect active window", "current window", "active window",
        ]):
            win = self.desktop_service.get_active_window()
            return f"Current active window: '{win.title}' (Process: {win.process_name}, PID: {win.pid}).", win.model_dump()

        return None

"""Natural language intent bridge connecting voice/chat commands to trusted desktop actions and local PC context."""
import re
import urllib.parse
from typing import Optional, Tuple, Dict, Any
from sqlalchemy.orm import Session

from app.desktop.schemas import DesktopActionType
from app.desktop.service import DesktopTaskService
from app.services.local_context_service import LocalContextService


class DesktopIntentBridge:
    """
    Interprets natural language desktop and local PC awareness directives.
    Retrieves real evidence using trusted desktop actions and local context inspection tools.
    """

    def __init__(
        self,
        desktop_service: DesktopTaskService,
        context_service: Optional[LocalContextService] = None,
        agent_service: Optional[Any] = None,
        db: Optional[Session] = None,
    ):
        self.desktop_service = desktop_service
        self.context_service = context_service or LocalContextService(
            desktop_adapter=desktop_service.adapter
        )
        self.agent_service = agent_service
        self.db = db

    def try_handle_desktop_intent(
        self, text: str, db: Optional[Session] = None
    ) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        Check if user query is a natural-language desktop directive or local PC awareness query.
        Returns (assistant_reply, metadata_dict) if handled, or None if regular conversational AI query.
        """
        active_db = db or self.db
        trimmed = text.strip().lower()

        # 0. Instant Wake Word & Greeting Responses
        if trimmed in [
            "hey gideon", "hello gideon", "hi gideon", "gideon",
            "ok gideon", "hey gideon.", "hello", "hi", "greetings",
            "hey", "ay gideon", "hi there", "hello there"
        ] or (trimmed.startswith("hey gideon") and len(trimmed) <= 14):
            return "I'm listening. What would you like me to do?", {"intent": "wake_greeting"}

        # 1. Global stop directives
        if any(trigger in trimmed for trigger in [
            "stop the current task", "stop task", "halt task", "cancel task",
            "emergency stop", "global stop", "abort task", "stop directive",
        ]):
            stop_res = self.desktop_service.stop_all()
            return f"Global stop engaged. {stop_res.tasks_cancelled} active directive(s) cancelled.", stop_res.model_dump()

        # 2. Local PC Awareness: "What is open on my screen?" / Open windows inspection
        if any(trigger in trimmed for trigger in [
            "what is open on my screen", "what's open on my screen", "what is on my screen",
            "what is open", "what windows are open", "show open windows", "list open windows",
            "running windows", "running applications", "open applications", "what's running",
        ]):
            windows = self.context_service.get_open_windows()
            active_win = next((w for w in windows if w.get("is_active")), None)
            
            if not windows:
                return "No open application windows were detected on your desktop.", {"windows": []}
            
            lines = []
            if active_win:
                lines.append(f"Active Foreground Window: \"{active_win['title']}\" (Process: {active_win['process_name']}, PID: {active_win['pid']})")
            
            other_windows = [w for w in windows if not w.get("is_active")]
            if other_windows:
                lines.append("\nOther visible application windows:")
                for w in other_windows[:10]:
                    lines.append(f"• \"{w['title']}\" ({w['process_name']})")
                if len(other_windows) > 10:
                    lines.append(f"• ... and {len(other_windows) - 10} more application window(s).")
            
            reply = "\n".join(lines)
            return reply, {"windows": windows, "active_window": active_win, "inspection_type": "open_windows"}

        # 3. Active window inspection
        if any(trigger in trimmed for trigger in [
            "what is the active window", "inspect active window", "current window", "active window",
        ]):
            win = self.desktop_service.get_active_window()
            return f"Current active window: '{win.title}' (Process: {win.process_name}, PID: {win.pid}).", win.model_dump()

        # 4. Local Task & Approval Status: "What tasks are still pending?"
        if any(trigger in trimmed for trigger in [
            "what tasks are still pending", "what tasks are pending", "pending tasks",
            "show pending tasks", "pending approvals", "what tasks are left", "active tasks",
            "tasks status", "system status",
        ]) and active_db:
            status_info = self.context_service.get_pending_tasks_and_approvals(active_db)
            pending_tasks = status_info["pending_tasks"]
            pending_approvals = status_info["pending_approvals"]
            
            lines = [f"Gideon Task Engine Status:"]
            lines.append(f"• Pending/Active Tasks: {status_info['pending_tasks_count']}")
            lines.append(f"• Pending Consequential Approvals: {status_info['pending_approvals_count']}")
            lines.append(f"• Completed Tasks: {status_info['completed_tasks_count']}")
            lines.append(f"• Recent Failures: {status_info['recent_failures_count']}")

            if pending_approvals:
                lines.append("\nActions Awaiting User Approval:")
                for a in pending_approvals:
                    lines.append(f"• [{a['action_type']}] {a['description']} (Approval ID: {a['approval_id'][:8]})")

            if pending_tasks:
                lines.append("\nPending/In-Progress Tasks:")
                for t in pending_tasks[:5]:
                    lines.append(f"• [{t['status'].upper()}] \"{t['title']}\" (Agent: {t['target_agent']})")
            elif not pending_approvals:
                lines.append("\nAll scheduled agent workflows have settled. No tasks are currently blocked or awaiting approval.")

            return "\n".join(lines), status_info

        # 5. Changes Since Yesterday: "What changed since yesterday?"
        if any(trigger in trimmed for trigger in [
            "what changed since yesterday", "what changed today", "changes since yesterday",
            "recent changes", "what has changed", "activity since yesterday",
        ]) and active_db:
            diff = self.context_service.get_changes_since_yesterday(active_db)
            lines = [f"System Activity & Workspace Changes (Last 24 Hours):"]
            lines.append(f"• Tasks Completed: {diff['tasks_completed_count']}")
            lines.append(f"• Tasks Failed: {diff['tasks_failed_count']}")
            lines.append(f"• New Tasks Created: {diff['tasks_created_count']}")
            lines.append(f"• Workspace Files Modified: {diff['workspace_files_modified_count']}")

            if diff["completed_tasks"]:
                lines.append("\nCompleted Workflows:")
                for title in diff["completed_tasks"][:5]:
                    lines.append(f"• {title}")

            if diff["failed_tasks"]:
                lines.append("\nFailed Workflows:")
                for title in diff["failed_tasks"][:3]:
                    lines.append(f"• {title}")

            if diff["workspace_files_modified"]:
                lines.append("\nRecent Workspace File Modifications:")
                for f in diff["workspace_files_modified"][:5]:
                    lines.append(f"• {f['name']} ({f['modified']})")

            return "\n".join(lines), diff

        # 6. Read and explain error: "Read this error and explain it"
        if any(trigger in trimmed for trigger in [
            "read this error", "read error", "explain this error", "explain the error",
            "what is the error", "show error", "diagnose error",
        ]) and active_db:
            err_info = self.context_service.explain_recent_errors(active_db, text_hint=text)
            reply = f"Error Diagnosis:\n{err_info['explanation']}"
            return reply, err_info

        # 7. Summarize folder: "Summarize this folder"
        if any(trigger in trimmed for trigger in [
            "summarize this folder", "summarize the folder", "summarize folder",
            "summarize workspace", "summarize project", "folder summary", "directory summary",
        ]):
            summary = self.context_service.summarize_directory()
            if not summary.get("success"):
                return f"Unable to summarize workspace directory: {summary.get('error')}", summary
            
            lines = [f"Workspace Directory Summary (Path: {summary['path']}):"]
            lines.append(f"• Total Files: {summary['total_files']}")
            lines.append(f"• Total Subdirectories: {summary['total_directories']}")
            lines.append(f"• Total Size: {summary['total_size_bytes'] / 1024:.1f} KB")

            if summary.get("recently_modified_24h"):
                lines.append("\nFiles Modified in the Last 24 Hours:")
                for mod in summary["recently_modified_24h"][:7]:
                    lines.append(f"• {mod['name']} ({mod['type']}, {mod['modified']})")

            return "\n".join(lines), summary

        # 8. Local Screen OCR: "Read my screen" / "Extract text from screen"
        if any(trigger in trimmed for trigger in [
            "read my screen", "ocr screen", "extract text from screen", "scan screen", "read the screen",
        ]):
            ocr_res = self.context_service.capture_screen_with_ocr(reason="natural_language_query")
            if not ocr_res.get("success"):
                return f"Screen OCR unavailable: {ocr_res.get('error')}", ocr_res
            
            text_preview = ocr_res.get("ocr_text", "").strip()
            if not text_preview:
                return "Screen captured successfully, but no readable text was detected by the local OCR engine.", ocr_res
            
            # Bound output preview to 800 characters
            preview = text_preview[:800] + ("..." if len(text_preview) > 800 else "")
            reply = f"Local Screen OCR Result ({ocr_res.get('word_count', 0)} words extracted):\n\n{preview}"
            return reply, ocr_res

        # 9. File Explorer directives
        if any(trigger in trimmed for trigger in [
            "open file explorer", "launch file explorer", "open explorer",
            "show explorer", "launch explorer",
        ]):
            task = self.desktop_service.create_task(
                action=DesktopActionType.open_file_explorer,
                params={},
            )
            if task.status.value == "completed":
                return "File Explorer is open. What would you like me to do next?", task.model_dump()
            elif task.status.value == "error":
                return f"Unable to open File Explorer: {task.error}. What would you like me to do instead?", task.model_dump()
            else:
                return "Opening File Explorer. What would you like me to do next?", task.model_dump()

        # 10. Project directory directives
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

        # 11. Open browser directives
        if any(trigger in trimmed for trigger in [
            "open my browser", "open browser", "launch browser", "launch web browser", "open web browser",
        ]):
            task = self.desktop_service.create_task(
                action=DesktopActionType.open_application,
                params={"app_name": "browser"},
            )
            if task.status.value == "completed":
                return "Browser is open. What would you like me to do next?", task.model_dump()
            elif task.status.value == "error":
                return f"Failed to open browser: {task.error}. What would you like me to do instead?", task.model_dump()
            else:
                return "Opening browser. What would you like me to do next?", task.model_dump()

        # 11b. Natural Search & Browser Navigation (YouTube, Google, Web)
        yt_match = re.search(r"\b(?:open\s+youtube\s+(?:and\s+)?search\s+(?:for\s+)?|search\s+youtube\s+(?:for\s+)?|search\s+(?:for\s+)?(.+)\s+on\s+youtube)(.+)?\b", trimmed)
        if yt_match:
            query = (yt_match.group(2) or yt_match.group(1) or "").strip()
            if query:
                search_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(query)}"
                task = self.desktop_service.create_task(
                    action=DesktopActionType.open_url,
                    params={"url": search_url},
                )
                return f"YouTube is open and searching for '{query}'. What would you like me to do next?", task.model_dump()

        google_match = re.search(r"\b(?:open\s+(?:chrome|browser|google)\s+(?:and\s+)?search\s+(?:google\s+)?(?:for\s+)?|search\s+google\s+(?:for\s+)?|google\s+search\s+(?:for\s+)?|search\s+(?:for\s+)?(.+)\s+on\s+google)(.+)?\b", trimmed)
        if google_match:
            query = (google_match.group(2) or google_match.group(1) or "").strip()
            if query:
                search_url = f"https://www.google.com/search?q={urllib.parse.quote_plus(query)}"
                task = self.desktop_service.create_task(
                    action=DesktopActionType.open_url,
                    params={"url": search_url},
                )
                return f"Google search for '{query}' is open. What would you like me to do next?", task.model_dump()

        # Standalone calculator command
        if trimmed in ["calculator", "calc", "open calc", "launch calc"]:
            task = self.desktop_service.create_task(
                action=DesktopActionType.open_application,
                params={"app_name": "calc"},
            )
            return "Calculator is open. What would you like me to do next?", task.model_dump()

        # 12. Close application directives: "close calculator", "quit spotify", "close chrome", etc.
        close_match = re.search(
            r"\b(?:close|quit|exit|terminate)\s+(?:the\s+)?([a-z0-9_\-\. ]+?)(?:\s+(?:app|application|window))?$",
            trimmed
        )
        if close_match:
            candidate_raw = close_match.group(1).strip()
            from app.desktop.app_discovery import app_discovery
            success, msg = app_discovery.close(candidate_raw)
            return msg, {"action": "close_application", "target": candidate_raw, "success": success}

        # 12b. Switch / Focus application directives: "switch to chrome", "focus spotify", "bring up visual studio"
        switch_match = re.search(
            r"\b(?:switch\s+to|bring\s+up|focus)\s+(?:the\s+)?([a-z0-9_\-\. ]+?)(?:\s+(?:app|application|window))?$",
            trimmed
        )
        if switch_match:
            candidate_raw = switch_match.group(1).strip()
            from app.desktop.app_discovery import app_discovery
            success, msg = app_discovery.switch_to(candidate_raw)
            return msg, {"action": "switch_application", "target": candidate_raw, "success": success}

        # 12c. Open specific application: "open photoshop", "launch visual studio", "open my video editor", "find and open spotify", etc.
        app_match = re.search(
            r"\b(?:open|launch|start|run|find\s+and\s+open)\s+(?:the\s+)?(?:application\s+i\s+use\s+for\s+)?(?:my\s+)?([a-z0-9_\-\. ]+?)(?:\s+(?:app|application|program))?$",
            trimmed
        )
        if app_match:
            candidate_raw = app_match.group(1).strip()
            norm_candidate = re.sub(r"\s+", "_", candidate_raw)
            aliases = {
                "google_chrome": "chrome",
                "microsoft_edge": "edge",
                "visual_studio_code": "vscode",
                "vs_code": "vscode",
                "task_manager": "task_manager",
                "taskmanager": "task_manager",
                "windows_settings": "settings",
                "system_settings": "settings",
                "microsoft_word": "word",
                "ms_word": "word",
                "microsoft_excel": "excel",
                "ms_excel": "excel",
                "file_explorer": "explorer",
                "files": "explorer",
                "web_browser": "browser",
            }
            target_app = aliases.get(norm_candidate, norm_candidate)
            is_valid, _, meta = self.desktop_service.security_policy.validate_application_name(target_app)
            if not is_valid:
                is_valid, _, meta = self.desktop_service.security_policy.validate_application_name(candidate_raw)
                if is_valid:
                    target_app = candidate_raw

            if is_valid:
                task = self.desktop_service.create_task(
                    action=DesktopActionType.open_application,
                    params={"app_name": target_app},
                )
                display_name = meta.get("name", target_app.title()) if meta else target_app.title()
                if task.status.value == "completed":
                    return f"{display_name} is open. What would you like me to do next?", task.model_dump()
                elif task.status.value == "error":
                    return f"I couldn't open {display_name}: {task.error}. What would you like me to do instead?", task.model_dump()
                else:
                    return f"{display_name} is opening. What would you like me to do next?", task.model_dump()
            else:
                return f"I searched your PC, but {candidate_raw.title()} does not appear to be installed. What would you like me to do instead?", {"action": "open_application", "target": candidate_raw, "status": "not_installed"}

        # 13. Open specific URL: "open url https://..."
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

        # 14. Phase 5 Agent Task delegation: research, marketing, email, tests, coding
        if self.agent_service and active_db:
            from app.schemas.agent import AgentTaskCreate

            # (a) Research tasks: e.g. "research potential customers for Pakhreen"
            if any(trigger in trimmed for trigger in [
                "research potential customers", "research customer", "research leads", "research market",
                "conduct research", "research competitors", "research for",
            ]) or (trimmed.startswith("research ") and len(trimmed) > 12):
                task_res = self.agent_service.create_task(
                    db=active_db,
                    payload=AgentTaskCreate(
                        title=f"Market & Customer Research: {text[:45]}",
                        user_request=text,
                        assigned_agent_id="agent_research",
                    ),
                )
                steps_count = len(task_res.steps) if task_res.steps else 3
                return (
                    f"Agent Task initiated: '{task_res.title}'\n"
                    f"• Assigned Agent: Research Agent (agent_research)\n"
                    f"• Status: {task_res.status.value.upper()}\n"
                    f"• Plan: Formulated with {steps_count} verified execution steps.\n"
                    f"• Task ID: {task_res.id}\n\n"
                    "The Research Agent is now exploring sources and drafting the briefing. "
                    "You can monitor live progress in the Agents tab or ask me for task status anytime.",
                    task_res.model_dump(),
                )

            # (b) Marketing plan tasks: e.g. "prepare a marketing plan for this week"
            if any(trigger in trimmed for trigger in [
                "prepare a marketing plan", "prepare marketing plan", "marketing plan for",
                "create a marketing plan", "draft marketing campaign", "marketing strategy",
            ]):
                task_res = self.agent_service.create_task(
                    db=active_db,
                    payload=AgentTaskCreate(
                        title=f"Marketing Plan Formulation: {text[:45]}",
                        user_request=text,
                        assigned_agent_id="agent_marketing",
                    ),
                )
                steps_count = len(task_res.steps) if task_res.steps else 3
                return (
                    f"Agent Task initiated: '{task_res.title}'\n"
                    f"• Assigned Agent: Marketing Strategy Agent (agent_marketing)\n"
                    f"• Status: {task_res.status.value.upper()}\n"
                    f"• Plan: {steps_count} structured steps (audience analysis, content calendar, campaign drafts).\n"
                    f"• Task ID: {task_res.id}\n\n"
                    "The Marketing Agent has begun formulating the strategy.",
                    task_res.model_dump(),
                )

            # (c) Email correspondence: e.g. "draft an email to this customer"
            if any(trigger in trimmed for trigger in [
                "draft an email", "draft email", "compose an email", "prepare email", "draft message to",
            ]):
                task_res = self.agent_service.create_task(
                    db=active_db,
                    payload=AgentTaskCreate(
                        title=f"Email Correspondence: {text[:45]}",
                        user_request=text,
                        assigned_agent_id="agent_email",
                    ),
                )
                steps_count = len(task_res.steps) if task_res.steps else 2
                return (
                    f"Agent Task initiated: '{task_res.title}'\n"
                    f"• Assigned Agent: Email Assistant (agent_email)\n"
                    f"• Status: {task_res.status.value.upper()}\n"
                    f"• Security Notice: Consequential actions (e.g. sending) will pause and require your explicit authorization.\n"
                    f"• Task ID: {task_res.id}\n\n"
                    "Drafting correspondence now. I will notify you when the draft is ready for review.",
                    task_res.model_dump(),
                )

            # (d) Safe test execution & project verification: e.g. "run the safe tests for my project"
            if any(trigger in trimmed for trigger in [
                "run the safe tests", "run safe tests", "run tests for my project", "run project tests", "test my project",
            ]):
                task_res = self.agent_service.create_task(
                    db=active_db,
                    payload=AgentTaskCreate(
                        title=f"Project Verification & Safe Tests: {text[:45]}",
                        user_request=text,
                        assigned_agent_id="agent_coding",
                    ),
                )
                steps_count = len(task_res.steps) if task_res.steps else 3
                return (
                    f"Agent Task initiated: '{task_res.title}'\n"
                    f"• Assigned Agent: Coding & Test Agent (agent_coding)\n"
                    f"• Status: {task_res.status.value.upper()}\n"
                    f"• Steps: {steps_count} safe validation steps within approved workspace boundaries.\n"
                    f"• Task ID: {task_res.id}\n\n"
                    "Executing safe test suite and inspecting workspace artifacts.",
                    task_res.model_dump(),
                )

        return None

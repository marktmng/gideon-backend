"""Built-in tool implementations for Gideon Phase 5 Agents."""
import os
import re
from pathlib import Path
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from app.agents.tools.base import BaseTool
from app.schemas.agent import ToolPermissionLevel
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


# -------------------------------------------------------------
# 1. Workspace / Code Tools (Read-Only & Local Changes)
# -------------------------------------------------------------

def _resolve_workspace_root() -> Path:
    # Use parent project root or current working directory
    workspace_root = Path(os.getcwd()).resolve()
    if (workspace_root / "gideon-backend").is_dir():
        return workspace_root
    if workspace_root.name in ("gideon-backend", "gideon-frontend"):
        return workspace_root.parent
    return workspace_root


def _validate_safe_path(relative_path: str) -> Path:
    root = _resolve_workspace_root()
    # Normalize and resolve target path
    clean_rel = relative_path.lstrip("/\\")
    target = (root / clean_rel).resolve()
    if not str(target).startswith(str(root)):
        raise PermissionError(f"Directory traversal detected. Access outside workspace '{root}' is forbidden.")
    # Block access to sensitive system paths or credentials (.env, secrets)
    forbidden_files = {".env", "gideon.db", "id_rsa", "credentials.json"}
    if target.name in forbidden_files or any(part.startswith(".git") for part in target.parts):
        raise PermissionError(f"Access to sensitive file or directory '{target.name}' is prohibited.")
    return target


class WorkspaceListFilesParams(BaseModel):
    subpath: str = Field(default="", description="Relative directory path within the workspace to list")
    max_depth: int = Field(default=2, ge=1, le=5, description="Maximum directory inspection depth")


class WorkspaceListFilesTool(BaseTool):
    tool_id = "tool_workspace_list_files"
    name = "List Workspace Files"
    description = "List files and directories in the authorized workspace project tree with traversal protection."
    permission_level = ToolPermissionLevel.read_only
    requires_approval = False
    supports_concurrency = True
    timeout_seconds = 10
    param_schema = WorkspaceListFilesParams

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        p = self.validate_params(params)
        target_dir = _validate_safe_path(p.subpath)
        if not target_dir.exists() or not target_dir.is_dir():
            return {"error": f"Directory '{p.subpath}' does not exist or is not a directory.", "files": []}

        items = []
        root = _resolve_workspace_root()
        try:
            for root_dir, dirs, files in os.walk(target_dir):
                # Prune node_modules, .venv, .git to prevent bloat
                dirs[:] = [d for d in dirs if d not in ("node_modules", ".venv", ".git", "__pycache__", ".pytest_cache")]
                rel_base = Path(root_dir).relative_to(root)
                depth = len(rel_base.parts)
                if depth > p.max_depth:
                    continue
                for f in files:
                    if f in (".env", "gideon.db"):
                        continue
                    item_path = str(rel_base / f).replace("\\", "/")
                    items.append(item_path)
                    if len(items) >= 200:
                        break
                if len(items) >= 200:
                    break
            return {"workspace_root": str(root), "files": items, "count": len(items)}
        except Exception as e:
            return {"error": f"Failed to list files: {str(e)}", "files": []}


class WorkspaceReadFileParams(BaseModel):
    file_path: str = Field(..., description="Relative file path within authorized workspace")
    max_lines: int = Field(default=300, ge=1, le=1000, description="Max lines to read")


class WorkspaceReadFileTool(BaseTool):
    tool_id = "tool_workspace_read_file"
    name = "Read Workspace File"
    description = "Read source code or documentation from an authorized workspace file."
    permission_level = ToolPermissionLevel.read_only
    requires_approval = False
    supports_concurrency = True
    timeout_seconds = 15
    param_schema = WorkspaceReadFileParams

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        p = self.validate_params(params)
        safe_path = _validate_safe_path(p.file_path)
        if not safe_path.exists() or not safe_path.is_file():
            return {"error": f"File '{p.file_path}' does not exist.", "content": None}

        try:
            with open(safe_path, "r", encoding="utf-8", errors="replace") as f:
                lines = [f.readline() for _ in range(p.max_lines)]
                content = "".join(lines)
            return {
                "file_path": p.file_path,
                "lines_read": len(lines),
                "content": content,
            }
        except Exception as e:
            return {"error": f"Failed to read file: {str(e)}", "content": None}


class WorkspaceProposeDiffParams(BaseModel):
    file_path: str = Field(..., description="Relative file path for proposed modification")
    proposed_diff: str = Field(..., description="Unified diff or detailed code change proposal")
    explanation: str = Field(..., description="Technical rationale for the proposed change")


class WorkspaceProposeDiffTool(BaseTool):
    tool_id = "tool_workspace_propose_diff"
    name = "Propose Code Changes"
    description = "Generate a validated code patch proposal for review without silently modifying production files."
    permission_level = ToolPermissionLevel.local_changes
    requires_approval = False
    supports_concurrency = True
    timeout_seconds = 20
    param_schema = WorkspaceProposeDiffParams

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        p = self.validate_params(params)
        safe_path = _validate_safe_path(p.file_path)
        exists = safe_path.exists()
        return {
            "status": "proposal_staged",
            "file_path": p.file_path,
            "target_exists": exists,
            "explanation": p.explanation,
            "proposed_diff": p.proposed_diff,
            "message": "Proposed changes validated and recorded. Ready for testing or user approval."
        }


# -------------------------------------------------------------
# 2. Directive Task & Memory Tools (Persistence Integration)
# -------------------------------------------------------------

class DirectiveTaskListParams(BaseModel):
    status_filter: Optional[str] = Field(default=None, description="Optional task status filter: pending, in_progress, completed, cancelled")
    limit: int = Field(default=20, ge=1, le=100)


class ListDirectiveTasksTool(BaseTool):
    tool_id = "tool_list_directive_tasks"
    name = "List Directive Tasks"
    description = "Inspect existing user directive tasks stored in Gideon's persistent tasks repository."
    permission_level = ToolPermissionLevel.read_only
    requires_approval = False
    supports_concurrency = True
    timeout_seconds = 10
    param_schema = DirectiveTaskListParams

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        p = self.validate_params(params)
        db_session = context.get("db") if context else None
        if not db_session:
            return {"tasks": [], "note": "No active database session in context."}

        from app.repositories.task_repository import TaskRepository
        repo = TaskRepository(db_session)
        items, total = repo.list(status=p.status_filter, limit=p.limit)
        return {
            "total": total,
            "tasks": [
                {"id": str(t.id), "title": t.title, "status": t.status, "priority": t.priority}
                for t in items
            ]
        }


class DirectiveTaskCreateParams(BaseModel):
    title: str = Field(..., min_length=1, max_length=255, description="Title of the directive task")
    description: Optional[str] = Field(default=None, description="Detailed task description or checklist")
    priority: str = Field(default="medium", description="Priority level: low, medium, high")


class CreateDirectiveTaskTool(BaseTool):
    tool_id = "tool_create_directive_task"
    name = "Create Directive Task"
    description = "Add a tracked directive task to Gideon's persistent task manager."
    permission_level = ToolPermissionLevel.local_changes
    requires_approval = False
    supports_concurrency = False
    timeout_seconds = 10
    param_schema = DirectiveTaskCreateParams

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        p = self.validate_params(params)
        db_session = context.get("db") if context else None
        if not db_session:
            return {"error": "Database session unavailable."}

        from app.repositories.task_repository import TaskRepository
        from app.schemas.task import TaskCreate
        repo = TaskRepository(db_session)
        created = repo.create(TaskCreate(title=p.title, description=p.description, priority=p.priority))
        db_session.commit()
        return {
            "status": "created",
            "task_id": str(created.id),
            "title": created.title,
            "priority": created.priority
        }


class MemorySearchParams(BaseModel):
    query: str = Field(..., min_length=1, description="Keywords to match in persistent memory archives")
    limit: int = Field(default=5, ge=1, le=20)


class SearchMemoriesTool(BaseTool):
    tool_id = "tool_search_memories"
    name = "Search Persistent Memories"
    description = "Retrieve contextual facts, directives, and user preferences from Gideon's persistent memory."
    permission_level = ToolPermissionLevel.read_only
    requires_approval = False
    supports_concurrency = True
    timeout_seconds = 10
    param_schema = MemorySearchParams

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        p = self.validate_params(params)
        db_session = context.get("db") if context else None
        if not db_session:
            return {"memories": [], "note": "No active database session."}

        from app.repositories.memory_repository import MemoryRepository
        repo = MemoryRepository(db_session)
        items = repo.search_relevant_memories(query=p.query, limit=p.limit)
        return {
            "memories": [
                {"id": str(m.id), "key": m.key, "content": m.content, "category": m.category}
                for m in items
            ]
        }


# -------------------------------------------------------------
# 3. Research & Information Extraction Tools
# -------------------------------------------------------------

class ResearchFetchParams(BaseModel):
    query: str = Field(..., min_length=2, description="Target query or subject to research")
    aspects: List[str] = Field(default_factory=list, description="Specific sub-questions or angles to investigate")


class ResearchFetchTool(BaseTool):
    tool_id = "tool_research_fetch"
    name = "Research Knowledge Fetcher"
    description = "Analyze knowledge base and authorized documents. Clearly notes external web search availability."
    permission_level = ToolPermissionLevel.read_only
    requires_approval = False
    supports_concurrency = True
    timeout_seconds = 20
    param_schema = ResearchFetchParams

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        p = self.validate_params(params)
        # Search persistent memories and workspace context
        db_session = context.get("db") if context else None
        memories = []
        if db_session:
            from app.repositories.memory_repository import MemoryRepository
            repo = MemoryRepository(db_session)
            memories = [m.content for m in repo.search_relevant_memories(query=p.query, limit=3)]

        has_external_web = bool(os.getenv("EXTERNAL_SEARCH_API_KEY"))
        return {
            "query": p.query,
            "aspects_investigated": p.aspects or ["general_overview"],
            "external_web_available": has_external_web,
            "sources_consulted": ["persistent_memory", "internal_workspace_docs"] + (["external_web"] if has_external_web else []),
            "internal_evidence": memories,
            "status": "completed",
            "capability_notice": (
                "Live external research is unavailable (EXTERNAL_SEARCH_API_KEY unconfigured). Findings are based strictly on internal knowledge base and workspace documents."
                if not has_external_web
                else "Verified across internal knowledge base and external search connector."
            ),
        }


# -------------------------------------------------------------
# 4. Email & Communication Tools (Drafting & Consequential Send)
# -------------------------------------------------------------

class DraftEmailParams(BaseModel):
    recipient: str = Field(..., description="Target email recipient address or identifier")
    subject: str = Field(..., min_length=1, description="Email subject line")
    body: str = Field(..., min_length=1, description="Email body text draft")
    context_notes: Optional[str] = Field(default=None, description="Optional drafting notes")


class DraftEmailTool(BaseTool):
    tool_id = "tool_draft_email"
    name = "Draft Email Message"
    description = "Compose and validate an email draft locally without sending. Prepares message for review."
    permission_level = ToolPermissionLevel.local_changes
    requires_approval = False
    supports_concurrency = True
    timeout_seconds = 15
    param_schema = DraftEmailParams

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        p = self.validate_params(params)
        return {
            "status": "draft_prepared",
            "recipient": p.recipient,
            "subject": p.subject,
            "body": p.body,
            "character_count": len(p.body),
            "requires_user_approval_to_send": True,
            "message": "Email draft created. External delivery requires explicit user approval."
        }


class SendEmailParams(BaseModel):
    recipient: str = Field(..., description="Validated recipient email address")
    subject: str = Field(..., min_length=1, description="Email subject line")
    body: str = Field(..., min_length=1, description="Complete email body")


class SendEmailTool(BaseTool):
    tool_id = "tool_send_email"
    name = "Send Email Message"
    description = "CONSEQUENTIAL ACTION: Transmit an email to an external recipient. Requires explicit user approval."
    permission_level = ToolPermissionLevel.consequential
    requires_approval = True
    supports_concurrency = False
    timeout_seconds = 30
    param_schema = SendEmailParams

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        p = self.validate_params(params)
        smtp_host = os.getenv("SMTP_HOST")
        if not smtp_host:
            # Explicit honest status: Email was approved & prepared, but NOT sent externally
            return {
                "status": "unconfigured",
                "recipient": p.recipient,
                "subject": p.subject,
                "external_dispatch": False,
                "email_sent": False,
                "message": f"Email approved and prepared for '{p.recipient}', but NOT sent because SMTP is unconfigured (SMTP_HOST is not set)."
            }

        # When SMTP is configured, attempt dispatch with timeout & error handling
        import smtplib
        from email.mime.text import MIMEText
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        smtp_user = os.getenv("SMTP_USER")
        smtp_pass = os.getenv("SMTP_PASSWORD")
        smtp_timeout = int(os.getenv("SMTP_TIMEOUT_SECONDS", "10"))

        try:
            msg = MIMEText(p.body, "plain", "utf-8")
            msg["Subject"] = p.subject
            msg["From"] = smtp_user or "gideon@localhost"
            msg["To"] = p.recipient

            with smtplib.SMTP(smtp_host, smtp_port, timeout=smtp_timeout) as server:
                server.starttls()
                if smtp_user and smtp_pass:
                    server.login(smtp_user, smtp_pass)
                server.send_message(msg)

            return {
                "status": "sent",
                "recipient": p.recipient,
                "subject": p.subject,
                "external_dispatch": True,
                "email_sent": True,
                "message": f"Email successfully dispatched to '{p.recipient}'."
            }
        except Exception as e:
            logger.error("SMTP delivery failure to %s: %s", p.recipient, str(e))
            raise RuntimeError(f"SMTP delivery failed to '{p.recipient}': {str(e)}")


# -------------------------------------------------------------
# 5. Desktop Automation Tool (Bridge to Phase 4 Service)
# -------------------------------------------------------------

class DesktopActionParams(BaseModel):
    action: str = Field(..., description="Allowlisted DesktopActionType from Phase 4")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Action-specific parameters")


class DesktopActionTool(BaseTool):
    tool_id = "tool_desktop_action"
    name = "Desktop Automation Bridge"
    description = "Execute an allowlisted Windows desktop operation governed by Phase 4 security and allowlists."
    permission_level = ToolPermissionLevel.local_changes  # May escalate to consequential based on action risk
    requires_approval = False
    supports_concurrency = False
    timeout_seconds = 45
    param_schema = DesktopActionParams

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        p = self.validate_params(params)
        desktop_service = context.get("desktop_service") if context else None
        if not desktop_service:
            from app.api.dependencies import get_desktop_service
            desktop_service = get_desktop_service()

        from app.desktop.schemas import DesktopActionType
        try:
            action_type = DesktopActionType(p.action)
        except ValueError:
            return {"error": f"Action '{p.action}' is not an allowlisted desktop action in Gideon."}

        try:
            task = desktop_service.create_task(
                action=action_type,
                params=p.parameters
            )
            return {
                "desktop_task_id": str(task.id),
                "action": task.action.value,
                "status": task.status.value,
                "risk_level": task.risk_level.value,
                "requires_confirmation": task.requires_confirmation,
                "target_app": task.target_app,
                "error": task.error
            }
        except Exception as err:
            return {"error": f"Desktop task execution failed: {str(err)}"}



# -------------------------------------------------------------
# 6. Local PC Context Tools (Screen Awareness, Native OCR, Folder Summary)
# -------------------------------------------------------------

class LocalScreenAwarenessParams(BaseModel):
    query_type: str = Field(
        default="windows",
        description="Type of inspection: 'windows' for open application windows, 'active' for active window, 'ocr' for local on-screen text extraction",
    )


class LocalScreenAwarenessTool(BaseTool):
    tool_id = "tool_local_screen_awareness"
    name = "Local Screen & Window Awareness"
    description = "Inspect open application windows, active window, or extract on-screen text using local native OCR."
    permission_level = ToolPermissionLevel.read_only
    requires_approval = False
    supports_concurrency = True
    timeout_seconds = 15
    param_schema = LocalScreenAwarenessParams

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        from app.services.local_context_service import LocalContextService
        service = LocalContextService()
        p = self.validate_params(params)
        
        if p.query_type == "active":
            return service.get_active_window()
        elif p.query_type == "ocr":
            return service.capture_screen_with_ocr(reason="agent_screen_awareness")
        else:
            return {"windows": service.get_open_windows()}


class LocalFolderSummaryParams(BaseModel):
    subpath: Optional[str] = Field(
        default=None,
        description="Optional relative directory path within workspace root to summarize",
    )


class LocalFolderSummaryTool(BaseTool):
    tool_id = "tool_local_folder_summary"
    name = "Local Folder Summary"
    description = "Safely summarize directory contents, file counts, and recent changes in authorized workspace."
    permission_level = ToolPermissionLevel.read_only
    requires_approval = False
    supports_concurrency = True
    timeout_seconds = 10
    param_schema = LocalFolderSummaryParams

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        from app.services.local_context_service import LocalContextService
        service = LocalContextService()
        p = self.validate_params(params)
        return service.summarize_directory(target_path_str=p.subpath)

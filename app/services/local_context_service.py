"""Local PC Context Service for secure on-device inspection and evidence retrieval."""
import os
import sys
import ctypes
from ctypes import wintypes
import tempfile
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.desktop.adapter import WindowsDesktopAdapter
from app.models.agent import AgentTask, AgentApproval, AgentExecutionLog
from app.schemas.agent import TaskStatusEnum, ApprovalDecisionEnum

logger = get_logger(__name__)

is_windows = sys.platform == "win32"
if is_windows:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
else:
    user32 = None
    kernel32 = None


# PowerShell WinRT OCR runner script template
WINRT_OCR_PS_SCRIPT = '''
param([string]$ImagePath)
Add-Type -AssemblyName System.Runtime.WindowsRuntime
[void][Windows.Media.Ocr.OcrEngine, Windows.Foundation.UniversalApiContract, ContentType = WindowsRuntime]
[void][Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation.UniversalApiContract, ContentType = WindowsRuntime]
[void][Windows.Storage.StorageFile, Windows.Foundation.UniversalApiContract, ContentType = WindowsRuntime]

$global:asTaskGeneric = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq "AsTask" -and 
    $_.IsGenericMethodDefinition -and 
    $_.GetGenericArguments().Length -eq 1 -and 
    $_.GetParameters()[0].ParameterType.Name -like "IAsyncOperation*"
} | Select-Object -First 1

function Await-Op($asyncOp, [Type]$targetType) {
    $m = $global:asTaskGeneric.MakeGenericMethod($targetType)
    $task = $m.Invoke($null, @($asyncOp))
    [void]$task.Wait(5000)
    return $task.Result
}

try {
    $fullPath = [System.IO.Path]::GetFullPath($ImagePath)
    $file = Await-Op ([Windows.Storage.StorageFile]::GetFileFromPathAsync($fullPath)) ([Windows.Storage.StorageFile])
    $stream = Await-Op ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream, Windows.Foundation.UniversalApiContract, ContentType = WindowsRuntime])
    $decoder = Await-Op ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $bitmap = Await-Op ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])

    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
    if ($null -eq $engine) {
        $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new("en-US"))
    }
    $ocrResult = Await-Op ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])

    Write-Output "RECOGNIZED_TEXT:$($ocrResult.Text)"
} catch {
    Write-Error $_.Exception.ToString()
}
'''


class LocalContextService:
    """
    Coordinates local PC context tools:
    - Running applications and visible window enumeration
    - Active window inspection
    - User-approved local screenshot & Windows native WinRT OCR
    - Safe authorized workspace directory scanning
    - Gideon's persisted tasks, pending approvals, and execution errors
    - Change diffing since yesterday
    """

    def __init__(self, desktop_adapter: Optional[WindowsDesktopAdapter] = None):
        self.desktop_adapter = desktop_adapter or WindowsDesktopAdapter()
        self._ocr_script_path: Optional[Path] = None

    def _ensure_ocr_script(self) -> Path:
        if self._ocr_script_path and self._ocr_script_path.exists():
            return self._ocr_script_path
        
        telemetry_dir = Path(tempfile.gettempdir()) / "gideon_telemetry"
        telemetry_dir.mkdir(parents=True, exist_ok=True)
        script_file = telemetry_dir / "native_ocr.ps1"
        with open(script_file, "w", encoding="utf-8") as f:
            f.write(WINRT_OCR_PS_SCRIPT)
        self._ocr_script_path = script_file
        return script_file

    def get_active_window(self) -> Dict[str, Any]:
        """Inspect the current foreground window."""
        info = self.desktop_adapter.inspect_active_window()
        return {
            "title": info.title,
            "process_name": info.process_name,
            "pid": info.pid,
            "is_elevated": info.is_elevated,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
        }

    def get_open_windows(self) -> List[Dict[str, Any]]:
        """
        Enumerate all open, visible top-level windows on the desktop.
        Filters out invisible helper processes and OS background windows.
        """
        if not is_windows or not user32:
            return [{"title": "Demo Workspace Window", "process_name": "explorer.exe", "pid": 1000, "is_active": True}]

        active_hwnd = user32.GetForegroundWindow()
        windows: List[Dict[str, Any]] = []

        # System window titles to ignore
        ignored_titles = {
            "", "Program Manager", "Default IME", "MSCTFIME UI",
            "Windows Shell Experience Host", "Task Switching",
        }

        def enum_windows_callback(hwnd, lParam):
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    title_buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, title_buf, length + 1)
                    title = title_buf.value.strip()

                    if title and title not in ignored_titles:
                        pid = wintypes.DWORD()
                        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                        proc_name = ""
                        h_proc = kernel32.OpenProcess(0x1000 | 0x0400, False, pid.value)
                        if h_proc:
                            name_buf = ctypes.create_unicode_buffer(1024)
                            size = wintypes.DWORD(1024)
                            if kernel32.QueryFullProcessImageNameW(h_proc, 0, name_buf, ctypes.byref(size)):
                                proc_name = os.path.basename(name_buf.value)
                            kernel32.CloseHandle(h_proc)

                        windows.append({
                            "title": title,
                            "process_name": proc_name or "unknown",
                            "pid": pid.value,
                            "is_active": (hwnd == active_hwnd),
                        })
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(WNDENUMPROC(enum_windows_callback), 0)

        # Sort so active window is first, followed by others
        windows.sort(key=lambda w: (not w["is_active"], w["title"].lower()))
        return windows

    def capture_screen_with_ocr(self, reason: str = "user_query") -> Dict[str, Any]:
        """
        Capture a local screenshot and extract text locally using Windows native WinRT OCR.
        Strictly local processing: zero cloud upload.
        """
        if not settings.screen_inspection_allowed:
            return {
                "success": False,
                "error": "Screen inspection is currently disabled in Gideon Settings.",
                "ocr_text": "",
            }

        logger.info("[SCREEN_INSPECTION_AUDIT] Screen inspection invoked: reason='%s'", reason)

        # 1. Capture local screenshot
        snap = self.desktop_adapter.capture_screenshot(local_only=True)
        img_path = snap.get("file_path")
        if not img_path or not os.path.exists(img_path):
            return {
                "success": False,
                "error": "Failed to capture desktop screenshot.",
                "ocr_text": "",
            }

        # 2. Run Windows Native WinRT OCR
        script_file = self._ensure_ocr_script()
        ocr_text = ""
        try:
            no_win = 0x08000000 if sys.platform == "win32" else 0
            res = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script_file), "-ImagePath", img_path],
                capture_output=True,
                text=True,
                timeout=12,
                creationflags=no_win,
            )
            stdout = res.stdout.strip()
            if "RECOGNIZED_TEXT:" in stdout:
                ocr_text = stdout.split("RECOGNIZED_TEXT:", 1)[1].strip()
            elif stdout:
                ocr_text = stdout
        except Exception as e:
            logger.warning("Local OCR extraction encountered an error: %s", str(e))
            ocr_text = f"(OCR processing error: {str(e)})"

        return {
            "success": True,
            "screenshot_path": img_path,
            "width": snap.get("width"),
            "height": snap.get("height"),
            "ocr_text": ocr_text,
            "word_count": len(ocr_text.split()) if ocr_text else 0,
            "captured_at": snap.get("captured_at"),
            "audit_logged": True,
        }

    def summarize_directory(self, target_path_str: Optional[str] = None) -> Dict[str, Any]:
        """
        Safely inspect and summarize an explicitly authorized directory (project workspace).
        Enforces security boundary: cannot escape workspace root.
        """
        if not settings.workspace_inspection_allowed:
            return {
                "success": False,
                "error": "Workspace directory inspection is disabled in Gideon Settings.",
            }

        workspace_root = Path(self.desktop_adapter.security_policy.workspace_root).resolve()
        
        if target_path_str:
            target_path = Path(target_path_str).resolve()
        else:
            target_path = workspace_root

        # Security check: must reside inside workspace_root
        try:
            target_path.relative_to(workspace_root)
        except ValueError:
            return {
                "success": False,
                "error": f"Access denied: Directory '{target_path}' is outside authorized workspace root '{workspace_root}'.",
            }

        if not target_path.exists() or not target_path.is_dir():
            return {
                "success": False,
                "error": f"Directory does not exist: {target_path}",
            }

        # Scan folder
        entries = []
        total_files = 0
        total_dirs = 0
        total_size = 0
        now = datetime.now(timezone.utc)
        recent_modifications = []

        try:
            for item in target_path.iterdir():
                if item.name.startswith((".", "__pycache__", "node_modules", ".venv")):
                    continue
                try:
                    stat = item.stat()
                    mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
                    is_recent = (now - mtime) < timedelta(hours=24)

                    if item.is_dir():
                        total_dirs += 1
                        entries.append({
                            "name": item.name,
                            "type": "directory",
                            "last_modified": mtime.isoformat(),
                        })
                    else:
                        total_files += 1
                        total_size += stat.st_size
                        entries.append({
                            "name": item.name,
                            "type": "file",
                            "size_bytes": stat.st_size,
                            "last_modified": mtime.isoformat(),
                        })

                    if is_recent:
                        recent_modifications.append({
                            "name": item.name,
                            "type": "dir" if item.is_dir() else "file",
                            "modified": mtime.strftime("%Y-%m-%d %H:%M:%S UTC"),
                        })
                except (OSError, PermissionError):
                    continue
        except Exception as e:
            return {
                "success": False,
                "error": f"Error scanning directory: {str(e)}",
            }

        return {
            "success": True,
            "path": str(target_path),
            "directory_name": target_path.name or str(target_path),
            "total_files": total_files,
            "total_directories": total_dirs,
            "total_size_bytes": total_size,
            "entries_preview": entries[:25],
            "recently_modified_24h": recent_modifications[:15],
        }

    def get_pending_tasks_and_approvals(self, db: Session) -> Dict[str, Any]:
        """
        Query actual persisted agent tasks, pending approvals, and recent failures.
        """
        active_statuses = [
            TaskStatusEnum.queued.value,
            TaskStatusEnum.planning.value,
            TaskStatusEnum.running.value,
            TaskStatusEnum.awaiting_approval.value,
        ]

        pending_tasks = db.query(AgentTask).filter(
            AgentTask.status.in_(active_statuses)
        ).order_by(AgentTask.created_at.desc()).all()

        pending_approvals = db.query(AgentApproval).filter(
            AgentApproval.decision == ApprovalDecisionEnum.pending.value
        ).order_by(AgentApproval.created_at.desc()).all()

        recent_failures = db.query(AgentTask).filter(
            AgentTask.status == TaskStatusEnum.failed.value
        ).order_by(AgentTask.completed_at.desc()).limit(5).all()

        completed_count = db.query(AgentTask).filter(
            AgentTask.status == TaskStatusEnum.completed.value
        ).count()

        return {
            "pending_tasks_count": len(pending_tasks),
            "pending_approvals_count": len(pending_approvals),
            "recent_failures_count": len(recent_failures),
            "completed_tasks_count": completed_count,
            "pending_tasks": [
                {
                    "task_id": str(t.id),
                    "title": t.title,
                    "status": t.status,
                    "target_agent": t.assigned_agent_id or "unassigned",
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                }
                for t in pending_tasks
            ],
            "pending_approvals": [
                {
                    "approval_id": str(a.id),
                    "task_id": str(a.task_id),
                    "action_type": a.action_type,
                    "description": a.description or a.action_type,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                }
                for a in pending_approvals
            ],
            "recent_failures": [
                {
                    "task_id": str(f.id),
                    "title": f.title,
                    "error": f.error_message,
                    "failed_at": f.completed_at.isoformat() if f.completed_at else None,
                }
                for f in recent_failures
            ],
        }

    def explain_recent_errors(self, db: Session, text_hint: Optional[str] = None) -> Dict[str, Any]:
        """
        Inspect the database and execution logs for recent errors, explaining causes honestly.
        """
        recent_failed_task = db.query(AgentTask).filter(
            AgentTask.status == TaskStatusEnum.failed.value
        ).order_by(AgentTask.completed_at.desc()).first()

        recent_error_log = db.query(AgentExecutionLog).filter(
            AgentExecutionLog.level.in_(["ERROR", "CRITICAL"])
        ).order_by(AgentExecutionLog.timestamp.desc()).first()

        if recent_failed_task and recent_failed_task.error_message:
            return {
                "source": "persisted_task_failure",
                "task_id": str(recent_failed_task.id),
                "task_title": recent_failed_task.title,
                "error_details": recent_failed_task.error_message,
                "explanation": (
                    f"Task '{recent_failed_task.title}' failed with error: "
                    f"'{recent_failed_task.error_message}'. "
                    "Review parameters or required prerequisites."
                ),
            }

        if recent_error_log:
            return {
                "source": "execution_log",
                "event": recent_error_log.event,
                "message": recent_error_log.message,
                "explanation": f"Recent system error logged during '{recent_error_log.event}': {recent_error_log.message}",
            }

        # Check screen OCR as fallback if user asked to read an error from screen
        screen_ocr = self.capture_screen_with_ocr(reason="error_reading")
        if screen_ocr.get("success") and screen_ocr.get("ocr_text"):
            text = screen_ocr["ocr_text"]
            lines = [line.strip() for line in text.split("\n") if any(kw in line.lower() for kw in ["error", "exception", "failed", "fail", "traceback", "cannot", "denied"])]
            if lines:
                return {
                    "source": "screen_ocr",
                    "detected_error_lines": lines[:5],
                    "explanation": f"Observed error on screen: {' '.join(lines[:3])}",
                }

        return {
            "source": "none",
            "message": "No recent task failures, error logs, or visible error dialogs found.",
            "explanation": "All monitored systems and tasks are currently operating without unhandled errors.",
        }

    def get_changes_since_yesterday(self, db: Session) -> Dict[str, Any]:
        """
        Summarize real activities, task completions, and workspace file changes over the last 24 hours.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

        # 1. Database tasks in last 24h
        completed_since_yesterday = db.query(AgentTask).filter(
            AgentTask.status == TaskStatusEnum.completed.value,
            AgentTask.completed_at >= cutoff
        ).all()

        failed_since_yesterday = db.query(AgentTask).filter(
            AgentTask.status == TaskStatusEnum.failed.value,
            AgentTask.completed_at >= cutoff
        ).all()

        new_tasks_since_yesterday = db.query(AgentTask).filter(
            AgentTask.created_at >= cutoff
        ).all()

        # 2. File changes in workspace in last 24h
        workspace_summary = self.summarize_directory()
        recent_files = workspace_summary.get("recently_modified_24h", [])

        return {
            "period": "Last 24 hours",
            "tasks_completed_count": len(completed_since_yesterday),
            "tasks_failed_count": len(failed_since_yesterday),
            "tasks_created_count": len(new_tasks_since_yesterday),
            "completed_tasks": [t.title for t in completed_since_yesterday],
            "failed_tasks": [t.title for t in failed_since_yesterday],
            "workspace_files_modified_count": len(recent_files),
            "workspace_files_modified": recent_files,
        }

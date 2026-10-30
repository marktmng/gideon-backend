"""Security policy, allowlists, and path verification for Windows Desktop Control."""
import os
import re
from pathlib import Path
from typing import Dict, Optional, Set, List, Tuple
from app.desktop.schemas import RiskLevel, DesktopActionType


# ============================================================================
# Trusted Applications Allowlist
# ============================================================================

# Trusted system executables mapped to standard Windows binary paths or commands
DEFAULT_APPLICATION_ALLOWLIST: Dict[str, Dict[str, str]] = {
    "notepad": {
        "binary": "notepad.exe",
        "name": "Notepad",
        "description": "Windows text editor",
    },
    "calculator": {
        "binary": "calc.exe",
        "name": "Calculator",
        "description": "Windows calculator utility",
    },
    "explorer": {
        "binary": "explorer.exe",
        "name": "File Explorer",
        "description": "Windows File Explorer",
    },
    "file_explorer": {
        "binary": "explorer.exe",
        "name": "File Explorer",
        "description": "Windows File Explorer",
    },
    "mspaint": {
        "binary": "mspaint.exe",
        "name": "Paint",
        "description": "Windows graphic image editor",
    },
    "browser": {
        "binary": "default_browser",
        "name": "Default Web Browser",
        "description": "User default web browser",
    },
    "edge": {
        "binary": "msedge.exe",
        "name": "Microsoft Edge",
        "description": "Microsoft Edge browser",
    },
    "chrome": {
        "binary": "chrome.exe",
        "name": "Google Chrome",
        "description": "Google Chrome browser",
    },
    "terminal": {
        "binary": "wt.exe",
        "name": "Windows Terminal",
        "description": "Windows Terminal environment",
    },
    "vscode": {
        "binary": "code.cmd",
        "name": "Visual Studio Code",
        "description": "Visual Studio Code editor",
    },
    "code": {
        "binary": "code.cmd",
        "name": "Visual Studio Code",
        "description": "Visual Studio Code editor",
    },
    "calc": {
        "binary": "calc.exe",
        "name": "Calculator",
        "description": "Windows calculator utility",
    },
    "paint": {
        "binary": "mspaint.exe",
        "name": "Paint",
        "description": "Windows graphic image editor",
    },
    "antigravity": {
        "binary": "antigravity.exe",
        "name": "Antigravity IDE",
        "description": "Antigravity Development Environment",
    },
    "google_chrome": {
        "binary": "chrome.exe",
        "name": "Google Chrome",
        "description": "Google Chrome browser",
    },
    "firefox": {
        "binary": "firefox.exe",
        "name": "Mozilla Firefox",
        "description": "Mozilla Firefox browser",
    },
    "brave": {
        "binary": "brave.exe",
        "name": "Brave Browser",
        "description": "Brave Web Browser",
    },
    "cmd": {
        "binary": "cmd.exe",
        "name": "Command Prompt",
        "description": "Windows Command Prompt",
    },
    "visual_studio_code": {
        "binary": "code.cmd",
        "name": "Visual Studio Code",
        "description": "Visual Studio Code editor",
    },
    "task_manager": {
        "binary": "taskmgr.exe",
        "name": "Task Manager",
        "description": "Windows Task Manager utility",
    },
    "taskmanager": {
        "binary": "taskmgr.exe",
        "name": "Task Manager",
        "description": "Windows Task Manager utility",
    },
    "taskmgr": {
        "binary": "taskmgr.exe",
        "name": "Task Manager",
        "description": "Windows Task Manager utility",
    },
    "control_panel": {
        "binary": "control.exe",
        "name": "Control Panel",
        "description": "Windows Control Panel",
    },
    "settings": {
        "binary": "ms-settings:",
        "name": "Settings",
        "description": "Windows System Settings",
    },
    "windows_settings": {
        "binary": "ms-settings:",
        "name": "Settings",
        "description": "Windows System Settings",
    },
    "camera": {
        "binary": "microsoft.windows.camera:",
        "name": "Camera",
        "description": "Windows Camera application",
    },
    "clock": {
        "binary": "ms-clock:",
        "name": "Clock & Alarms",
        "description": "Windows Clock application",
    },
    "alarms": {
        "binary": "ms-clock:",
        "name": "Clock & Alarms",
        "description": "Windows Clock application",
    },
    "photos": {
        "binary": "ms-photos:",
        "name": "Photos",
        "description": "Windows Photos application",
    },
    "snipping_tool": {
        "binary": "snippingtool.exe",
        "name": "Snipping Tool",
        "description": "Windows Snipping Tool screen capture",
    },
    "snip": {
        "binary": "snippingtool.exe",
        "name": "Snipping Tool",
        "description": "Windows Snipping Tool screen capture",
    },
    "spotify": {
        "binary": "spotify.exe",
        "name": "Spotify",
        "description": "Spotify Music Player",
    },
    "discord": {
        "binary": "discord.exe",
        "name": "Discord",
        "description": "Discord communication application",
    },
    "steam": {
        "binary": "steam.exe",
        "name": "Steam",
        "description": "Steam gaming platform",
    },
    "vlc": {
        "binary": "vlc.exe",
        "name": "VLC Media Player",
        "description": "VLC multimedia player",
    },
    "word": {
        "binary": "winword.exe",
        "name": "Microsoft Word",
        "description": "Microsoft Word document processor",
    },
    "ms_word": {
        "binary": "winword.exe",
        "name": "Microsoft Word",
        "description": "Microsoft Word document processor",
    },
    "excel": {
        "binary": "excel.exe",
        "name": "Microsoft Excel",
        "description": "Microsoft Excel spreadsheet processor",
    },
    "ms_excel": {
        "binary": "excel.exe",
        "name": "Microsoft Excel",
        "description": "Microsoft Excel spreadsheet processor",
    },
    "powerpoint": {
        "binary": "powerpnt.exe",
        "name": "Microsoft PowerPoint",
        "description": "Microsoft PowerPoint presentation tool",
    },
    "outlook": {
        "binary": "outlook.exe",
        "name": "Microsoft Outlook",
        "description": "Microsoft Outlook email client",
    },
    "onenote": {
        "binary": "onenote.exe",
        "name": "Microsoft OneNote",
        "description": "Microsoft OneNote notes notebook",
    },
    "teams": {
        "binary": "teams.exe",
        "name": "Microsoft Teams",
        "description": "Microsoft Teams communication",
    },
    "zoom": {
        "binary": "zoom.exe",
        "name": "Zoom",
        "description": "Zoom video conferencing application",
    },
    "slack": {
        "binary": "slack.exe",
        "name": "Slack",
        "description": "Slack collaboration messaging",
    },
    "obs": {
        "binary": "obs64.exe",
        "name": "OBS Studio",
        "description": "OBS Studio broadcast recording software",
    },
    "blender": {
        "binary": "blender.exe",
        "name": "Blender",
        "description": "Blender 3D computer graphics software",
    },
    "figma": {
        "binary": "figma.exe",
        "name": "Figma",
        "description": "Figma design and prototyping tool",
    },
    "notion": {
        "binary": "notion.exe",
        "name": "Notion",
        "description": "Notion workspace and notes application",
    },
    "telegram": {
        "binary": "telegram.exe",
        "name": "Telegram",
        "description": "Telegram messaging application",
    },
    "whatsapp": {
        "binary": "whatsapp.exe",
        "name": "WhatsApp",
        "description": "WhatsApp desktop messaging application",
    },
}

# ============================================================================
# Safe Keyboard Shortcuts Allowlist
# ============================================================================

ALLOWED_SHORTCUTS: Set[str] = {
    "ctrl+c", "ctrl+v", "ctrl+x", "ctrl+z", "ctrl+y",
    "ctrl+s", "ctrl+f", "ctrl+a", "ctrl+p", "ctrl+n", "ctrl+w",
    "ctrl+shift+p",
    "enter", "return", "escape", "esc", "tab", "backspace", "space",
    "delete", "f5", "up", "down", "left", "right",
    "home", "end", "pageup", "pagedown",
}

# ============================================================================
# Sensitive / Elevated Window Title Indicators
# ============================================================================

SENSITIVE_WINDOW_PATTERNS = [
    r"administrator",
    r"user account control",
    r"task manager",
    r"registry editor",
    r"group policy",
    r"credential manager",
    r"bitlocker",
    r"windows security",
    r"security prompt",
    r"powershell.*admin",
    r"cmd.*admin",
]

# Sensitive process executables that Gideon must NEVER inject keystrokes into
SENSITIVE_PROCESS_NAMES = {
    "taskmgr.exe",
    "regedit.exe",
    "mmc.exe",
    "consent.exe",  # UAC prompt
    "logonui.exe",
    "lsass.exe",
    "cmd.exe",      # Raw command shells restricted from autonomous keystroke injection
    "powershell.exe",
    "pwsh.exe",
}


class DesktopSecurityPolicy:
    """Enforces validation, allowlists, and security boundaries on all desktop operations."""

    def __init__(self, workspace_root: Optional[Path] = None):
        # Establish permitted directory roots
        user_home = Path.home().resolve()
        self.workspace_root = workspace_root.resolve() if workspace_root else Path(os.getcwd()).resolve()

        # Approved base directories where Gideon is permitted to open Explorer or view paths
        self.approved_directory_roots: List[Path] = [
            self.workspace_root,
            user_home / "Desktop",
            user_home / "Documents",
            user_home / "Downloads",
            user_home / "Pictures",
            user_home / "Videos",
            user_home / "Projects",
            user_home / "Mark",
            Path("C:/Mark").resolve() if Path("C:/Mark").exists() else None,
        ]
        # Filter out non-existent and duplicates
        self.approved_directory_roots = [
            p.resolve() for p in self.approved_directory_roots if p and p.exists()
        ]

    def validate_application_name(self, app_name: str) -> Tuple[bool, str, Optional[Dict[str, str]]]:
        """Verify requested application is in the trusted allowlist or a verified safe system application."""
        import shutil
        norm_name = app_name.strip().lower()
        # Strip .exe if provided
        if norm_name.endswith(".exe"):
            norm_name = norm_name[:-4]

        if norm_name in DEFAULT_APPLICATION_ALLOWLIST:
            return True, "Application is allowlisted.", DEFAULT_APPLICATION_ALLOWLIST[norm_name]

        alt_name = norm_name.replace(" ", "_")
        if alt_name in DEFAULT_APPLICATION_ALLOWLIST:
            return True, "Application is allowlisted.", DEFAULT_APPLICATION_ALLOWLIST[alt_name]

        alt_no_space = norm_name.replace(" ", "")
        if alt_no_space in DEFAULT_APPLICATION_ALLOWLIST:
            return True, "Application is allowlisted.", DEFAULT_APPLICATION_ALLOWLIST[alt_no_space]

        # Check dynamic Windows Start Menu, Registry, and system application discovery
        try:
            from app.desktop.app_discovery import app_discovery
            discovered = app_discovery.resolve_application(norm_name)
            if discovered:
                return True, "Application verified on system.", {
                    "binary": discovered["target"],
                    "name": discovered["name"],
                    "description": f"Discovered Windows application: {discovered['name']}",
                }
        except Exception:
            pass

        # Check if requested application binary exists safely on the system
        dangerous_commands = {
            "format", "del", "erase", "rmdir", "rd", "regedit", "reg", "shutdown",
            "diskpart", "bcdedit", "vssadmin", "takeown", "icacls", "cipher",
            "powershell", "powershell_malicious", "format_c"
        }
        if norm_name not in dangerous_commands and not any(d in norm_name for d in ["malicious", "format", "shutdown", "rmdir"]):
            resolved = shutil.which(norm_name) or shutil.which(f"{norm_name}.exe") or shutil.which(f"{alt_name}.exe")
            if resolved:
                return True, "Application verified on system.", {
                    "binary": Path(resolved).name,
                    "name": app_name.strip().title(),
                    "description": f"Verified Windows executable: {resolved}",
                }

        return False, f"Application '{app_name}' is not in the trusted allowlist. Supported applications: {', '.join(sorted(DEFAULT_APPLICATION_ALLOWLIST.keys()))}", None

    def validate_url(self, url: str) -> Tuple[bool, str]:
        """Ensure URL scheme is strictly http or https with no command injection characters."""
        trimmed = url.strip()
        lower = trimmed.lower()
        if not (lower.startswith("http://") or lower.startswith("https://")):
            return False, f"Disallowed URL scheme in '{url}'. Only 'http://' and 'https://' destinations are permitted."

        # Reject dangerous shell or control characters
        disallowed = ["\n", "\r", "\t", '"', "'", ";", "|", "&", "<", ">", "`", "$"]
        if any(char in trimmed for char in disallowed):
            return False, "URL contains disallowed control or shell characters."

        return True, "URL is valid."

    def validate_directory_path(self, path_str: str) -> Tuple[bool, str, Optional[Path]]:
        """Validate and canonicalize directory path, ensuring boundary confinement and non-traversal."""
        trimmed = path_str.strip()
        if ".." in trimmed:
            return False, "Path traversal sequence ('..') is prohibited.", None

        try:
            target_path = Path(trimmed).resolve()
        except Exception as e:
            return False, f"Invalid filesystem path syntax: {e}", None

        if not target_path.exists():
            return False, f"Target directory does not exist: {target_path}", None

        if not target_path.is_dir():
            return False, f"Target path is not a directory: {target_path}", None

        # Check if target is inside an approved root
        is_permitted = False
        for root in self.approved_directory_roots:
            try:
                if target_path == root or target_path.is_relative_to(root):
                    is_permitted = True
                    break
            except (ValueError, AttributeError):
                pass

        # Disallow root drive directly
        try:
            if target_path == Path("C:/").resolve():
                return False, f"Direct access to system boundary '{target_path}' is restricted.", None
        except Exception:
            pass

        # Disallow Windows system directories and any subdirectories
        system_root = Path(os.environ.get("SystemRoot", "C:/Windows"))
        prog_files = Path(os.environ.get("ProgramFiles", "C:/Program Files"))
        prog_files_x86 = Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)"))
        prog_data = Path(os.environ.get("ProgramData", "C:/ProgramData"))
        forbidden_system_dirs = [system_root, system_root / "System32", prog_files, prog_files_x86, prog_data]
        for f_dir in forbidden_system_dirs:
            try:
                f_res = f_dir.resolve()
                if target_path == f_res or target_path.is_relative_to(f_res):
                    return False, f"Direct access to system boundary '{target_path}' is restricted.", None
            except Exception:
                pass

        if not is_permitted:
            return False, f"Access denied: '{target_path}' is outside configured user directory boundaries.", None

        return True, "Directory path is verified and approved.", target_path

    def validate_application_arguments(self, app_name: str, args: Optional[List[str]]) -> Tuple[bool, str]:
        """Verify command arguments are strictly non-malicious and do not attempt shell escapes."""
        if not args:
            return True, "No arguments provided."

        for arg in args:
            trimmed = str(arg).strip()
            # Reject dangerous characters for command injection
            disallowed = [";", "|", "&", ">", "<", "`", "$", "\n", "\r"]
            if any(c in trimmed for c in disallowed):
                return False, f"Disallowed control characters in argument: '{arg}'"

            # If argument specifies a path, verify it does not traverse into system directories
            if "/" in trimmed or "\\" in trimmed or ".." in trimmed:
                if ".." in trimmed:
                    return False, "Path traversal sequence ('..') in arguments is prohibited."
                # If it's a path, check it against system roots
                try:
                    p = Path(trimmed).resolve()
                    if p.exists():
                        system_root = Path(os.environ.get("SystemRoot", "C:/Windows")).resolve()
                        if p == system_root or p.is_relative_to(system_root):
                            return False, f"Argument references restricted system directory: '{trimmed}'"
                except Exception:
                    pass

        return True, "Arguments are verified."

    def validate_shortcut(self, shortcut_str: str) -> Tuple[bool, str]:
        """Verify requested shortcut is within the safe keyboard shortcut allowlist."""
        normalized = shortcut_str.strip().lower().replace(" ", "")
        if normalized in ALLOWED_SHORTCUTS:
            return True, "Shortcut is permitted."

        return False, f"Shortcut '{shortcut_str}' is not allowlisted. Permitted shortcuts include standard navigation and editing combinations."

    def check_target_window_safety(self, window_title: str, process_name: Optional[str] = None, is_elevated: bool = False) -> Tuple[bool, str]:
        """Verify target window is not an elevated administrative utility or sensitive security credential dialog."""
        if is_elevated:
            return False, f"Operation halted: Target window '{window_title}' is running with elevated administrative privileges."

        title_lower = window_title.lower()

        for pattern in SENSITIVE_WINDOW_PATTERNS:
            if re.search(pattern, title_lower):
                return False, f"Operation halted: Target window '{window_title}' is classified as a sensitive administrative context."

        if process_name:
            proc_lower = process_name.lower().strip()
            if proc_lower in SENSITIVE_PROCESS_NAMES:
                return False, f"Operation halted: Target process '{process_name}' is restricted from autonomous input injection."

        return True, "Target window is approved for interaction."

    def evaluate_risk(self, action: DesktopActionType, params: Dict) -> Tuple[RiskLevel, bool]:
        """Determine risk level and confirmation requirement for an action."""
        # Low risk actions:
        if action in (
            DesktopActionType.open_application,
            DesktopActionType.open_url,
            DesktopActionType.open_directory,
            DesktopActionType.open_file_explorer,
            DesktopActionType.inspect_active_window,
            DesktopActionType.capture_screenshot,
            DesktopActionType.cancel_task,
        ):
            # Low risk can execute directly without modal confirmation if allowed
            return RiskLevel.low, False

        # Medium risk actions:
        if action in (
            DesktopActionType.type_text,
            DesktopActionType.press_shortcut,
            DesktopActionType.click_accessible_element,
            DesktopActionType.activate_application,
        ):
            # Requires explicit confirmation by default
            return RiskLevel.medium, True

        return RiskLevel.high, True

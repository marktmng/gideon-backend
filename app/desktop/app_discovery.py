"""
Dynamic Windows Application Discovery, Resolution, and Lifecycle Management.

Discovers and launches applications dynamically across Windows systems via:
- User & System Start Menu shortcuts (.lnk files)
- Windows Registry App Paths (HKLM & HKCU)
- Windows AppUserModelId / protocol handlers
- Standard Windows executable directories
- Natural semantic category mapping (e.g. "video editor", "photo editor", "code editor")
"""
import os
import re
import sys
import time
import ctypes
from ctypes import wintypes
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple

is_windows = sys.platform == "win32"
if is_windows:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
else:
    user32 = None
    kernel32 = None

# Dangerous commands that must never be launched or executed
BLOCKED_DANGEROUS_BINARIES = {
    "format", "format.com", "del", "erase", "rmdir", "rd",
    "regedit", "regedit.exe", "reg.exe", "reg", "shutdown", "shutdown.exe",
    "diskpart", "diskpart.exe", "bcdedit", "bcdedit.exe", "vssadmin", "vssadmin.exe",
    "takeown", "icacls", "cipher", "powershell_malicious", "format_c"
}

# Semantic Category Mappings for natural language queries like "open my video editor"
CATEGORY_KEYWORDS = {
    "video_editor": [
        "video editor", "video editing", "editing video", "edit video",
        "movie editor", "video cut", "clipchamp"
    ],
    "image_editor": [
        "image editor", "editing images", "photo editor", "edit photo",
        "picture editor", "draw", "graphic editor", "graphics"
    ],
    "code_editor": [
        "code editor", "text editor", "programming", "ide",
        "development tool", "source editor"
    ],
    "music_player": [
        "music player", "music", "songs", "listen to music",
        "audio player", "playlist"
    ],
    "browser": [
        "web browser", "internet browser", "browser", "internet",
        "surf web", "browse"
    ],
    "messaging": [
        "chat app", "messaging app", "communication", "messenger"
    ]
}

CATEGORY_PREFERRED_APPS = {
    "video_editor": ["davinci resolve", "clipchamp", "premiere", "capcut", "shotcut", "vegas", "davinci", "movie maker"],
    "image_editor": ["photoshop", "illustrator", "lightroom", "gimp", "paint.net", "mspaint", "paint", "canva", "figma"],
    "code_editor": ["vscode", "code", "visual studio", "pycharm", "intellij", "sublime", "notepad++"],
    "music_player": ["spotify", "itunes", "apple music", "vlc", "groove", "media player"],
    "browser": ["chrome", "edge", "firefox", "brave", "opera"],
    "messaging": ["discord", "slack", "teams", "telegram", "whatsapp"]
}

# Substrings in shortcut names that usually represent secondary tools rather than main apps
SECONDARY_TOOL_FILTER = ["control panel", "speed test", "proxy generator", "utility", "installer", "uninstall", "setup", "help", "website", "documentation"]


class WindowsAppDiscovery:
    """Discovers and resolves applications dynamically on Windows."""

    def __init__(self):
        self._cached_apps: Optional[Dict[str, Dict[str, Any]]] = None
        self._last_scan_time = 0.0
        self._cache_ttl = 60.0  # re-scan every 60s if needed

    def _get_start_menu_dirs(self) -> List[Path]:
        dirs = []
        appdata = os.environ.get("APPDATA")
        if appdata:
            dirs.append(Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
        progdata = os.environ.get("ProgramData", "C:\\ProgramData")
        if progdata:
            dirs.append(Path(progdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
        return [d for d in dirs if d.exists()]

    def scan_all_applications(self, force: bool = False) -> Dict[str, Dict[str, Any]]:
        """Scan and index all discoverable applications across the system."""
        now = time.time()
        if not force and self._cached_apps and (now - self._last_scan_time < self._cache_ttl):
            return self._cached_apps

        discovered: Dict[str, Dict[str, Any]] = {}

        # 1. Scan Start Menu Shortcuts
        for s_dir in self._get_start_menu_dirs():
            try:
                for root, _, files in os.walk(s_dir):
                    for f in files:
                        if f.lower().endswith(".lnk"):
                            shortcut_name = f[:-4].strip()
                            clean_key = re.sub(r"[^a-z0-9]", "", shortcut_name.lower())
                            if clean_key and clean_key not in discovered:
                                full_path = os.path.join(root, f)
                                discovered[clean_key] = {
                                    "name": shortcut_name,
                                    "target": full_path,
                                    "type": "shortcut",
                                    "extension": ".lnk",
                                }
            except Exception:
                pass

        # 2. Scan Registry App Paths
        if is_windows:
            import winreg
            for root_key in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
                try:
                    with winreg.OpenKey(root_key, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths") as key:
                        count = winreg.QueryInfoKey(key)[0]
                        for i in range(count):
                            sub = winreg.EnumKey(key, i)
                            clean_key = re.sub(r"[^a-z0-9]", "", sub.lower().replace(".exe", ""))
                            if clean_key and clean_key not in discovered:
                                try:
                                    with winreg.OpenKey(key, sub) as subkey:
                                        val, _ = winreg.QueryValueEx(subkey, "")
                                        if val and os.path.exists(val):
                                            discovered[clean_key] = {
                                                "name": sub[:-4] if sub.lower().endswith(".exe") else sub,
                                                "target": val,
                                                "type": "registry",
                                                "extension": ".exe",
                                            }
                                except Exception:
                                    pass
                except Exception:
                    pass

        # 3. Known System Apps & Protocol Handlers
        system_defaults = {
            "calculator": {"name": "Calculator", "target": "calc.exe", "type": "system", "extension": ".exe"},
            "calc": {"name": "Calculator", "target": "calc.exe", "type": "system", "extension": ".exe"},
            "notepad": {"name": "Notepad", "target": "notepad.exe", "type": "system", "extension": ".exe"},
            "paint": {"name": "Paint", "target": "mspaint.exe", "type": "system", "extension": ".exe"},
            "mspaint": {"name": "Paint", "target": "mspaint.exe", "type": "system", "extension": ".exe"},
            "explorer": {"name": "File Explorer", "target": "explorer.exe", "type": "system", "extension": ".exe"},
            "fileexplorer": {"name": "File Explorer", "target": "explorer.exe", "type": "system", "extension": ".exe"},
            "files": {"name": "File Explorer", "target": "explorer.exe", "type": "system", "extension": ".exe"},
            "taskmanager": {"name": "Task Manager", "target": "taskmgr.exe", "type": "system", "extension": ".exe"},
            "taskmgr": {"name": "Task Manager", "target": "taskmgr.exe", "type": "system", "extension": ".exe"},
            "settings": {"name": "Settings", "target": "ms-settings:", "type": "protocol", "extension": ""},
            "windowssettings": {"name": "Settings", "target": "ms-settings:", "type": "protocol", "extension": ""},
            "camera": {"name": "Camera", "target": "microsoft.windows.camera:", "type": "protocol", "extension": ""},
            "clock": {"name": "Clock", "target": "ms-clock:", "type": "protocol", "extension": ""},
            "alarms": {"name": "Clock & Alarms", "target": "ms-clock:", "type": "protocol", "extension": ""},
            "photos": {"name": "Photos", "target": "ms-photos:", "type": "protocol", "extension": ""},
            "terminal": {"name": "Windows Terminal", "target": "wt.exe", "type": "system", "extension": ".exe"},
            "cmd": {"name": "Command Prompt", "target": "cmd.exe", "type": "system", "extension": ".exe"},
            "controlpanel": {"name": "Control Panel", "target": "control.exe", "type": "system", "extension": ".exe"},
            "snippingtool": {"name": "Snipping Tool", "target": "snippingtool.exe", "type": "system", "extension": ".exe"},
            "snip": {"name": "Snipping Tool", "target": "snippingtool.exe", "type": "system", "extension": ".exe"},
        }
        for k, v in system_defaults.items():
            if k not in discovered:
                discovered[k] = v

        self._cached_apps = discovered
        self._last_scan_time = now
        return discovered

    def resolve_application(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Resolve a user query to an application.
        Handles direct names, category phrases ("video editor"), and fuzzy matching.
        """
        raw = query.strip().lower().replace("_", " ")
        if not raw:
            return None

        # Check dangerous command blacklists
        for d in BLOCKED_DANGEROUS_BINARIES:
            if raw == d or d in raw.split():
                return None

        apps = self.scan_all_applications()

        # Step 1: Check category matching (e.g. "open my video editor" -> DaVinci Resolve / Premiere)
        is_category_query = False
        for cat, phrases in CATEGORY_KEYWORDS.items():
            if any(p in raw for p in phrases):
                is_category_query = True
                preferred = CATEGORY_PREFERRED_APPS.get(cat, [])
                for pref in preferred:
                    pref_clean = re.sub(r"[^a-z0-9]", "", pref.lower())
                    for k, app_data in apps.items():
                        name_lower = app_data["name"].lower()
                        if pref_clean in k or pref in name_lower:
                            # Skip secondary utilities if looking for a category application
                            if any(tool in name_lower for tool in SECONDARY_TOOL_FILTER):
                                continue
                            return app_data

        clean_q = re.sub(r"[^a-z0-9]", "", raw)

        # Distinguish "visual studio" vs "visual studio code"
        if "code" in raw or "vscode" in clean_q or "vs code" in raw:
            for k in ["visualstudiocode", "vscode", "code"]:
                if k in apps:
                    return apps[k]
        elif "visual studio" in raw or "visualstudio" in clean_q:
            # Prioritize primary Visual Studio (e.g. Visual Studio 2022)
            for target_k in ["visualstudio2022", "visualstudio", "visualstudio2019", "devenv"]:
                if target_k in apps:
                    return apps[target_k]
            for k, app_data in apps.items():
                name_l = app_data["name"].lower()
                if "visual studio" in name_l and "code" not in name_l and "blend" not in name_l and "installer" not in name_l:
                    return app_data

        # If it was a category query and no category app matched, do not fall through to generic text
        if is_category_query:
            return None

        # Step 2: Exact key match
        if clean_q in apps:
            return apps[clean_q]

        # Step 3: Exact name match
        for k, app_data in apps.items():
            name_l = app_data["name"].lower()
            if raw == name_l or clean_q == k:
                return app_data

        # Step 4: Word-boundary search (e.g. "photoshop" in "adobe photoshop 2024")
        for k, app_data in apps.items():
            name_l = app_data["name"].lower()
            # Ensure whole token match in name
            if re.search(r"\b" + re.escape(raw) + r"\b", name_l):
                return app_data
            if raw in name_l:
                return app_data

        # Step 5: Substring in key where clean_q is at least 4 characters and clean_q in k
        # (e.g. "spotify" in "spotifyfree")
        for k, app_data in apps.items():
            if len(clean_q) >= 4 and clean_q in k:
                return app_data

        # Step 6: System PATH fallback via shutil.which
        import shutil
        found_bin = shutil.which(raw) or shutil.which(f"{raw}.exe")
        if found_bin and os.path.exists(found_bin):
            return {
                "name": Path(found_bin).stem.title(),
                "target": found_bin,
                "type": "executable",
                "extension": Path(found_bin).suffix,
            }

        return None

    def launch(self, app_info: Dict[str, Any]) -> Tuple[bool, str]:
        """Launch the resolved application safely."""
        target = app_info.get("target")
        name = app_info.get("name", "Application")
        if not target:
            return False, f"Target for {name} is unspecified."

        if not is_windows:
            return True, f"Simulated launch for {name} on non-Windows environment."

        try:
            # Protocol URI (e.g. ms-settings:) or .lnk shortcut
            if target.startswith("ms-") or target.startswith("microsoft.") or target.lower().endswith(".lnk"):
                os.startfile(target)
                return True, f"{name} is opening."

            # Executable file
            if target.lower().endswith((".exe", ".cmd", ".bat")):
                import subprocess
                no_win = 0x08000000 if target.lower().endswith((".cmd", ".bat")) else 0
                subprocess.Popen([target], shell=False, creationflags=no_win)
                return True, f"{name} is opening."

            os.startfile(target)
            return True, f"{name} is opening."
        except Exception as exc:
            return False, f"Failed to start {name}: {str(exc)}"

    def close(self, query: str) -> Tuple[bool, str]:
        """Gracefully close the specified application window or process."""
        if not is_windows or not user32:
            return True, f"Simulated closing of '{query}' on non-Windows environment."

        clean_q = query.strip().lower()
        closed_count = 0
        matched_title = ""

        WM_CLOSE = 0x0010

        def enum_close_callback(hwnd, lParam):
            nonlocal closed_count, matched_title
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    title_buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, title_buf, length + 1)
                    title = title_buf.value

                    # Get process name
                    pid = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    proc_name = ""
                    h_proc = kernel32.OpenProcess(0x1000 | 0x0400, False, pid.value)
                    if h_proc:
                        name_buf = ctypes.create_unicode_buffer(1024)
                        size = wintypes.DWORD(1024)
                        if kernel32.QueryFullProcessImageNameW(h_proc, 0, name_buf, ctypes.byref(size)):
                            proc_name = os.path.basename(name_buf.value).lower()
                        kernel32.CloseHandle(h_proc)

                    # Match title or process name
                    if clean_q in title.lower() or (proc_name and clean_q in proc_name):
                        user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
                        closed_count += 1
                        matched_title = title
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(WNDENUMPROC(enum_close_callback), 0)

        if closed_count > 0:
            return True, f"{query.title()} is closed. What would you like me to do next?"
        return False, f"No running window matching '{query}' was found to close."

    def switch_to(self, query: str) -> Tuple[bool, str]:
        """Bring the specified application window to the foreground."""
        if not is_windows or not user32:
            return True, f"Switched to '{query}'."

        clean_q = query.strip().lower()
        matched_hwnd = None
        matched_title = ""

        def enum_switch_callback(hwnd, lParam):
            nonlocal matched_hwnd, matched_title
            if user32.IsWindowVisible(hwnd) and not user32.GetParent(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    title_buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, title_buf, length + 1)
                    title = title_buf.value

                    # Get process name
                    pid = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    proc_name = ""
                    h_proc = kernel32.OpenProcess(0x1000 | 0x0400, False, pid.value)
                    if h_proc:
                        name_buf = ctypes.create_unicode_buffer(1024)
                        size = wintypes.DWORD(1024)
                        if kernel32.QueryFullProcessImageNameW(h_proc, 0, name_buf, ctypes.byref(size)):
                            proc_name = os.path.basename(name_buf.value).lower()
                        kernel32.CloseHandle(h_proc)

                    if clean_q in title.lower() or (proc_name and clean_q in proc_name):
                        matched_hwnd = hwnd
                        matched_title = title
                        return False  # Stop enumeration
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(WNDENUMPROC(enum_switch_callback), 0)

        if matched_hwnd:
            SW_RESTORE = 9
            if user32.IsIconic(matched_hwnd):
                user32.ShowWindow(matched_hwnd, SW_RESTORE)
            user32.SetForegroundWindow(matched_hwnd)
            return True, f"Switched to {query.title()}. What would you like me to do next?"

        return False, f"Could not find an active window for '{query}' to switch to."


# Global singleton instance
app_discovery = WindowsAppDiscovery()

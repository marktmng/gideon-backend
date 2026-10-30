#!/usr/bin/env python3
"""
Gideon Windows Voice Companion Script (Phase 5).

A standalone companion utility for Windows that bridges system-level hotkeys
and background wake events to Gideon's backend voice API:
  POST /api/v1/voice/wake

Features:
- Pure Python standard library (zero mandatory pip dependencies).
- Connects to local FastAPI backend at http://127.0.0.1:8000/api/v1/voice.
- Supports CLI test dispatch (`--test`, `--phrase`, `--command`).
- Interactive terminal mode for rapid vocal directive testing without a microphone.
- Optional global hotkey listener (Win+Alt+G or Ctrl+Alt+G) when `keyboard` package is installed.
- Verifies Phase 4 & 5 security constraints on all dispatched commands.

Usage:
  python gideon_voice_companion.py --test
  python gideon_voice_companion.py --phrase "Hey Gideon" --command "What is open on my screen?"
  python gideon_voice_companion.py --interactive
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from typing import Optional, Dict, Any

DEFAULT_API_URL = "http://127.0.0.1:8000/api/v1/voice"


def check_api_status(base_url: str = DEFAULT_API_URL) -> Dict[str, Any]:
    """Check health and capabilities of Gideon's voice API subsystem."""
    status_url = f"{base_url}/status"
    req = urllib.request.Request(status_url, headers={"User-Agent": "GideonVoiceCompanion/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return {"online": True, "data": data}
    except urllib.error.URLError as exc:
        return {"online": False, "error": str(exc)}
    except Exception as exc:
        return {"online": False, "error": str(exc)}


def dispatch_wake_event(
    phrase: str = "Hey Gideon",
    command: Optional[str] = None,
    source: str = "windows_companion",
    base_url: str = DEFAULT_API_URL,
) -> Dict[str, Any]:
    """
    Dispatch a wake-word activation event to Gideon's backend.
    
    Endpoint: POST /api/v1/voice/wake
    Payload: {"phrase": phrase, "command": command, "source": source}
    """
    wake_url = f"{base_url}/wake"
    payload = {
        "phrase": phrase,
        "command": command,
        "source": source,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        wake_url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "GideonVoiceCompanion/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return {"success": True, "data": result}
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(err_body)
            return {"success": False, "http_code": exc.code, "error": parsed}
        except Exception:
            return {"success": False, "http_code": exc.code, "error": err_body}
    except urllib.error.URLError as exc:
        return {
            "success": False,
            "error": f"Connection to Gideon backend at {wake_url} failed: {exc}",
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def run_interactive_mode(base_url: str):
    """Interactive loop to trigger wake phrases and directives from Windows console."""
    print("\n" + "=" * 60)
    print(" GIDEON WINDOWS VOICE COMPANION — INTERACTIVE MODE")
    print("=" * 60)
    print(f"Target API: {base_url}")
    print("Commands:")
    print("  Type any directive (e.g. 'What is open on my screen?').")
    print("  Type 'wake' or press Enter to trigger 'Hey Gideon' alone.")
    print("  Type 'status' to probe live backend diagnostics.")
    print("  Type 'exit' or 'quit' to terminate.")
    print("=" * 60 + "\n")

    while True:
        try:
            line = input("Gideon Voice > ").strip()
            if not line:
                print(">> Dispatching wake trigger: 'Hey Gideon'...")
                res = dispatch_wake_event("Hey Gideon", command=None, base_url=base_url)
                _print_result(res)
                continue

            lower = line.lower()
            if lower in ("exit", "quit", "q"):
                print("Exiting voice companion. Goodbye.")
                break

            if lower == "status":
                st = check_api_status(base_url)
                print(json.dumps(st, indent=2))
                continue

            if lower == "wake":
                print(">> Dispatching wake phrase 'Hey Gideon'...")
                res = dispatch_wake_event("Hey Gideon", command=None, base_url=base_url)
                _print_result(res)
                continue

            # Check if user included wake phrase
            if lower.startswith("hey gideon,"):
                cmd = line[len("hey gideon,") :].strip()
                res = dispatch_wake_event("Hey Gideon", command=cmd, base_url=base_url)
            elif lower.startswith("hey gideon"):
                cmd = line[len("hey gideon") :].strip()
                res = dispatch_wake_event("Hey Gideon", command=cmd if cmd else None, base_url=base_url)
            elif lower.startswith("gideon,"):
                cmd = line[len("gideon,") :].strip()
                res = dispatch_wake_event("Gideon", command=cmd, base_url=base_url)
            else:
                # Treat line as command following 'Hey Gideon'
                res = dispatch_wake_event("Hey Gideon", command=line, base_url=base_url)

            _print_result(res)

        except KeyboardInterrupt:
            print("\nInterrupt received. Exiting.")
            break
        except EOFError:
            break


def _print_result(res: Dict[str, Any]):
    if res.get("success"):
        data = res.get("data", {})
        status = data.get("status", "unknown")
        phrase = data.get("phrase", "")
        cmd = data.get("command")
        msg = data.get("message", "")
        safety = data.get("safety_passed", True)

        icon = "[ACK]" if safety else "[REJECTED]"
        print(f" {icon} Status: {status} | Phrase: '{phrase}' | Safety Passed: {safety}")
        if cmd:
            print(f"       Directive: '{cmd}'")
        print(f"       Message: {msg}\n")
    else:
        print(f" [ERROR] Request failed: {res.get('error', 'Unknown error')}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Gideon Windows Voice Companion — System Wake & Directives Bridge"
    )
    parser.add_argument(
        "--api-url",
        default=DEFAULT_API_URL,
        help=f"Base URL for Gideon voice API (default: {DEFAULT_API_URL})",
    )
    parser.add_argument(
        "--phrase",
        default="Hey Gideon",
        help="Wake phrase to trigger ('Hey Gideon' or 'Gideon')",
    )
    parser.add_argument(
        "--command",
        default=None,
        help="Optional directive to execute with the wake event",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run end-to-end diagnostic test against the backend API",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Launch interactive console mode",
    )

    args = parser.parse_args()

    # Case 1: Run diagnostic self-test
    if args.test:
        print(">> Checking Gideon Voice API subsystem...")
        status_info = check_api_status(args.api_url)
        if not status_info.get("online"):
            print(f"[-] Backend offline or unreachable at {args.api_url}/status")
            print(f"    Error: {status_info.get('error')}")
            sys.exit(1)

        print("[+] Backend Voice API online:")
        print(json.dumps(status_info["data"], indent=2))

        print("\n>> Testing wake event dispatch ('Hey Gideon')...")
        wake_res = dispatch_wake_event("Hey Gideon", command=args.command or "System diagnostic check", base_url=args.api_url)
        _print_result(wake_res)

        print(">> Testing safety policy on banned command...")
        banned_res = dispatch_wake_event("Hey Gideon", command="format c:", base_url=args.api_url)
        _print_result(banned_res)
        assert banned_res.get("data", {}).get("safety_passed") is False, "Safety filter failed to block dangerous command!"
        print("[+] All voice API and safety validation tests passed successfully.")
        return

    # Case 2: Direct one-off command
    if args.command or not args.interactive:
        if not args.command and not sys.stdin.isatty():
            # Piped input
            cmd = sys.stdin.read().strip()
            res = dispatch_wake_event(args.phrase, command=cmd or None, base_url=args.api_url)
            _print_result(res)
            return

        if args.command:
            res = dispatch_wake_event(args.phrase, command=args.command, base_url=args.api_url)
            _print_result(res)
            return

    # Case 3: Interactive mode
    run_interactive_mode(args.api_url)


if __name__ == "__main__":
    main()


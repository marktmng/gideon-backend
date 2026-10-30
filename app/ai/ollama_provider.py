"""Local AI provider integrating with Ollama runtime (http://127.0.0.1:11434)."""
import json
from typing import List, Dict, Any, Optional, AsyncIterator
import httpx

from app.ai.base import BaseAIProvider
from app.core.exceptions import AIProviderError, AIConfigurationError
from app.core.logging import get_logger

logger = get_logger(__name__)


class OllamaAIProvider(BaseAIProvider):
    """
    Local AI provider connecting to an on-device Ollama instance.
    Runs completely offline and locally without cloud API keys or external telemetry.
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "llama3.2",
        timeout_seconds: float = 60.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model or "llama3.2"
        self.timeout_seconds = timeout_seconds

    @property
    def name(self) -> str:
        return "ollama"

    @property
    def is_demo(self) -> bool:
        return False

    @property
    def supports_streaming(self) -> bool:
        return True

    def _try_auto_start_ollama(self):
        """Attempt to launch the local Ollama daemon if installed on Windows PC."""
        import os
        import shutil
        import subprocess
        from pathlib import Path

        candidates = [
            shutil.which("ollama"),
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe"),
            r"C:\Users\admin\AppData\Local\Programs\Ollama\ollama.exe",
            r"C:\Program Files\Ollama\ollama.exe",
        ]
        exe_path = next((c for c in candidates if c and Path(c).is_file()), None)
        if not exe_path:
            return

        try:
            CREATE_NO_WINDOW = 0x08000000
            CREATE_NEW_PROCESS_GROUP = 0x00000200
            subprocess.Popen(
                [exe_path, "serve"],
                creationflags=CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP,
                close_fds=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            logger.info("Auto-launched local Ollama background service (hidden): %s serve", exe_path)
        except Exception as e:
            logger.debug("Could not auto-launch Ollama executable: %s", str(e))

    def check_connection(self) -> Dict[str, Any]:
        """
        Check if Ollama service is reachable and list locally available models.
        If not initially reachable, attempts to auto-launch local Ollama on Windows PC.
        """
        url = f"{self.base_url}/api/tags"

        def _probe():
            try:
                with httpx.Client(timeout=2.0) as client:
                    return client.get(url)
            except Exception:
                return None

        res = _probe()
        if res is None and ("127.0.0.1" in self.base_url or "localhost" in self.base_url):
            self._try_auto_start_ollama()
            import time
            for _ in range(5):
                time.sleep(0.4)
                res = _probe()
                if res is not None:
                    break

        if res is not None and res.status_code == 200:
            data = res.json()
            models = [m.get("name") for m in data.get("models", [])]
            has_active_model = any(
                m == self.model or m.startswith(f"{self.model}:")
                for m in models
            )
            return {
                "connected": True,
                "base_url": self.base_url,
                "active_model": self.model,
                "has_active_model": has_active_model,
                "available_models": models,
            }
        elif res is not None:
            return {
                "connected": False,
                "base_url": self.base_url,
                "error": f"Ollama returned HTTP status {res.status_code}",
                "setup_instructions": self._get_setup_instructions(),
            }
        else:
            logger.info("Ollama is not reachable at %s", self.base_url)
            return {
                "connected": False,
                "base_url": self.base_url,
                "error": f"Could not connect to Ollama at {self.base_url}",
                "setup_instructions": self._get_setup_instructions(),
            }

    def _get_setup_instructions(self) -> List[str]:
        return [
            "1. Download and install Ollama from https://ollama.com/download (Windows native).",
            "2. Open a terminal or start the Ollama desktop app, or run: ollama serve",
            f"3. Download your preferred local model: ollama pull {self.model}",
            "4. Verify at http://127.0.0.1:11434, then re-check connection in Gideon Settings.",
        ]

    def _format_messages(
        self,
        messages: List[Dict[str, str]],
        system_instruction: Optional[str] = None,
        memories: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, str]]:
        formatted = []
        
        # Build system message including instructions and persistent memories
        system_parts = []
        if system_instruction:
            system_parts.append(system_instruction.strip())
        else:
            system_parts.append(
                "You are Gideon, an advanced local-first AI assistant. You run directly on the user's PC. "
                "You have access to verified local PC context tools. Always speak truthfully, distinguishing "
                "directly observed local evidence from inferences. Be helpful, concise, and accurate."
            )

        if memories:
            memory_lines = [
                f"- [{m.get('category', 'general')}]: {m.get('content', '')}"
                for m in memories
                if m.get("content")
            ]
            if memory_lines:
                system_parts.append(
                    "Relevant persistent memory facts from previous sessions:\n"
                    + "\n".join(memory_lines)
                )

        formatted.append({"role": "system", "content": "\n\n".join(system_parts)})

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role in ["user", "assistant", "system"]:
                formatted.append({"role": role, "content": content})

        return formatted

    def generate_response(
        self,
        messages: List[Dict[str, str]],
        system_instruction: Optional[str] = None,
        memories: Optional[List[Dict[str, Any]]] = None,
        **kwargs: Any
    ) -> str:
        url = f"{self.base_url}/api/chat"
        formatted_messages = self._format_messages(messages, system_instruction, memories)
        payload = {
            "model": self.model,
            "messages": formatted_messages,
            "stream": False,
            "options": {
                "temperature": kwargs.get("temperature", 0.7),
            },
        }

        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                res = client.post(url, json=payload)
                if res.status_code != 200:
                    err_msg = res.text
                    if res.status_code == 404:
                        raise AIProviderError(
                            f"Model '{self.model}' not found in local Ollama. "
                            f"Run 'ollama pull {self.model}' in your terminal."
                        )
                    raise AIProviderError(
                        f"Ollama error (HTTP {res.status_code}): {err_msg}"
                    )
                data = res.json()
                msg = data.get("message", {})
                content = msg.get("content", "").strip()
                if not content:
                    raise AIProviderError("Ollama generated an empty response.")
                return content
        except httpx.ConnectError:
            instructions = "\n".join(self._get_setup_instructions())
            raise AIProviderError(
                f"Cannot connect to local Ollama runtime at {self.base_url}.\n\n"
                f"Setup Guide:\n{instructions}"
            )
        except httpx.TimeoutException:
            raise AIProviderError(
                f"Local Ollama model '{self.model}' timed out after {self.timeout_seconds}s."
            )

    async def generate_response_async(
        self,
        messages: List[Dict[str, str]],
        system_instruction: Optional[str] = None,
        memories: Optional[List[Dict[str, Any]]] = None,
        **kwargs: Any
    ) -> str:
        url = f"{self.base_url}/api/chat"
        formatted_messages = self._format_messages(messages, system_instruction, memories)
        payload = {
            "model": self.model,
            "messages": formatted_messages,
            "stream": False,
            "options": {
                "temperature": kwargs.get("temperature", 0.7),
            },
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                res = await client.post(url, json=payload)
                if res.status_code != 200:
                    if res.status_code == 404:
                        raise AIProviderError(
                            f"Model '{self.model}' not found in local Ollama. "
                            f"Run 'ollama pull {self.model}' in your terminal."
                        )
                    raise AIProviderError(
                        f"Ollama error (HTTP {res.status_code}): {res.text}"
                    )
                data = res.json()
                msg = data.get("message", {})
                content = msg.get("content", "").strip()
                if not content:
                    raise AIProviderError("Ollama generated an empty response.")
                return content
        except httpx.ConnectError:
            instructions = "\n".join(self._get_setup_instructions())
            raise AIProviderError(
                f"Cannot connect to local Ollama runtime at {self.base_url}.\n\n"
                f"Setup Guide:\n{instructions}"
            )
        except httpx.TimeoutException:
            raise AIProviderError(
                f"Local Ollama model '{self.model}' timed out after {self.timeout_seconds}s."
            )

    async def generate_stream(
        self,
        messages: List[Dict[str, str]],
        system_instruction: Optional[str] = None,
        memories: Optional[List[Dict[str, Any]]] = None,
        **kwargs: Any
    ) -> AsyncIterator[str]:
        url = f"{self.base_url}/api/chat"
        formatted_messages = self._format_messages(messages, system_instruction, memories)
        payload = {
            "model": self.model,
            "messages": formatted_messages,
            "stream": True,
            "options": {
                "temperature": kwargs.get("temperature", 0.7),
            },
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                async with client.stream("POST", url, json=payload) as response:
                    if response.status_code != 200:
                        content = await response.aread()
                        if response.status_code == 404:
                            raise AIProviderError(
                                f"Model '{self.model}' not found in local Ollama. "
                                f"Run 'ollama pull {self.model}'."
                            )
                        raise AIProviderError(
                            f"Ollama stream error (HTTP {response.status_code}): {content.decode()}"
                        )

                    async for line in response.aiter_lines():
                        if not line or not line.strip():
                            continue
                        try:
                            chunk_data = json.loads(line)
                            chunk_msg = chunk_data.get("message", {})
                            delta = chunk_msg.get("content", "")
                            if delta:
                                yield delta
                            if chunk_data.get("done", False):
                                break
                        except json.JSONDecodeError:
                            continue
        except httpx.ConnectError:
            instructions = "\n".join(self._get_setup_instructions())
            raise AIProviderError(
                f"Cannot connect to local Ollama runtime at {self.base_url}.\n\n"
                f"Setup Guide:\n{instructions}"
            )
        except httpx.TimeoutException:
            raise AIProviderError(
                f"Local Ollama stream timed out after {self.timeout_seconds}s."
            )


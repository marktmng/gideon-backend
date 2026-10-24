"""Demo AI Provider for local testing and offline execution."""
import asyncio
from typing import List, Dict, Any, Optional, AsyncIterator
from app.ai.base import BaseAIProvider


class DemoAIProvider(BaseAIProvider):
    """
    Local demo provider used for development and testing.
    Does not require external API keys or network access.
    """

    @property
    def name(self) -> str:
        return "demo"

    @property
    def is_demo(self) -> bool:
        return True

    def generate_response(
        self,
        messages: List[Dict[str, str]],
        system_instruction: Optional[str] = None,
        memories: Optional[List[Dict[str, Any]]] = None,
        **kwargs: Any
    ) -> str:
        # Get the latest user message
        last_user_message = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_user_message = msg.get("content", "").strip()
                break

        truncated = (last_user_message[:60] + "...") if len(last_user_message) > 60 else last_user_message

        memory_note = ""
        if memories and len(memories) > 0:
            memory_note = f" (Loaded {len(memories)} relevant reference memory/memories)."

        return (
            f"[Gideon Demo Mode]: I received your message: \"{truncated}\". "
            "I am running in local demo mode without an active external AI API key. "
            f"Conversations, tasks, and system pipelines are fully operational.{memory_note} "
            "Connect an AI provider in your environment configuration to enable real-time generative responses."
        )

    async def generate_stream(
        self,
        messages: List[Dict[str, str]],
        system_instruction: Optional[str] = None,
        memories: Optional[List[Dict[str, Any]]] = None,
        **kwargs: Any
    ) -> AsyncIterator[str]:
        full_response = self.generate_response(
            messages=messages,
            system_instruction=system_instruction,
            memories=memories,
            **kwargs
        )

        # Break into natural phrase chunks to simulate realistic progressive streaming
        words = full_response.split(" ")
        chunk_size = 4
        for i in range(0, len(words), chunk_size):
            chunk = " ".join(words[i:i + chunk_size])
            if i + chunk_size < len(words):
                chunk += " "
            yield chunk
            # Yield control back to event loop for realistic simulation
            await asyncio.sleep(0.01)

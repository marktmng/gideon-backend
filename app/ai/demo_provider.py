"""Demo AI Provider for local offline execution with honest capability reporting."""
import asyncio
from typing import List, Dict, Any, Optional, AsyncIterator
from app.ai.base import BaseAIProvider


class DemoAIProvider(BaseAIProvider):
    """
    Local offline provider used when neither cloud AI (Gemini) nor local LLM (Ollama) is active.
    Provides honest, truthful local responses without requiring external API keys.
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

        query_lower = last_user_message.lower()

        # Check if local context or evidence was injected into the prompt
        evidence_content = ""
        for msg in messages:
            content = msg.get("content", "")
            if "[LOCAL_PC_EVIDENCE]" in content:
                evidence_content = content
                break

        if evidence_content:
            return f"[Gideon Demo Mode]: Based on verified local PC evidence:\n{evidence_content}"

        # If user sends a friendly greeting ("hello Gideon", "hey Gideon", "hi", etc.)
        greeting_words = ["hello", "hey", "hi", "greetings", "good morning", "good afternoon", "good evening"]
        if any(query_lower.startswith(g) or f" {g}" in query_lower for g in greeting_words):
            return "Greetings. I am online and listening. How may I assist you?"

        # If user asks about Gideon's local capabilities
        if any(kw in query_lower for kw in ["what can you do", "help", "capabilities", "features", "commands"]):
            return (
                "I am your personal AI assistant and Windows command core. "
                "I can open and close applications, search Google and YouTube, inspect open windows and screen OCR, "
                "and manage your directives. What would you like me to do?"
            )

        truncated = (last_user_message[:70] + "...") if len(last_user_message) > 70 else last_user_message

        memory_note = ""
        if memories and len(memories) > 0:
            memory_note = f" Loaded {len(memories)} persistent memories from prior sessions."

        return (
            f"[Gideon Demo Mode]: I processed your request: \"{truncated}\".{memory_note}\n\n"
            "I am running in local offline demo mode. Real local PC context tools (window inspection, task status, "
            "screen OCR, and directory summaries) and Phase 4 desktop actions are fully operational.\n"
            "For free, private generative AI responses on this PC, install Ollama and select 'Local AI' in Settings."
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

        words = full_response.split(" ")
        chunk_size = 4
        for i in range(0, len(words), chunk_size):
            chunk = " ".join(words[i:i + chunk_size])
            if i + chunk_size < len(words):
                chunk += " "
            yield chunk
            await asyncio.sleep(0.01)

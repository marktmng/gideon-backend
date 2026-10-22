"""Demo AI Provider for local testing and offline execution."""
from typing import List, Dict, Any
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
        **kwargs: Any
    ) -> str:
        # Get the latest user message
        last_user_message = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_user_message = msg.get("content", "").strip()
                break

        truncated = (last_user_message[:60] + "...") if len(last_user_message) > 60 else last_user_message

        return (
            f"[Gideon Demo Mode]: I received your message: \"{truncated}\". "
            "I am running in local demo mode without an active external AI API key. "
            "Conversations, tasks, and system pipelines are fully operational. "
            "Connect an AI provider in your environment configuration to enable real-time generative responses."
        )

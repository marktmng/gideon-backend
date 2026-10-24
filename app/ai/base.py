"""Abstract base class for AI providers."""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, AsyncIterator


class BaseAIProvider(ABC):
    """Abstract interface for AI model providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the provider."""
        pass

    @property
    @abstractmethod
    def is_demo(self) -> bool:
        """True if the provider is a local mock/demo provider."""
        pass

    @property
    def supports_streaming(self) -> bool:
        """Whether the provider supports streaming responses."""
        return True

    @abstractmethod
    def generate_response(
        self,
        messages: List[Dict[str, str]],
        system_instruction: Optional[str] = None,
        memories: Optional[List[Dict[str, Any]]] = None,
        **kwargs: Any
    ) -> str:
        """
        Generate an assistant response from the conversation history (synchronous).

        :param messages: List of message dicts with 'role' and 'content'.
        :param system_instruction: System prompt to direct assistant behavior.
        :param memories: Relevant persistent memories to include as reference context.
        :return: Assistant text response.
        """
        pass

    async def generate_response_async(
        self,
        messages: List[Dict[str, str]],
        system_instruction: Optional[str] = None,
        memories: Optional[List[Dict[str, Any]]] = None,
        **kwargs: Any
    ) -> str:
        """
        Generate an assistant response asynchronously.
        Defaults to wrapping synchronous generate_response unless overridden.
        """
        return self.generate_response(
            messages=messages,
            system_instruction=system_instruction,
            memories=memories,
            **kwargs
        )

    @abstractmethod
    async def generate_stream(
        self,
        messages: List[Dict[str, str]],
        system_instruction: Optional[str] = None,
        memories: Optional[List[Dict[str, Any]]] = None,
        **kwargs: Any
    ) -> AsyncIterator[str]:
        """
        Generate assistant response as an asynchronous stream of text tokens/deltas.

        :param messages: List of message dicts with 'role' and 'content'.
        :param system_instruction: System prompt to direct assistant behavior.
        :param memories: Relevant persistent memories to include as reference context.
        :return: AsyncIterator yielding string chunks.
        """
        pass

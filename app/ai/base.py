"""Abstract base class for AI providers."""
from abc import ABC, abstractmethod
from typing import List, Dict, Any


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

    @abstractmethod
    def generate_response(
        self,
        messages: List[Dict[str, str]],
        **kwargs: Any
    ) -> str:
        """
        Generate an assistant response from the conversation history.

        :param messages: List of message dicts with 'role' and 'content'.
        :return: Assistant text response.
        """
        pass

"""Google Gemini AI Provider implementing BaseAIProvider interface."""
import asyncio
from typing import List, Dict, Any, Optional, AsyncIterator
from google import genai
from google.genai import types, errors
from app.ai.base import BaseAIProvider
from app.ai.prompts import build_system_instruction
from app.core.config import settings
from app.core.exceptions import (
    AIProviderError,
    AIConfigurationError,
    AIRateLimitError,
    AIProviderTimeoutError,
)
from app.core.logging import get_logger

logger = get_logger(__name__)


class GeminiAIProvider(BaseAIProvider):
    """
    Official Google Gemini AI provider implementation using the google-genai SDK.
    Supports asynchronous text generation, streaming, bounded context, and sandboxed memory injection.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        temperature: Optional[float] = None,
        max_output_tokens: Optional[int] = None,
        client: Optional[Any] = None,
    ):
        self._api_key = api_key or settings.effective_gemini_api_key
        if not self._api_key or not self._api_key.strip():
            raise AIConfigurationError(
                "Gemini API key is not configured. Please set GEMINI_API_KEY in your environment."
            )

        self._model = (model or settings.ai_model or "gemini-2.5-flash").strip()
        self._timeout_seconds = timeout_seconds or settings.ai_request_timeout_seconds or 60
        self._temperature = temperature if temperature is not None else settings.ai_temperature
        self._max_output_tokens = max_output_tokens or settings.ai_max_output_tokens

        # Allow dependency injection of client for unit testing without live credentials
        if client is not None:
            self._client = client
        else:
            http_options = types.HttpOptions(
                timeout=int(self._timeout_seconds * 1000)
            )
            self._client = genai.Client(
                api_key=self._api_key.strip(),
                http_options=http_options,
            )

    @property
    def name(self) -> str:
        return "gemini"

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def is_demo(self) -> bool:
        return False

    @property
    def supports_streaming(self) -> bool:
        return True

    def _format_contents(self, messages: List[Dict[str, str]]) -> List[types.Content]:
        """Convert standard message dictionaries to Gemini types.Content objects."""
        contents: List[types.Content] = []
        for msg in messages:
            raw_role = msg.get("role", "user")
            content_text = msg.get("content", "").strip()

            if not content_text:
                continue

            # System instructions are configured separately in GenerateContentConfig
            if raw_role == "system":
                continue

            # Map assistant to Gemini's expected 'model' role
            gemini_role = "model" if raw_role in ("assistant", "model") else "user"

            part = types.Part.from_text(text=content_text)
            contents.append(types.Content(role=gemini_role, parts=[part]))

        return contents

    def _build_config(
        self,
        system_instruction: Optional[str] = None,
        memories: Optional[List[Dict[str, Any]]] = None,
    ) -> types.GenerateContentConfig:
        """Construct generation configuration with versioned system instruction and memory context."""
        full_instruction = build_system_instruction(
            base_instruction=system_instruction,
            memories=memories,
        )

        return types.GenerateContentConfig(
            system_instruction=full_instruction,
            temperature=self._temperature,
            max_output_tokens=self._max_output_tokens,
        )

    def _sanitize_message(self, text: str) -> str:
        """Strip any API keys or credentials from error text."""
        import re
        sanitized = text
        if self._api_key and self._api_key in sanitized:
            sanitized = sanitized.replace(self._api_key, "[REDACTED_API_KEY]")
        # Redact any AIza... or typical Google API key patterns
        sanitized = re.sub(r"AIza[0-9A-Za-z_\-]{20,}", "[REDACTED_API_KEY]", sanitized)
        # Redact key=... patterns
        sanitized = re.sub(r"(key[=:\s]+)[A-Za-z0-9_\-]+", r"\1[REDACTED]", sanitized, flags=re.IGNORECASE)
        return sanitized

    def _handle_exception(self, err: Exception) -> Exception:
        """Map SDK errors to sanitized domain exceptions without leaking secrets."""
        err_str = self._sanitize_message(str(err))

        if isinstance(err, (asyncio.TimeoutError, TimeoutError)):
            return AIProviderTimeoutError(
                f"Gemini API request timed out after {self._timeout_seconds} seconds."
            )

        if isinstance(err, errors.APIError):
            status_code = getattr(err, "code", None) or getattr(err, "status", None)
            code_str = str(status_code) if status_code else ""

            if (
                code_str in ("401", "403")
                or "API_KEY_INVALID" in err_str
                or "PERMISSION_DENIED" in err_str
                or "UNAUTHENTICATED" in err_str
            ):
                return AIConfigurationError(
                    "Gemini API authentication failed. Verify that your GEMINI_API_KEY is valid."
                )

            if code_str == "429" or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower():
                return AIRateLimitError(
                    "Gemini API rate limit or quota exceeded. Please wait a moment before retrying."
                )

            if code_str in ("408", "504") or "DEADLINE_EXCEEDED" in err_str:
                return AIProviderTimeoutError("Gemini API request timed out.")

            clean_msg = err_str.split("\n")[0] if "\n" in err_str else err_str
            return AIProviderError(f"Gemini generation error: {clean_msg}")

        # Network or other errors
        if "connection" in err_str.lower() or "connect" in err_str.lower():
            return AIProviderError("Unable to connect to Gemini AI services. Check network connectivity.")

        clean_msg = err_str.split("\n")[0] if "\n" in err_str else err_str
        return AIProviderError(f"Gemini generation failed: {clean_msg}")

    def generate_response(
        self,
        messages: List[Dict[str, str]],
        system_instruction: Optional[str] = None,
        memories: Optional[List[Dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> str:
        """Synchronously generate response."""
        contents = self._format_contents(messages)
        if not contents:
            raise ValueError("Cannot generate AI response with empty conversation messages.")

        config = self._build_config(system_instruction=system_instruction, memories=memories)

        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=contents,
                config=config,
            )
            if not response or not response.text:
                raise AIProviderError("Gemini returned an empty response.")
            return response.text
        except Exception as e:
            mapped_err = self._handle_exception(e)
            logger.error("Gemini synchronous generation failed: %s", type(mapped_err).__name__)
            raise mapped_err from None

    async def generate_response_async(
        self,
        messages: List[Dict[str, str]],
        system_instruction: Optional[str] = None,
        memories: Optional[List[Dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> str:
        """Asynchronously generate response."""
        contents = self._format_contents(messages)
        if not contents:
            raise ValueError("Cannot generate AI response with empty conversation messages.")

        config = self._build_config(system_instruction=system_instruction, memories=memories)

        try:
            response = await asyncio.wait_for(
                self._client.aio.models.generate_content(
                    model=self._model,
                    contents=contents,
                    config=config,
                ),
                timeout=self._timeout_seconds,
            )
            if not response or not response.text:
                raise AIProviderError("Gemini returned an empty response.")
            return response.text
        except Exception as e:
            mapped_err = self._handle_exception(e)
            logger.error("Gemini async generation failed: %s", type(mapped_err).__name__)
            raise mapped_err from None

    async def generate_stream(
        self,
        messages: List[Dict[str, str]],
        system_instruction: Optional[str] = None,
        memories: Optional[List[Dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Asynchronously stream generation tokens/deltas."""
        contents = self._format_contents(messages)
        if not contents:
            raise ValueError("Cannot stream AI response with empty conversation messages.")

        config = self._build_config(system_instruction=system_instruction, memories=memories)

        try:
            response_stream = await asyncio.wait_for(
                self._client.aio.models.generate_content_stream(
                    model=self._model,
                    contents=contents,
                    config=config,
                ),
                timeout=self._timeout_seconds,
            )

            has_yielded = False
            async for chunk in response_stream:
                if chunk and chunk.text:
                    has_yielded = True
                    yield chunk.text

            if not has_yielded:
                logger.warning("Gemini stream completed without emitting text chunks.")
        except Exception as e:
            mapped_err = self._handle_exception(e)
            logger.error("Gemini stream generation failed: %s", type(mapped_err).__name__)
            raise mapped_err from None

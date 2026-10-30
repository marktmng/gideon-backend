"""Service coordinating assistant capabilities, runtime diagnostics, and AI generation."""
from typing import List, Dict, Any, Optional, AsyncIterator
from app.ai.base import BaseAIProvider
from app.ai.provider_factory import AIProviderFactory
from app.core.config import settings
from app.core.exceptions import AIConfigurationError, AIProviderError
from app.core.logging import get_logger
from app.models.message import Message
from app.schemas.assistant import AssistantStatus

logger = get_logger(__name__)


class AssistantService:
    def __init__(self, provider: Optional[BaseAIProvider] = None):
        self.provider: Optional[BaseAIProvider] = provider
        self.init_error: Optional[str] = None

        if self.provider is None:
            import os
            is_testing = bool(os.environ.get("PYTEST_CURRENT_TEST") or getattr(settings, "app_env", "") == "test")
            configured_provider = (settings.ai_provider or "demo").lower().strip()

            # Proactively check if local Ollama runtime is available on live startup
            if not is_testing and configured_provider in ["ollama", "local", "demo"]:
                from app.ai.ollama_provider import OllamaAIProvider
                probe_model = settings.ollama_model or "qwen2.5:3b"
                ollama_probe = OllamaAIProvider(
                    base_url=settings.ollama_base_url,
                    model=probe_model,
                    timeout_seconds=settings.ai_request_timeout_seconds,
                )
                conn = ollama_probe.check_connection()
                if conn.get("connected") and conn.get("has_active_model"):
                    self.provider = ollama_probe
                    settings.ai_provider = "ollama"
                    settings.ollama_model = probe_model
                    logger.info("Auto-initialized Local AI with Ollama (%s)", probe_model)
                elif conn.get("connected") and conn.get("available_models"):
                    first_model = conn["available_models"][0]
                    ollama_probe.model = first_model
                    settings.ollama_model = first_model
                    settings.ai_provider = "ollama"
                    self.provider = ollama_probe
                    logger.info("Auto-initialized Local AI with available Ollama model: %s", first_model)

            if self.provider is None:
                try:
                    self.provider = AIProviderFactory.get_provider()
                except AIConfigurationError as err:
                    self.init_error = str(err)
                    logger.warning("Assistant provider initialization deferred: %s", str(err))

    def _ensure_provider(self) -> BaseAIProvider:
        if self.provider is None:
            if self.init_error:
                raise AIConfigurationError(self.init_error)
            self.provider = AIProviderFactory.get_provider()
        return self.provider

    def switch_provider(
        self,
        provider_name: str,
        model: Optional[str] = None,
        validate_connection: bool = False,
    ) -> BaseAIProvider:
        """Switch active AI provider at runtime, optionally validating live availability."""
        clean_name = provider_name.lower().strip()
        if clean_name not in ["demo", "ollama", "local", "gemini"]:
            raise AIConfigurationError(
                f"Unsupported provider '{clean_name}'. Choose 'ollama', 'gemini', or 'demo'."
            )
        
        target_model = model
        if model and clean_name in ["ollama", "local"]:
            settings.ollama_model = model
            target_model = model
        elif model and clean_name == "gemini":
            settings.ai_model = model
            target_model = model

        # Instantiate provider to validate configuration
        new_provider = AIProviderFactory.get_provider(clean_name)

        if validate_connection:
            if clean_name in ["ollama", "local"]:
                conn = new_provider.check_connection()
                if not conn.get("connected"):
                    raise AIConfigurationError(
                        f"Cannot switch to Ollama: Service is not reachable at {getattr(new_provider, 'base_url', 'http://127.0.0.1:11434')}. "
                        "Please install and start Ollama ('ollama serve') before activating Local AI."
                    )
                if not conn.get("has_active_model"):
                    avail = conn.get("available_models", [])
                    avail_str = ", ".join(avail) if avail else "none"
                    effective_m = target_model or settings.ollama_model or "llama3.2"
                    raise AIConfigurationError(
                        f"Ollama is running, but model '{effective_m}' is not installed (installed models: {avail_str}). "
                        f"Run 'ollama pull {effective_m}' before activating."
                    )
            elif clean_name == "gemini":
                api_key = settings.effective_gemini_api_key
                if not api_key or not api_key.strip():
                    raise AIConfigurationError(
                        "Gemini AI provider requested, but no valid API key was found. "
                        "Configure GEMINI_API_KEY in backend/.env."
                    )

        settings.ai_provider = clean_name
        self.provider = new_provider
        self.init_error = None
        logger.info("Switched active AI provider to '%s' (model: %s)", clean_name, target_model or "default")
        return self.provider

    def get_status(self, db_connected: bool = True, check_live: bool = False) -> AssistantStatus:
        provider_name = self.provider.name if self.provider else (settings.ai_provider or "unknown")
        is_demo = self.provider.is_demo if self.provider else (provider_name == "demo")
        has_credentials = bool(settings.effective_gemini_api_key and settings.effective_gemini_api_key.strip())
        streaming_supported = self.provider.supports_streaming if self.provider else False

        if provider_name in ["ollama", "local"]:
            active_model = settings.ollama_model or "qwen2.5:3b"
            if check_live and hasattr(self.provider, "check_connection"):
                conn = self.provider.check_connection()
                if conn.get("connected") and conn.get("has_active_model"):
                    system_status = "local_ai_active"
                    has_credentials = True
                else:
                    system_status = "ollama_offline"
                    has_credentials = False
            else:
                system_status = "local_ai_active"
                has_credentials = True  # Default nominal state
        elif is_demo:
            system_status = "demo_mode"
            active_model = "qwen2.5:3b"
        elif has_credentials:
            system_status = "configured"
            active_model = settings.ai_model if settings.ai_model else "gemini-2.5-flash"
        else:
            system_status = "unconfigured"
            active_model = settings.ai_model if settings.ai_model else "unconfigured"

        return AssistantStatus(
            name=settings.app_name,
            version="5.1.0 (Local-First Awareness)",
            provider=provider_name,
            is_demo=is_demo,
            model=active_model,
            status=system_status,
            has_provider_credentials=has_credentials,
            streaming_supported=streaming_supported,
            memory_enabled=True,
            database_connected=db_connected,
            provider_initialized=self.provider is not None,
            capabilities=[
                "conversations_persistent",
                "message_history",
                "context_aware_generation",
                "streaming_responses",
                "persistent_memory_retrieval",
                "task_management",
                "google_gemini_provider",
                "offline_demo_provider",
                "local_ollama_provider",
                "local_pc_screen_awareness",
                "windows_native_ocr",
                "workspace_file_inspection",
                "opt_in_local_monitoring",
                "database_migrations",
                "voice_speech_interaction",
                "camera_vision_service",
                "hand_gesture_recognition",
                "futuristic_tech_brain_ui",
                "desktop_automation_bridge",
                "agent_orchestration_engine",
                "multi_step_task_automation",
                "specialized_agents_registry",
                "consequential_action_approvals",
            ],
            unconfigured_features=[
                "wake_word_continuous_activation",
                "calendar_email_direct_sync",
                "biometric_facial_identification",
            ],
        )

    def generate_response(
        self,
        context_messages: List[Message],
        memories: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        provider = self._ensure_provider()
        formatted = [
            {"role": msg.role, "content": msg.content}
            for msg in context_messages
        ]
        return provider.generate_response(messages=formatted, memories=memories)

    async def generate_response_async(
        self,
        context_messages: List[Message],
        memories: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        provider = self._ensure_provider()
        formatted = [
            {"role": msg.role, "content": msg.content}
            for msg in context_messages
        ]
        return await provider.generate_response_async(messages=formatted, memories=memories)

    async def generate_stream(
        self,
        context_messages: List[Message],
        memories: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncIterator[str]:
        provider = self._ensure_provider()
        formatted = [
            {"role": msg.role, "content": msg.content}
            for msg in context_messages
        ]
        async for chunk in provider.generate_stream(messages=formatted, memories=memories):
            yield chunk

from collections.abc import Mapping
from typing import Any

from .config import AIConfig
from .context import build_ai_context
from .prompts import (
    build_debug_analysis_prompt,
    build_explain_error_prompt,
    build_next_step_prompt,
)
from .provider import (
    AIProviderError,
    BaseAIProvider,
    MockAIProvider,
    OpenAICompatibleProvider,
    _redact_secret,
)


class AIServiceError(Exception):
    def __init__(self, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def _error_result(code: str, message: str, details: dict | None = None) -> dict[str, Any]:
    return {
        "success": False,
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        },
    }


def create_provider(config: AIConfig) -> BaseAIProvider:
    if config.provider == "mock":
        return MockAIProvider()
    if config.provider == "openai-compatible":
        return OpenAICompatibleProvider()
    raise AIServiceError("AI_CONFIG_ERROR", f"Unsupported AI provider: {config.provider}")


class AIAnalysisService:
    def __init__(
        self,
        controller: Any,
        config: AIConfig,
        provider: BaseAIProvider | None = None,
    ):
        self.controller = controller
        self.config = config
        self.provider = provider

    def get_config(self) -> dict[str, Any]:
        return self.config.to_safe_dict()

    def update_config(self, updates: Mapping[str, Any]) -> dict[str, Any]:
        self.config = self.config.with_overrides(updates)
        if self.provider is None and self.config.provider == "mock":
            self.provider = MockAIProvider()
        return self.get_config()

    def analyze(self, question: str | None = None) -> dict[str, Any]:
        return self._run_analysis(
            lambda context: build_debug_analysis_prompt(context, question)
        )

    def explain_error(self, error_message: str | None = None) -> dict[str, Any]:
        return self._run_analysis(
            lambda context: build_explain_error_prompt(context, error_message)
        )

    def suggest_next_step(self) -> dict[str, Any]:
        return self._run_analysis(build_next_step_prompt)

    def _run_analysis(self, prompt_builder) -> dict[str, Any]:
        if not self.config.enabled:
            return _error_result(
                "AI_DISABLED",
                "AI assistant is disabled. Enable it explicitly before requesting analysis.",
            )

        errors = self.config.validate()
        if errors:
            return _error_result(
                "AI_CONFIG_ERROR",
                "AI configuration is invalid",
                {"errors": errors},
            )

        try:
            provider = self.provider if self.provider is not None else create_provider(self.config)
        except AIServiceError as exc:
            return _error_result(exc.code, exc.message, exc.details)

        context = build_ai_context(self.controller, self.config)
        messages = prompt_builder(context)

        try:
            analysis = provider.analyze(messages, self.config)
        except AIProviderError as exc:
            return _error_result(
                "AI_PROVIDER_ERROR", _redact_secret(str(exc), self.config.api_key)
            )

        return {
            "success": True,
            "data": {
                "analysis": analysis,
                "context_summary": context.to_redacted_dict(),
                "provider": self.config.provider,
                "model": self.config.model,
            },
        }

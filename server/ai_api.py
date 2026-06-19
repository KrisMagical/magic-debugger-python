"""Shared AI API helpers for HTTP and RPC layers."""

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from ai import AIAnalysisService, AIConfig
from ai.config import _FIELD_NAMES, _coerce_field
from ai.provider import BaseAIProvider
from server.errors import error_payload, success_payload


class AIAPIState:
    """In-memory AI configuration and service factory for one server process."""

    def __init__(
        self,
        controller: Any,
        ai_config: AIConfig | None = None,
        provider: BaseAIProvider | None = None,
    ):
        self.controller = controller
        self.config = ai_config or AIConfig.from_env()
        self.provider = provider

    def get_config(self) -> dict[str, Any]:
        return success_payload(self.config.to_safe_dict())

    def update_config(self, updates: Mapping[str, Any] | None) -> dict[str, Any]:
        if not isinstance(updates, Mapping):
            return error_payload("AI_CONFIG_ERROR", "AI config update must be an object")

        try:
            update_values = {
                name: _coerce_field(name, value)
                for name, value in updates.items()
                if name in _FIELD_NAMES
            }
            updated = replace(self.config, **update_values)
        except (TypeError, ValueError) as exc:
            return error_payload("AI_CONFIG_ERROR", str(exc))

        self.config = updated
        return success_payload(self.config.to_safe_dict())

    def analyze(self, question: Any = None) -> dict[str, Any]:
        if question is not None and not isinstance(question, str):
            return error_payload("AI_CONFIG_ERROR", "AI question must be a string")
        return self._service().analyze(question)

    def explain_error(self, error_message: Any = None) -> dict[str, Any]:
        if error_message is not None and not isinstance(error_message, str):
            return error_payload("AI_CONFIG_ERROR", "AI error message must be a string")
        return self._service().explain_error(error_message)

    def suggest_next_step(self) -> dict[str, Any]:
        return self._service().suggest_next_step()

    def _service(self) -> AIAnalysisService:
        return AIAnalysisService(self.controller, self.config, provider=self.provider)


def unwrap_success_data(result: dict[str, Any]) -> Any:
    """Return RPC result data for successful AI calls, preserving error payloads."""
    if result.get("success") is True:
        return result.get("data")
    return result

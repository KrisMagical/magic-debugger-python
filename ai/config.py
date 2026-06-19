import os
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any


_BOOL_TRUE = {"1", "true", "yes", "on"}
_BOOL_FALSE = {"0", "false", "no", "off"}

_FIELD_NAMES = {
    "enabled",
    "provider",
    "model",
    "base_url",
    "api_key",
    "timeout",
    "max_context_chars",
    "include_source",
    "include_variables",
    "include_stack",
    "include_breakpoints",
}

_BOOL_FIELDS = {
    "enabled",
    "include_source",
    "include_variables",
    "include_stack",
    "include_breakpoints",
}


def _parse_bool(value: Any, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _BOOL_TRUE:
            return True
        if normalized in _BOOL_FALSE:
            return False
    raise ValueError(f"Invalid boolean value for {field_name}: {value!r}")


def _coerce_field(name: str, value: Any) -> Any:
    if name in _BOOL_FIELDS:
        return _parse_bool(value, name)
    if name == "timeout":
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid float value for timeout: {value!r}") from exc
    if name == "max_context_chars":
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Invalid integer value for max_context_chars: {value!r}"
            ) from exc
    if name in {"provider", "model", "base_url", "api_key"}:
        if value is None:
            return ""
        return str(value)
    return value


def _config_kwargs(data: Mapping[str, Any]) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    for name in _FIELD_NAMES:
        if name in data:
            kwargs[name] = _coerce_field(name, data[name])
    return kwargs


@dataclass(frozen=True)
class AIConfig:
    enabled: bool = False
    provider: str = "openai-compatible"
    model: str = ""
    base_url: str = ""
    api_key: str = field(default="", repr=False)
    timeout: float = 30.0
    max_context_chars: int = 12000
    include_source: bool = False
    include_variables: bool = False
    include_stack: bool = True
    include_breakpoints: bool = True

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "AIConfig":
        source = os.environ if env is None else env
        mapping = {
            "enabled": "MAGIC_DEBUG_AI_ENABLED",
            "provider": "MAGIC_DEBUG_AI_PROVIDER",
            "model": "MAGIC_DEBUG_AI_MODEL",
            "base_url": "MAGIC_DEBUG_AI_BASE_URL",
            "api_key": "MAGIC_DEBUG_AI_API_KEY",
            "timeout": "MAGIC_DEBUG_AI_TIMEOUT",
            "max_context_chars": "MAGIC_DEBUG_AI_MAX_CONTEXT_CHARS",
            "include_source": "MAGIC_DEBUG_AI_INCLUDE_SOURCE",
            "include_variables": "MAGIC_DEBUG_AI_INCLUDE_VARIABLES",
            "include_stack": "MAGIC_DEBUG_AI_INCLUDE_STACK",
            "include_breakpoints": "MAGIC_DEBUG_AI_INCLUDE_BREAKPOINTS",
        }

        data = {
            field_name: source[env_name]
            for field_name, env_name in mapping.items()
            if env_name in source
        }
        return cls(**_config_kwargs(data))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "AIConfig":
        if data is None:
            return cls()

        source: Mapping[str, Any]
        nested = data.get("ai")
        if isinstance(nested, Mapping):
            source = nested
        else:
            source = data
        return cls(**_config_kwargs(source))

    def merge(self, other: "AIConfig") -> "AIConfig":
        updates = {
            "enabled": other.enabled,
            "provider": other.provider,
            "timeout": other.timeout,
            "max_context_chars": other.max_context_chars,
            "include_source": other.include_source,
            "include_variables": other.include_variables,
            "include_stack": other.include_stack,
            "include_breakpoints": other.include_breakpoints,
        }
        for name in ("model", "base_url", "api_key"):
            value = getattr(other, name)
            if value:
                updates[name] = value
        return replace(self, **updates)

    def with_overrides(self, updates: Mapping[str, Any]) -> "AIConfig":
        return self.merge(AIConfig.from_dict(updates))

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "api_key": "***" if self.api_key else "",
            "timeout": self.timeout,
            "max_context_chars": self.max_context_chars,
            "include_source": self.include_source,
            "include_variables": self.include_variables,
            "include_stack": self.include_stack,
            "include_breakpoints": self.include_breakpoints,
        }

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.timeout <= 0:
            errors.append("AI timeout must be greater than 0")
        if self.max_context_chars < 1000:
            errors.append("AI max_context_chars must be at least 1000")
        if not self.provider:
            errors.append("AI provider must not be empty")
        if self.provider and self.provider not in {"openai-compatible", "mock"}:
            errors.append(f"Unsupported AI provider: {self.provider}")

        for name in _BOOL_FIELDS:
            if not isinstance(getattr(self, name), bool):
                errors.append(f"AI {name} must be a boolean")

        if self.enabled:
            if not self.model:
                errors.append("AI model is required when AI is enabled")
            if not self.base_url:
                errors.append("AI base_url is required when AI is enabled")
            if not self.api_key:
                errors.append("AI api_key is required when AI is enabled")

        return errors

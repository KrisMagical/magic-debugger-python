import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ai import AIConfig  # noqa: E402


def test_default_config_is_disabled_and_privacy_preserving():
    config = AIConfig()

    assert config.enabled is False
    assert config.provider == "openai-compatible"
    assert config.include_source is False
    assert config.include_variables is False
    assert config.include_stack is True
    assert config.include_breakpoints is True


def test_from_env_reads_core_fields_and_secret():
    config = AIConfig.from_env(
        {
            "MAGIC_DEBUG_AI_ENABLED": "true",
            "MAGIC_DEBUG_AI_PROVIDER": "mock",
            "MAGIC_DEBUG_AI_MODEL": "debug-model",
            "MAGIC_DEBUG_AI_BASE_URL": "https://api.example.com/v1",
            "MAGIC_DEBUG_AI_API_KEY": "secret-key",
            "MAGIC_DEBUG_AI_TIMEOUT": "12.5",
            "MAGIC_DEBUG_AI_MAX_CONTEXT_CHARS": "24000",
            "MAGIC_DEBUG_AI_INCLUDE_SOURCE": "yes",
            "MAGIC_DEBUG_AI_INCLUDE_VARIABLES": "1",
            "MAGIC_DEBUG_AI_INCLUDE_STACK": "off",
            "MAGIC_DEBUG_AI_INCLUDE_BREAKPOINTS": "0",
        }
    )

    assert config.enabled is True
    assert config.provider == "mock"
    assert config.model == "debug-model"
    assert config.base_url == "https://api.example.com/v1"
    assert config.api_key == "secret-key"
    assert config.timeout == 12.5
    assert config.max_context_chars == 24000
    assert config.include_source is True
    assert config.include_variables is True
    assert config.include_stack is False
    assert config.include_breakpoints is False


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("true", True),
        ("false", False),
        ("1", True),
        ("0", False),
        ("yes", True),
        ("no", False),
        ("on", True),
        ("off", False),
        ("TRUE", True),
        ("NO", False),
    ],
)
def test_from_env_bool_parsing(value, expected):
    config = AIConfig.from_env({"MAGIC_DEBUG_AI_ENABLED": value})

    assert config.enabled is expected


def test_from_env_rejects_invalid_numbers():
    with pytest.raises(ValueError):
        AIConfig.from_env({"MAGIC_DEBUG_AI_TIMEOUT": "slow"})

    with pytest.raises(ValueError):
        AIConfig.from_env({"MAGIC_DEBUG_AI_MAX_CONTEXT_CHARS": "many"})


def test_from_dict_reads_direct_ai_dict():
    config = AIConfig.from_dict(
        {
            "enabled": True,
            "provider": "mock",
            "model": "m",
            "base_url": "http://localhost",
            "api_key": "secret",
            "unknown": "ignored",
        }
    )

    assert config.enabled is True
    assert config.provider == "mock"
    assert config.model == "m"
    assert config.base_url == "http://localhost"
    assert config.api_key == "secret"


def test_from_dict_reads_magic_debug_json_ai_section():
    config = AIConfig.from_dict(
        {
            "program": "/tmp/test",
            "ai": {
                "enabled": "yes",
                "model": "nested-model",
                "base_url": "https://api.example.com/v1",
                "api_key": "nested-secret",
            },
        }
    )

    assert config.enabled is True
    assert config.model == "nested-model"
    assert config.api_key == "nested-secret"


def test_from_dict_none_returns_default_config():
    assert AIConfig.from_dict(None) == AIConfig()


def test_safe_dict_and_repr_do_not_leak_api_key():
    config = AIConfig(api_key="very-secret")

    safe = config.to_safe_dict()
    assert safe["api_key"] == "***"
    assert "very-secret" not in repr(config)
    assert "very-secret" not in str(safe)


def test_safe_dict_empty_api_key_stays_empty():
    assert AIConfig().to_safe_dict()["api_key"] == ""


def test_validate_disabled_allows_empty_provider_details():
    config = AIConfig()

    assert config.validate() == []


def test_validate_enabled_requires_provider_details():
    config = AIConfig(enabled=True)
    errors = config.validate()

    assert "AI model is required when AI is enabled" in errors
    assert "AI base_url is required when AI is enabled" in errors
    assert "AI api_key is required when AI is enabled" in errors


def test_validate_rejects_bad_limits_and_provider():
    errors = AIConfig(timeout=0, max_context_chars=999, provider="unknown").validate()

    assert "AI timeout must be greater than 0" in errors
    assert "AI max_context_chars must be at least 1000" in errors
    assert "Unsupported AI provider: unknown" in errors


def test_validate_requires_boolean_context_flags():
    config = AIConfig(include_source="yes")  # type: ignore[arg-type]

    assert "AI include_source must be a boolean" in config.validate()


def test_merge_overrides_values_without_empty_secret_overwrite():
    base = AIConfig(
        enabled=False,
        model="base-model",
        base_url="https://base.example.com/v1",
        api_key="base-secret",
        include_stack=True,
    )
    override = AIConfig(
        enabled=True,
        model="override-model",
        base_url="",
        api_key="",
        include_stack=False,
    )

    merged = base.merge(override)

    assert merged.enabled is True
    assert merged.model == "override-model"
    assert merged.base_url == "https://base.example.com/v1"
    assert merged.api_key == "base-secret"
    assert merged.include_stack is False
    assert base.enabled is False


def test_with_overrides_uses_dict_conversion():
    config = AIConfig().with_overrides({"enabled": "on", "provider": "mock"})

    assert config.enabled is True
    assert config.provider == "mock"


def test_config_example_ai_defaults_are_safe():
    config = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8"))

    ai_config = config["ai"]
    assert ai_config["enabled"] is False
    assert ai_config["api_key"] == ""
    assert ai_config["include_source"] is False
    assert ai_config["include_variables"] is False
    assert ai_config["include_stack"] is True
    assert ai_config["include_breakpoints"] is True

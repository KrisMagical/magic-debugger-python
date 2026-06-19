import sys
import json
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ai import AIConfig  # noqa: E402
from ai.provider import (  # noqa: E402
    AIProviderError,
    MockAIProvider,
    OpenAICompatibleProvider,
    _redact_secret,
)


MESSAGES = [
    {"role": "system", "content": "You are a Debug Assistant."},
    {"role": "user", "content": 'Task: Analyze\n{"status": "stopped"}'},
]


def test_mock_provider_returns_deterministic_text():
    provider = MockAIProvider()

    first = provider.analyze(MESSAGES, AIConfig(provider="mock"))
    second = provider.analyze(MESSAGES, AIConfig(provider="mock"))

    assert first == second
    assert "Mock AI Analysis" in first
    assert "Suggested next steps" in first
    assert "Confidence" in first
    assert "stopped" in first


def test_mock_provider_does_not_need_or_leak_api_key():
    result = MockAIProvider().analyze(
        MESSAGES, AIConfig(provider="mock", api_key="super-secret")
    )

    assert "super-secret" not in result


@pytest.mark.parametrize("messages", [[], [{"role": "user"}], ["not-a-message"]])
def test_mock_provider_rejects_invalid_messages(messages):
    with pytest.raises(AIProviderError):
        MockAIProvider().analyze(messages, AIConfig(provider="mock"))  # type: ignore[arg-type]


def openai_config(**overrides):
    data = {
        "provider": "openai-compatible",
        "model": "debug-model",
        "base_url": "https://api.example.test/v1",
        "api_key": "super-secret",
        "timeout": 12.5,
    }
    data.update(overrides)
    return AIConfig(**data)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        if isinstance(self.payload, bytes):
            return self.payload
        return json.dumps(self.payload).encode("utf-8")


def test_openai_provider_requires_api_key():
    with pytest.raises(AIProviderError, match="API key"):
        OpenAICompatibleProvider().analyze(MESSAGES, openai_config(api_key=""))


def test_openai_provider_requires_base_url():
    with pytest.raises(AIProviderError, match="base URL"):
        OpenAICompatibleProvider().analyze(MESSAGES, openai_config(base_url=""))


def test_openai_provider_requires_model():
    with pytest.raises(AIProviderError, match="model"):
        OpenAICompatibleProvider().analyze(MESSAGES, openai_config(model=""))


@pytest.mark.parametrize("messages", [[], [{"role": "user"}], ["bad"]])
def test_openai_provider_rejects_invalid_messages(messages):
    with pytest.raises(AIProviderError):
        OpenAICompatibleProvider().analyze(messages, openai_config())  # type: ignore[arg-type]


def test_openai_provider_sends_chat_completion_request(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse(
            {"choices": [{"message": {"content": "  useful analysis  "}}]}
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    result = OpenAICompatibleProvider().analyze(MESSAGES, openai_config())

    request = captured["request"]
    body = json.loads(request.data.decode("utf-8"))
    assert result == "useful analysis"
    assert request.full_url == "https://api.example.test/v1/chat/completions"
    assert captured["timeout"] == 12.5
    assert body["model"] == "debug-model"
    assert body["messages"] == MESSAGES
    assert body["temperature"] == 0.2
    assert body["max_tokens"] == 800
    assert request.get_header("Authorization") == "Bearer super-secret"
    assert request.get_header("Content-type") == "application/json"


def test_openai_provider_http_error_redacts_api_key(monkeypatch):
    def fake_urlopen(request, timeout):
        raise HTTPError(
            request.full_url,
            401,
            "Unauthorized",
            hdrs=None,
            fp=BytesIO(b'{"error":"super-secret is invalid"}'),
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    with pytest.raises(AIProviderError) as exc_info:
        OpenAICompatibleProvider().analyze(MESSAGES, openai_config())

    message = str(exc_info.value)
    assert "401" in message
    assert "super-secret" not in message
    assert "***" in message


def test_openai_provider_url_error(monkeypatch):
    def fake_urlopen(request, timeout):
        raise URLError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    with pytest.raises(AIProviderError, match="network error"):
        OpenAICompatibleProvider().analyze(MESSAGES, openai_config())


def test_openai_provider_invalid_json(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda request, timeout: FakeResponse(b"not json")
    )

    with pytest.raises(AIProviderError, match="invalid JSON"):
        OpenAICompatibleProvider().analyze(MESSAGES, openai_config())


@pytest.mark.parametrize(
    "payload",
    [
        {"choices": []},
        {"choices": [{"message": {}}]},
        {"choices": [{"message": {"content": ""}}]},
    ],
)
def test_openai_provider_rejects_missing_or_empty_content(monkeypatch, payload):
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda request, timeout: FakeResponse(payload)
    )

    with pytest.raises(AIProviderError):
        OpenAICompatibleProvider().analyze(MESSAGES, openai_config())


def test_openai_provider_supports_text_fallback(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda request, timeout: FakeResponse({"choices": [{"text": "fallback"}]}),
    )

    assert OpenAICompatibleProvider().analyze(MESSAGES, openai_config()) == "fallback"


def test_redact_secret_replaces_api_key():
    assert _redact_secret("bad super-secret token", "super-secret") == "bad *** token"
    assert _redact_secret("safe", "") == "safe"

import copy
import json
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ai import AIConfig, AIAnalysisService  # noqa: E402
from ai.provider import AIProviderError, BaseAIProvider  # noqa: E402


@dataclass
class FakeFrame:
    id: int = 1
    name: str = "main"
    file: str = "/tmp/main.c"
    line: int = 10
    column: int = 1


class FakeState:
    def __init__(self):
        self.status = "stopped"
        self.stop_reason = "breakpoint"
        self.current_thread_id = 1
        self.current_frame_id = 1
        self.stack_frames = [FakeFrame()]
        self.breakpoints = {"/tmp/main.c": [{"line": 10, "verified": True}]}
        self.variables = {1: [{"name": "password", "type": "str", "value": "secret"}]}
        self.session_info = {"program": "/tmp/test", "cwd": "/tmp", "args": []}


class FakeController:
    def __init__(self):
        self.state = FakeState()

    def continue_(self):
        raise AssertionError("AI service must not call debug controls")

    def step_over(self):
        raise AssertionError("AI service must not call debug controls")


class FailingProvider(BaseAIProvider):
    def analyze(self, messages, config):
        raise AIProviderError("provider failed")


class RecordingProvider(BaseAIProvider):
    def __init__(self, analysis="fake openai analysis"):
        self.analysis = analysis
        self.messages = None
        self.config = None

    def analyze(self, messages, config):
        self.messages = messages
        self.config = config
        return self.analysis


def enabled_mock_config(**kwargs):
    data = {
        "enabled": True,
        "provider": "mock",
        "model": "mock-model",
        "base_url": "mock://local",
        "api_key": "secret-key",
    }
    data.update(kwargs)
    return AIConfig(**data)


def enabled_openai_config(**kwargs):
    data = {
        "enabled": True,
        "provider": "openai-compatible",
        "model": "openai-model",
        "base_url": "https://api.example.test/v1",
        "api_key": "secret-key",
    }
    data.update(kwargs)
    return AIConfig(**data)


def test_get_config_does_not_return_plain_api_key():
    service = AIAnalysisService(FakeController(), enabled_mock_config())

    config = service.get_config()

    assert config["api_key"] == "***"
    assert "secret-key" not in json.dumps(config)


def test_update_config_does_not_return_plain_api_key():
    service = AIAnalysisService(FakeController(), AIConfig())

    config = service.update_config({"api_key": "new-secret", "provider": "mock"})

    assert config["api_key"] == "***"
    assert "new-secret" not in json.dumps(config)


def test_analyze_returns_ai_disabled_when_disabled():
    result = AIAnalysisService(FakeController(), AIConfig()).analyze()

    assert result["success"] is False
    assert result["error"]["code"] == "AI_DISABLED"


def test_mock_provider_analyze_success_contains_context_and_metadata():
    result = AIAnalysisService(FakeController(), enabled_mock_config()).analyze("What now?")

    assert result["success"] is True
    data = result["data"]
    assert "Mock AI Analysis" in data["analysis"]
    assert data["context_summary"]["status"] == "stopped"
    assert data["provider"] == "mock"
    assert data["model"] == "mock-model"
    assert "api_key" not in json.dumps(data)


def test_explain_error_and_next_step_succeed():
    service = AIAnalysisService(FakeController(), enabled_mock_config())

    assert service.explain_error("boom")["success"] is True
    assert service.suggest_next_step()["success"] is True


def test_provider_error_returns_structured_error():
    result = AIAnalysisService(
        FakeController(), enabled_mock_config(), provider=FailingProvider()
    ).analyze()

    assert result["success"] is False
    assert result["error"]["code"] == "AI_PROVIDER_ERROR"
    assert "provider failed" in result["error"]["message"]


def test_invalid_config_returns_config_error():
    result = AIAnalysisService(FakeController(), AIConfig(enabled=True)).analyze()

    assert result["success"] is False
    assert result["error"]["code"] == "AI_CONFIG_ERROR"


def test_openai_compatible_can_use_injected_provider_without_network():
    provider = RecordingProvider()

    result = AIAnalysisService(
        FakeController(), enabled_openai_config(), provider=provider
    ).analyze()

    assert result["success"] is True
    assert result["data"]["analysis"] == "fake openai analysis"
    assert result["data"]["provider"] == "openai-compatible"
    assert result["data"]["model"] == "openai-model"
    assert provider.messages is not None
    assert provider.config.provider == "openai-compatible"
    assert "secret-key" not in json.dumps(result)


def test_openai_compatible_factory_path_can_be_monkeypatched_without_network(monkeypatch):
    class FakeOpenAIProvider(RecordingProvider):
        pass

    monkeypatch.setattr("ai.service.OpenAICompatibleProvider", FakeOpenAIProvider)

    result = AIAnalysisService(FakeController(), enabled_openai_config()).analyze()

    assert result["success"] is True
    assert result["data"]["analysis"] == "fake openai analysis"


def test_openai_provider_error_returns_structured_error_without_leaking_key():
    result = AIAnalysisService(
        FakeController(), enabled_openai_config(), provider=FailingProvider()
    ).analyze()

    assert result["success"] is False
    assert result["error"]["code"] == "AI_PROVIDER_ERROR"
    assert "secret-key" not in json.dumps(result)


def test_openai_missing_required_config_returns_config_error():
    result = AIAnalysisService(
        FakeController(), enabled_openai_config(api_key="")
    ).analyze()

    assert result["success"] is False
    assert result["error"]["code"] == "AI_CONFIG_ERROR"


def test_openai_compatible_explain_error_and_next_step_with_fake_provider():
    service = AIAnalysisService(
        FakeController(), enabled_openai_config(), provider=RecordingProvider()
    )

    assert service.explain_error("boom")["success"] is True
    assert service.suggest_next_step()["success"] is True


def test_service_does_not_modify_state_or_call_controls():
    controller = FakeController()
    before = copy.deepcopy(controller.state.__dict__)

    result = AIAnalysisService(controller, enabled_mock_config()).analyze()

    assert result["success"] is True
    assert controller.state.__dict__ == before


def test_question_can_be_empty():
    assert AIAnalysisService(FakeController(), enabled_mock_config()).analyze()["success"] is True


def test_variables_and_source_default_absent_from_context_summary():
    result = AIAnalysisService(FakeController(), enabled_mock_config()).analyze()
    summary = result["data"]["context_summary"]

    assert summary["variables_summary"] == []
    assert summary["source_snippet"] is None
    assert "secret" not in json.dumps(summary)

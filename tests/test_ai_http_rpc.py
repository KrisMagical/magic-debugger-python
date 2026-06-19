import copy
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ai.provider import AIProviderError, BaseAIProvider  # noqa: E402
from server.http import HTTPAPIServer  # noqa: E402
from server.rpc import RPCServer  # noqa: E402


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
        self.variables = {1: [{"name": "token", "type": "str", "value": "secret"}]}
        self.session_info = {"program": "/tmp/test", "cwd": "/tmp", "args": []}
        self.threads = []
        self.scopes = []

    def get_file_breakpoints(self, file_path):
        return []

    def get_all_breakpoints(self):
        return []

    def get_output(self, category=None, limit=100):
        return []


class FakeController:
    def __init__(self):
        self.state = FakeState()

    def get_status(self):
        return {"status": "stopped"}

    def get_full_state(self):
        return {"status": "stopped"}

    def continue_(self):
        raise AssertionError("AI API must not call debug controls")

    def step_over(self):
        raise AssertionError("AI API must not call debug controls")

    def on(self, event, callback):
        pass


class FailingProvider(BaseAIProvider):
    def analyze(self, messages, config):
        raise AIProviderError("provider failed with secret-key")


def mock_config(secret="secret-key"):
    return {
        "enabled": True,
        "provider": "mock",
        "model": "mock-debugger",
        "base_url": "mock://local",
        "api_key": secret,
    }


def assert_no_secret(payload, secret="secret-key"):
    assert secret not in json.dumps(payload)


def test_http_get_ai_config_returns_safe_default_config():
    status, payload = HTTPAPIServer(FakeController()).handle_request(
        "GET", "/api/ai/config", query={}
    )

    assert status == 200
    assert payload["success"] is True
    assert payload["data"]["enabled"] is False
    assert payload["data"]["api_key"] == ""


def test_http_update_ai_config_can_enable_mock_and_masks_key():
    server = HTTPAPIServer(FakeController())

    status, payload = server.handle_request(
        "POST", "/api/ai/config", payload=mock_config()
    )

    assert status == 200
    assert payload["data"]["enabled"] is True
    assert payload["data"]["provider"] == "mock"
    assert payload["data"]["api_key"] == "***"
    assert_no_secret(payload)


def test_http_analyze_disabled_returns_409():
    status, payload = HTTPAPIServer(FakeController()).handle_request(
        "POST", "/api/ai/analyze", payload={"question": "why?"}
    )

    assert status == 409
    assert payload["success"] is False
    assert payload["error"]["code"] == "AI_DISABLED"


def test_http_ai_analysis_methods_succeed_with_mock_provider():
    server = HTTPAPIServer(FakeController())
    server.handle_request("POST", "/api/ai/config", payload=mock_config())

    for path, payload in [
        ("/api/ai/analyze", {"question": "Why did it stop?"}),
        ("/api/ai/explain-error", {"error": "Segmentation fault"}),
        ("/api/ai/suggest-next-step", {}),
    ]:
        status, response = server.handle_request("POST", path, payload=payload)
        assert status == 200
        assert response["success"] is True
        assert "Mock AI Analysis" in response["data"]["analysis"]
        assert_no_secret(response)


def test_http_openai_missing_config_returns_config_error_without_network():
    server = HTTPAPIServer(FakeController())
    server.handle_request(
        "POST",
        "/api/ai/config",
        payload={"enabled": True, "provider": "openai-compatible", "model": "m"},
    )

    status, payload = server.handle_request(
        "POST", "/api/ai/analyze", payload={"question": "why?"}
    )

    assert status == 400
    assert payload["error"]["code"] == "AI_CONFIG_ERROR"


def test_http_provider_error_returns_502_and_masks_key():
    server = HTTPAPIServer(FakeController(), ai_provider=FailingProvider())
    server.handle_request("POST", "/api/ai/config", payload=mock_config())

    status, payload = server.handle_request(
        "POST", "/api/ai/analyze", payload={"question": "why?"}
    )

    assert status == 502
    assert payload["error"]["code"] == "AI_PROVIDER_ERROR"
    assert_no_secret(payload)


def test_http_analyze_does_not_modify_controller_state():
    controller = FakeController()
    server = HTTPAPIServer(controller)
    server.handle_request("POST", "/api/ai/config", payload=mock_config())
    before = copy.deepcopy(controller.state.__dict__)

    status, payload = server.handle_request(
        "POST", "/api/ai/analyze", payload={"question": "why?"}
    )

    assert status == 200
    assert payload["success"] is True
    assert controller.state.__dict__ == before


def test_rpc_get_config_returns_safe_config():
    response = RPCServer(FakeController())._handle_request(
        {"id": 1, "method": "ai.getConfig", "params": {}}
    ).to_dict()

    assert response["type"] == "response"
    assert response["id"] == 1
    assert response["success"] is True
    assert response["result"]["enabled"] is False
    assert response["result"]["api_key"] == ""


def test_rpc_update_config_and_mock_analyze_success():
    server = RPCServer(FakeController())

    update = server._handle_request(
        {"id": 2, "method": "ai.updateConfig", "params": mock_config()}
    ).to_dict()
    response = server._handle_request(
        {
            "id": 3,
            "method": "ai.analyze",
            "params": {"question": "why?"},
        }
    ).to_dict()

    assert update["success"] is True
    assert update["result"]["api_key"] == "***"
    assert response["type"] == "response"
    assert response["id"] == 3
    assert response["success"] is True
    assert "Mock AI Analysis" in response["result"]["analysis"]
    assert_no_secret(response)


def test_rpc_ai_analyze_disabled_returns_error_not_result():
    response = RPCServer(FakeController())._handle_request(
        {"id": 4, "method": "ai.analyze", "params": {"question": "why?"}}
    ).to_dict()

    assert response["type"] == "response"
    assert response["id"] == 4
    assert response["success"] is False
    assert response["error"]["code"] == "AI_DISABLED"
    assert "result" not in response


def test_rpc_ai_explain_error_and_suggest_next_step_success():
    server = RPCServer(FakeController())
    server._handle_request({"id": 5, "method": "ai.updateConfig", "params": mock_config()})

    explain = server._handle_request(
        {"id": 6, "method": "ai.explainError", "params": {"error": "boom"}}
    ).to_dict()
    next_step = server._handle_request(
        {"id": 7, "method": "ai.suggestNextStep", "params": {}}
    ).to_dict()

    assert explain["success"] is True
    assert next_step["success"] is True
    assert "Mock AI Analysis" in explain["result"]["analysis"]
    assert "Mock AI Analysis" in next_step["result"]["analysis"]


def test_rpc_ai_failure_shape_and_key_masking():
    server = RPCServer(FakeController(), ai_provider=FailingProvider())
    server._handle_request({"id": 8, "method": "ai.updateConfig", "params": mock_config()})

    response = server._handle_request(
        {"id": 9, "method": "ai.analyze", "params": {"question": "why?"}}
    ).to_dict()

    assert response["type"] == "response"
    assert response["id"] == 9
    assert response["success"] is False
    assert response["error"]["code"] == "AI_PROVIDER_ERROR"
    assert "result" not in response
    assert_no_secret(response)


def test_rpc_unknown_ai_method_returns_method_not_found():
    response = RPCServer(FakeController())._handle_request(
        {"id": 10, "method": "ai.nope", "params": {}}
    ).to_dict()

    assert response["success"] is False
    assert response["error"]["code"] == "METHOD_NOT_FOUND"

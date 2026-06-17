import sys
from types import SimpleNamespace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.http import HTTPAPIServer
from server.rpc import RPCResponse, RPCServer


class FakeController:
    def __init__(self):
        self.state = SimpleNamespace(
            threads=[],
            stack_frames=[],
            scopes=[],
            current_thread_id=None,
            current_frame_id=None,
            get_file_breakpoints=lambda file_path: [],
            get_all_breakpoints=lambda: [],
            get_output=lambda category=None, limit=100: [],
        )

    def get_status(self):
        return {"status": "idle"}

    def get_full_state(self):
        return {"status": "idle"}

    def start(self, config):
        return True

    def continue_(self):
        return False

    def set_breakpoint(self, *args, **kwargs):
        return True

    def on(self, event, callback):
        pass


def assert_error_shape(payload):
    assert payload["success"] is False
    assert "error" in payload
    assert isinstance(payload["error"]["code"], str)
    assert payload["error"]["message"]
    assert payload["error"]["details"] == {}


def test_http_parameter_error_returns_400():
    server = HTTPAPIServer(FakeController())

    status, payload = server.handle_request("POST", "/api/start", payload={})

    assert status == 400
    assert_error_shape(payload)
    assert payload["error"]["code"] == "BAD_REQUEST"


def test_http_state_conflict_returns_409():
    server = HTTPAPIServer(FakeController())

    status, payload = server.handle_request("POST", "/api/continue", payload={})

    assert status == 409
    assert_error_shape(payload)
    assert payload["error"]["code"] == "INVALID_STATE"


def test_http_not_found_returns_404():
    server = HTTPAPIServer(FakeController())

    status, payload = server.handle_request("GET", "/api/nope", query={})

    assert status == 404
    assert_error_shape(payload)
    assert payload["error"]["code"] == "NOT_FOUND"


def test_http_internal_exception_returns_500_without_traceback():
    controller = FakeController()

    def explode():
        raise RuntimeError("boom")

    controller.continue_ = explode
    server = HTTPAPIServer(controller)

    status, payload = server.handle_request("POST", "/api/continue", payload={})

    assert status == 500
    assert_error_shape(payload)
    assert payload["error"]["code"] == "INTERNAL_ERROR"
    assert "Traceback" not in payload["error"]["message"]


def test_rpc_unknown_method_returns_error_not_result():
    server = RPCServer(FakeController())

    response = server._handle_request(
        {"id": 1, "method": "unknown.method", "params": {}}
    ).to_dict()

    assert response["type"] == "response"
    assert response["id"] == 1
    assert response["success"] is False
    assert response["error"]["code"] == "METHOD_NOT_FOUND"
    assert "result" not in response


def test_rpc_parameter_error_returns_bad_request():
    server = RPCServer(FakeController())

    response = server._handle_request(
        {"id": 2, "method": "setBreakpoint", "params": {}}
    ).to_dict()

    assert response["type"] == "response"
    assert response["id"] == 2
    assert response["success"] is False
    assert response["error"]["code"] == "BAD_REQUEST"
    assert "result" not in response


def test_rpc_state_error_returns_invalid_state():
    server = RPCServer(FakeController())

    response = server._handle_request(
        {"id": 3, "method": "continue", "params": {}}
    ).to_dict()

    assert response["type"] == "response"
    assert response["id"] == 3
    assert response["success"] is False
    assert response["error"]["code"] == "INVALID_STATE"
    assert "result" not in response


def test_rpc_response_and_event_are_distinguishable():
    server = RPCServer(FakeController())

    event = server._format_event({"event": "stopped", "body": {"threadId": 1}})
    response = RPCResponse(id=4, result={"ok": True}).to_dict()

    assert event["type"] == "event"
    assert event["event"] == "stopped"
    assert "id" not in event
    assert response["type"] == "response"
    assert response["id"] == 4
    assert response["success"] is True

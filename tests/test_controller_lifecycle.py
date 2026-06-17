"""Controller lifecycle and active-thread safety tests."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.controller import DebugConfig, DebugController
from core.dap import DAPClient
from core.state import DebugState, DebugStatus


class FakeDAP:
    def __init__(self):
        self.handlers = {}
        self.calls = []

    def on_event(self, event, handler):
        self.handlers[event] = handler

    def start_reader(self):
        self.calls.append(("start_reader", None))

    def initialize(self):
        self.calls.append(("initialize", None))
        return {"success": True, "body": {}}

    def launch(self, **kwargs):
        self.calls.append(("launch", kwargs))
        return {"success": True}

    def configuration_done(self):
        self.calls.append(("configuration_done", None))
        return {"success": True}

    def continue_(self, thread_id=None):
        self.calls.append(("continue", thread_id))
        return {"success": True}

    def pause(self, thread_id=None):
        self.calls.append(("pause", thread_id))
        return {"success": True}

    def step_over(self, thread_id):
        self.calls.append(("step_over", thread_id))
        return {"success": True}

    def step_into(self, thread_id):
        self.calls.append(("step_into", thread_id))
        return {"success": True}

    def step_out(self, thread_id):
        self.calls.append(("step_out", thread_id))
        return {"success": True}

    def threads(self):
        self.calls.append(("threads", None))
        return {"success": True, "body": {"threads": []}}

    def stack_trace(self, thread_id):
        self.calls.append(("stack_trace", thread_id))
        return {"success": True, "body": {"stackFrames": []}}


def make_controller():
    state = DebugState()
    dap = FakeDAP()
    controller = DebugController(dap, state)
    return controller, dap, state


def test_current_thread_id_initially_none():
    assert DebugState().current_thread_id is None


def test_reset_runtime_does_not_clear_breakpoints():
    state = DebugState()
    state.update_breakpoints("main.c", [{"line": 12, "verified": True}])

    state.reset_runtime()

    assert state.get_file_breakpoints("main.c")


def test_start_preserves_preconfigured_breakpoints_and_does_not_enter_running():
    controller, dap, state = make_controller()
    assert controller.set_breakpoint("main.c", 12)

    assert controller.start(DebugConfig(program="prog"))

    assert state.get_file_breakpoints("main.c")
    assert state.status == DebugStatus.CONFIGURED
    assert state.status != DebugStatus.RUNNING


def test_stopped_event_updates_current_thread_id():
    controller, dap, state = make_controller()
    controller._initialized = True

    controller._on_stopped({"reason": "breakpoint", "threadId": 3})

    assert state.status == DebugStatus.STOPPED
    assert state.current_thread_id == 3


def test_continued_event_updates_running():
    controller, dap, state = make_controller()

    controller._on_continued({"threadId": 3})

    assert state.status == DebugStatus.RUNNING


def test_step_without_active_thread_does_not_send_thread_zero():
    controller, dap, state = make_controller()
    controller._initialized = True
    state.status = DebugStatus.STOPPED
    state.current_thread_id = None

    assert controller.step_over() is False

    assert ("step_over", 0) not in dap.calls
    assert not any(call[0] == "step_over" for call in dap.calls)


def test_continue_without_active_thread_does_not_send_thread_zero():
    controller, dap, state = make_controller()
    controller._initialized = True
    state.status = DebugStatus.STOPPED
    state.current_thread_id = None

    assert controller.continue_() is True

    assert ("continue", None) in dap.calls
    assert ("continue", 0) not in dap.calls


def test_run_in_terminal_unsupported_does_not_fake_success():
    class RecordingDAP(DAPClient):
        def __init__(self):
            self.responses = []

        def send_response(self, request_seq, command, success, message=None, body=None):
            self.responses.append(
                {
                    "request_seq": request_seq,
                    "command": command,
                    "success": success,
                    "message": message,
                    "body": body,
                }
            )

    dap = RecordingDAP()
    dap._handle_reverse_request({"seq": 9, "command": "runInTerminal"})

    assert dap.responses
    response = dap.responses[0]
    assert response["success"] is False
    assert "not supported" in response["message"]
    assert response["body"] is None

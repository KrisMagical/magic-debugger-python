import copy
import json
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ai import AIConfig, DebugAIContext, build_ai_context  # noqa: E402
from ai.context import collect_source_snippet  # noqa: E402


@dataclass
class FakeFrame:
    id: int
    name: str
    file: str
    line: int
    column: int = 1


@dataclass
class FakeBreakpoint:
    file: str
    line: int
    verified: bool = True
    condition: str | None = None
    hit_condition: str | None = None


@dataclass
class FakeVariable:
    name: str
    type: str
    value: str


class FakeState:
    def __init__(self, source_file=None):
        self.status = "stopped"
        self.stop_reason = "breakpoint"
        self.current_thread_id = 7
        self.current_frame_id = 11
        self.stack_frames = [
            FakeFrame(11, "main", str(source_file or "/tmp/main.c"), 8),
            {"id": 12, "function": "helper", "path": "/tmp/helper.c", "lineno": 3},
        ]
        self.breakpoints = {
            str(source_file or "/tmp/main.c"): [
                FakeBreakpoint(str(source_file or "/tmp/main.c"), 8, condition="x > 1")
            ],
            "/tmp/other.c": [{"line": 2, "verified": False}],
        }
        self.variables = {
            1: [
                FakeVariable("secret", "char *", "s" * 200),
                {"name": "count", "type": "int", "value": "3"},
            ]
        }
        self.exception_info = None
        self.session_info = {
            "program": "/tmp/test_sample",
            "cwd": "/tmp",
            "args": ["--flag"],
        }

    def get_top_frame(self):
        return self.stack_frames[0]


class FakeController:
    def __init__(self, state):
        self.state = state

    def continue_(self):
        raise AssertionError("build_ai_context must not call control methods")

    def step_over(self):
        raise AssertionError("build_ai_context must not call control methods")


def test_build_ai_context_reads_status_from_controller_state():
    context = build_ai_context(FakeController(FakeState()), AIConfig())

    assert context.status == "stopped"
    assert context.stopped_reason == "breakpoint"
    assert context.current_thread_id == 7
    assert context.current_frame_id == 11
    assert context.program == "/tmp/test_sample"
    assert context.cwd == "/tmp"
    assert context.args == ["--flag"]


def test_default_collects_stack_and_breakpoints_but_not_variables_or_source():
    context = build_ai_context(FakeController(FakeState()), AIConfig())

    assert context.stack_frames
    assert context.stack_frames[0]["name"] == "main"
    assert context.breakpoints
    assert context.variables_summary == []
    assert context.source_snippet is None
    assert context.omitted["variables"] == "disabled by config"
    assert context.omitted["source"] == "disabled by config"


def test_include_variables_collects_summary_and_truncates_preview():
    context = build_ai_context(
        FakeController(FakeState()), AIConfig(include_variables=True)
    )

    assert context.variables_summary
    secret = context.variables_summary[0]
    assert secret["name"] == "secret"
    assert secret["type"] == "char *"
    assert len(secret["value_preview"]) <= 120
    assert secret["value_preview"].endswith("...")


def test_include_source_reads_small_window_near_current_frame(tmp_path):
    source = tmp_path / "sample.c"
    source.write_text("\n".join(f"line {i}" for i in range(1, 30)), encoding="utf-8")

    context = build_ai_context(
        FakeController(FakeState(source)), AIConfig(include_source=True)
    )

    assert context.source_snippet is not None
    assert "8: line 8" in context.source_snippet
    assert "3: line 3" in context.source_snippet
    assert "13: line 13" in context.source_snippet
    snippet_lines = context.source_snippet.splitlines()
    assert "1: line 1" not in snippet_lines
    assert "20: line 20" not in snippet_lines


def test_small_context_limit_truncates_context():
    state = FakeState()
    state.stack_frames = [
        {"id": i, "name": f"frame-{i}", "file": "/tmp/a.c", "line": i}
        for i in range(100)
    ]

    context = build_ai_context(
        FakeController(state), AIConfig(max_context_chars=1000, include_variables=True)
    )

    assert context.truncated is True
    assert context.omitted["truncation"] == "context exceeded max_context_chars"
    assert len(json.dumps(context.to_prompt_dict(), ensure_ascii=False)) <= 1200


def test_build_ai_context_does_not_modify_state():
    state = FakeState()
    before = copy.deepcopy(state.__dict__)

    build_ai_context(FakeController(state), AIConfig(include_variables=True))

    assert state.__dict__ == before


def test_missing_state_does_not_crash():
    context = build_ai_context(object(), AIConfig())

    assert context.status == "unknown"
    assert context.stack_frames == []
    assert context.breakpoints == []


def test_stack_frames_accept_dicts_lists_and_objects():
    state = FakeState()
    state.stack_frames = [
        {"frameId": 1, "function": "dict_frame", "source": {"path": "/tmp/a.c"}, "line": 4},
        FakeFrame(2, "object_frame", "/tmp/b.c", 5),
    ]

    context = build_ai_context(FakeController(state), AIConfig())

    assert context.stack_frames[0]["id"] == 1
    assert context.stack_frames[0]["name"] == "dict_frame"
    assert context.stack_frames[0]["file"] == "/tmp/a.c"
    assert context.stack_frames[1]["name"] == "object_frame"


def test_breakpoints_accept_dicts_lists_and_objects():
    state = FakeState()
    state.breakpoints = {
        "/tmp/a.c": [{"line": 1, "verified": True}],
        "/tmp/b.c": [FakeBreakpoint("/tmp/b.c", 2, hit_condition="5")],
    }

    context = build_ai_context(FakeController(state), AIConfig())

    assert {"file": "/tmp/a.c", "line": 1, "verified": True, "condition": None, "hit_condition": None} in context.breakpoints
    assert any(bp["file"] == "/tmp/b.c" and bp["hit_condition"] == "5" for bp in context.breakpoints)


def test_prompt_and_redacted_dict_are_json_serializable_and_secret_free():
    context = build_ai_context(
        FakeController(FakeState()), AIConfig(include_variables=True, api_key="api-token")
    )

    prompt = context.to_prompt_dict()
    redacted = context.to_redacted_dict()

    json.dumps(prompt)
    json.dumps(redacted)
    assert "api_key" not in json.dumps(redacted)
    assert "api-token" not in json.dumps(redacted)


def test_collect_source_snippet_missing_path_returns_none():
    frame = {"source": {"path": "/path/does/not/exist.c"}, "line": 1}

    assert collect_source_snippet(None, frame, 12000) is None


def test_include_source_false_does_not_read_file_or_expose_source(tmp_path):
    source = tmp_path / "secret.c"
    source.write_text("int secret = 42;\n", encoding="utf-8")

    context = build_ai_context(FakeController(FakeState(source)), AIConfig())

    assert context.source_snippet is None
    assert "secret = 42" not in json.dumps(context.to_prompt_dict())


def test_include_variables_false_does_not_expose_variable_values():
    context = build_ai_context(FakeController(FakeState()), AIConfig())

    serialized = json.dumps(context.to_prompt_dict())
    assert context.variables_summary == []
    assert "ssssssss" not in serialized

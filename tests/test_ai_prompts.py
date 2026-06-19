import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ai.context import DebugAIContext  # noqa: E402
from ai.prompts import (  # noqa: E402
    build_debug_analysis_prompt,
    build_explain_error_prompt,
    build_next_step_prompt,
)


def make_context():
    return DebugAIContext(
        status="stopped",
        stopped_reason="breakpoint",
        current_thread_id=3,
        current_frame_id=9,
        stack_frames=[{"id": 9, "name": "main", "file": "/tmp/main.c", "line": 12}],
        breakpoints=[{"file": "/tmp/main.c", "line": 12, "verified": True}],
        variables_summary=[{"name": "x", "type": "int", "value_preview": "3"}],
        source_snippet="12: x += 2;",
        recent_error="example error",
        program="/tmp/test",
        cwd="/tmp",
        args=["--flag"],
        truncated=True,
        omitted={"source": "disabled by config"},
    )


def test_debug_analysis_prompt_returns_system_and_user_messages():
    messages = build_debug_analysis_prompt(make_context())

    assert [message["role"] for message in messages] == ["system", "user"]


def test_system_prompt_contains_safety_constraints():
    system = build_debug_analysis_prompt(make_context())[0]["content"].lower()

    assert "debug assistant" in system
    assert "only analyze the provided debug context" in system
    assert "do not invent" in system
    assert "do not automatically execute" in system
    assert "do not automatically modify" in system
    assert "insufficient" in system
    assert "advisory" in system


def test_user_prompt_contains_context_and_question():
    user = build_debug_analysis_prompt(make_context(), "Why did it stop?")[1]["content"]

    assert '"status": "stopped"' in user
    assert '"name": "main"' in user
    assert '"breakpoints"' in user
    assert "Why did it stop?" in user
    assert '"truncated": true' in user
    assert '"omitted"' in user


def test_explain_error_prompt_includes_error_message():
    user = build_explain_error_prompt(make_context(), "segmentation fault")[1]["content"]

    assert "segmentation fault" in user
    assert "Explain the error" in user


def test_next_step_prompt_contains_next_step_semantics():
    user = build_next_step_prompt(make_context())[1]["content"]

    assert "Suggest the next debugging step" in user
    assert "Suggested next steps" in user


def test_prompt_does_not_include_api_key():
    serialized = json.dumps(build_debug_analysis_prompt(make_context()))

    assert "api_key" not in serialized
    assert "secret-token" not in serialized


def test_prompt_messages_are_json_serializable():
    json.dumps(build_debug_analysis_prompt(make_context()))
    json.dumps(build_explain_error_prompt(make_context()))
    json.dumps(build_next_step_prompt(make_context()))

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import AIConfig


@dataclass
class DebugAIContext:
    status: str
    stopped_reason: str | None = None
    current_thread_id: int | None = None
    current_frame_id: int | None = None
    stack_frames: list[dict[str, Any]] = field(default_factory=list)
    breakpoints: list[dict[str, Any]] = field(default_factory=list)
    variables_summary: list[dict[str, Any]] = field(default_factory=list)
    recent_error: str | None = None
    program: str | None = None
    cwd: str | None = None
    args: list[str] = field(default_factory=list)
    source_snippet: str | None = None
    truncated: bool = False
    omitted: dict[str, str] = field(default_factory=dict)

    def to_prompt_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "stopped_reason": self.stopped_reason,
            "current_thread_id": self.current_thread_id,
            "current_frame_id": self.current_frame_id,
            "stack_frames": self.stack_frames,
            "breakpoints": self.breakpoints,
            "variables_summary": self.variables_summary,
            "recent_error": self.recent_error,
            "program": self.program,
            "cwd": self.cwd,
            "args": self.args,
            "source_snippet": self.source_snippet,
            "truncated": self.truncated,
            "omitted": self.omitted,
        }

    def to_redacted_dict(self) -> dict[str, Any]:
        return self.to_prompt_dict()


def get_attr_or_key(obj: Any, name: str, default: Any = None) -> Any:
    try:
        if isinstance(obj, Mapping):
            return obj.get(name, default)
        return getattr(obj, name, default)
    except Exception:
        return default


def _first_value(obj: Any, names: Iterable[str], default: Any = None) -> Any:
    for name in names:
        value = get_attr_or_key(obj, name, None)
        if value is not None:
            return value
    return default


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        items: list[Any] = []
        for key, item in value.items():
            if isinstance(item, list | tuple | set):
                items.extend(item)
            else:
                items.append((key, item))
        return items
    if isinstance(value, list | tuple | set):
        return list(value)
    return [value]


def _source_path(source: Any) -> str | None:
    if source is None:
        return None
    path = _first_value(source, ("path", "file", "name"))
    return str(path) if path else None


def _frame_file(frame: Any) -> str | None:
    source = get_attr_or_key(frame, "source")
    path = _first_value(frame, ("file", "path"))
    return str(path) if path else _source_path(source)


def _normalize_frame(frame: Any) -> dict[str, Any]:
    line = _first_value(frame, ("line", "lineno"), 0)
    column = _first_value(frame, ("column", "col"), 0)
    return {
        "id": _safe_int(_first_value(frame, ("id", "frameId"))) or 0,
        "name": str(_first_value(frame, ("name", "function"), "<unknown>")),
        "file": _frame_file(frame),
        "line": _safe_int(line) or 0,
        "column": _safe_int(column) or 0,
    }


def collect_stack_frames(state: Any, limit: int = 20) -> list[dict[str, Any]]:
    try:
        frames = _as_list(get_attr_or_key(state, "stack_frames", []))
        return [_normalize_frame(frame) for frame in frames[:limit]]
    except Exception:
        return []


def _normalize_breakpoint(item: Any) -> dict[str, Any]:
    path_hint = None
    bp = item
    if isinstance(item, tuple) and len(item) == 2:
        path_hint, bp = item
    source = get_attr_or_key(bp, "source")
    path = _first_value(bp, ("file", "path"))
    if not path:
        path = _source_path(source) or path_hint

    line = _first_value(bp, ("line", "lineno"), 0)
    return {
        "file": str(path) if path else None,
        "line": _safe_int(line) or 0,
        "verified": bool(get_attr_or_key(bp, "verified", False)),
        "condition": _first_value(bp, ("condition",), None),
        "hit_condition": _first_value(bp, ("hit_condition", "hitCondition"), None),
    }


def collect_breakpoints(state: Any, limit: int = 100) -> list[dict[str, Any]]:
    try:
        raw = get_attr_or_key(state, "breakpoints", [])
        items: list[Any] = []
        if isinstance(raw, Mapping):
            for path, breakpoints in raw.items():
                for breakpoint in _as_list(breakpoints):
                    items.append((path, breakpoint))
        else:
            items = _as_list(raw)
        return [_normalize_breakpoint(item) for item in items[:limit]]
    except Exception:
        return []


def _value_preview(value: Any, limit: int = 120) -> str:
    preview = "" if value is None else str(value)
    if len(preview) > limit:
        return preview[: limit - 3] + "..."
    return preview


def _normalize_variable(variable: Any) -> dict[str, Any]:
    return {
        "name": str(_first_value(variable, ("name",), "")),
        "type": _first_value(variable, ("type",), None),
        "value_preview": _value_preview(_first_value(variable, ("value",), "")),
    }


def collect_variables_summary(state: Any, limit: int = 50) -> list[dict[str, Any]]:
    try:
        raw = get_attr_or_key(state, "variables", [])
        variables: list[Any] = []
        if isinstance(raw, Mapping):
            for value in raw.values():
                variables.extend(_as_list(value))
        else:
            variables = _as_list(raw)
        return [_normalize_variable(variable) for variable in variables[:limit]]
    except Exception:
        return []


def _current_frame(state: Any) -> Any:
    try:
        get_top_frame = get_attr_or_key(state, "get_top_frame")
        if callable(get_top_frame):
            frame = get_top_frame()
            if frame is not None:
                return frame
    except Exception:
        pass
    frames = _as_list(get_attr_or_key(state, "stack_frames", []))
    return frames[0] if frames else None


def collect_source_snippet(state: Any, current_frame: Any, max_chars: int) -> str | None:
    if current_frame is None:
        return None
    file_path = _frame_file(current_frame)
    line = _safe_int(_first_value(current_frame, ("line", "lineno"), 0)) or 0
    if not file_path or "://" in file_path or line <= 0:
        return None

    try:
        path = Path(file_path).expanduser()
        if not path.is_file() or path.stat().st_size > 1_000_000:
            return None
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None

    start = max(1, line - 5)
    end = min(len(lines), line + 5)
    snippet_lines = [f"{idx}: {lines[idx - 1]}" for idx in range(start, end + 1)]
    snippet = "\n".join(snippet_lines)
    if len(snippet) > max_chars:
        return snippet[: max(0, max_chars - 3)] + "..."
    return snippet


def _json_size(context: DebugAIContext) -> int:
    return len(json.dumps(context.to_prompt_dict(), ensure_ascii=False, sort_keys=True))


def truncate_context(context: DebugAIContext, max_chars: int) -> DebugAIContext:
    limit = max(200, int(max_chars or 0))
    if _json_size(context) <= limit:
        return context

    context.truncated = True
    context.omitted["truncation"] = "context exceeded max_context_chars"

    if context.source_snippet:
        context.source_snippet = context.source_snippet[: max(0, limit // 4)] + "..."
    while context.variables_summary and _json_size(context) > limit:
        context.variables_summary.pop()
    while context.stack_frames and _json_size(context) > limit:
        context.stack_frames.pop()
    while context.breakpoints and _json_size(context) > limit:
        context.breakpoints.pop()
    if context.source_snippet and _json_size(context) > limit:
        context.source_snippet = None
        context.omitted["source"] = "omitted by context size limit"
    if context.variables_summary and _json_size(context) > limit:
        context.variables_summary = []
        context.omitted["variables"] = "omitted by context size limit"

    return context


def _controller_state(controller: Any) -> Any:
    state = get_attr_or_key(controller, "state")
    if state is not None:
        return state
    get_state = get_attr_or_key(controller, "get_state")
    if callable(get_state):
        try:
            return get_state()
        except Exception:
            return None
    return None


def _session_info(state: Any) -> Any:
    return get_attr_or_key(state, "session_info", {}) if state is not None else {}


def _recent_error(state: Any) -> str | None:
    value = _first_value(state, ("last_error", "recent_error", "exception_info"), None)
    if value is None:
        return None
    return str(value)


def build_ai_context(controller: Any, config: AIConfig) -> DebugAIContext:
    state = _controller_state(controller)
    session_info = _session_info(state)
    status = _enum_value(get_attr_or_key(state, "status", "unknown"))
    stopped_reason = _enum_value(
        _first_value(state, ("stopped_reason", "stop_reason", "reason"), None)
    )

    context = DebugAIContext(
        status=str(status),
        stopped_reason=str(stopped_reason) if stopped_reason is not None else None,
        current_thread_id=_safe_int(get_attr_or_key(state, "current_thread_id")),
        current_frame_id=_safe_int(get_attr_or_key(state, "current_frame_id")),
        recent_error=_recent_error(state),
        program=_first_value(session_info, ("program",), None),
        cwd=_first_value(session_info, ("cwd",), None),
        args=list(_as_list(_first_value(session_info, ("args",), []))),
    )

    if config.include_stack:
        context.stack_frames = collect_stack_frames(state)
    else:
        context.omitted["stack"] = "disabled by config"

    if config.include_breakpoints:
        context.breakpoints = collect_breakpoints(state)
    else:
        context.omitted["breakpoints"] = "disabled by config"

    if config.include_variables:
        context.variables_summary = collect_variables_summary(state)
    else:
        context.omitted["variables"] = "disabled by config"

    current_frame = _current_frame(state)
    if config.include_source:
        context.source_snippet = collect_source_snippet(
            state, current_frame, config.max_context_chars
        )
        if context.source_snippet is None:
            context.omitted["source"] = "unavailable"
    else:
        context.omitted["source"] = "disabled by config"

    return truncate_context(context, config.max_context_chars)

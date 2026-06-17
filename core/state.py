"""Debug state model for DAP data."""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class DebugStatus(Enum):
    """Debug session status."""

    IDLE = "idle"
    INITIALIZING = "initializing"
    LAUNCHING = "launching"
    CONFIGURED = "configured"
    RUNNING = "running"
    STOPPED = "stopped"
    PAUSED = "paused"
    TERMINATED = "terminated"
    ERROR = "error"


class StopReason(Enum):
    """Stop reason."""

    BREAKPOINT = "breakpoint"
    STEP = "step"
    EXCEPTION = "exception"
    PAUSE = "pause"
    ENTRY = "entry"
    GOTO = "goto"
    FUNCTION_BREAKPOINT = "function breakpoint"
    DATA_BREAKPOINT = "data breakpoint"
    INSTRUCTION_BREAKPOINT = "instruction breakpoint"
    UNKNOWN = "unknown"


@dataclass
class SourceLocation:
    """Source code location."""

    path: str
    line: int
    column: Optional[int] = None
    end_line: Optional[int] = None
    end_column: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {"path": self.path, "line": self.line}
        if self.column is not None:
            result["column"] = self.column
        if self.end_line is not None:
            result["endLine"] = self.end_line
        if self.end_column is not None:
            result["endColumn"] = self.end_column
        return result

    def __str__(self) -> str:
        result = f"{self.path}:{self.line}"
        if self.column is not None:
            result += f":{self.column}"
        return result


@dataclass
class StackFrame:
    """Call stack frame."""

    id: int
    name: str
    source: Optional[SourceLocation] = None
    line: int = 0
    column: int = 0
    instruction_pointer_reference: Optional[str] = None
    module_id: Optional[str] = None
    presentation_hint: Optional[str] = None

    @classmethod
    def from_dap(cls, frame: Dict[str, Any]) -> "StackFrame":
        source = None
        if frame.get("source"):
            src = frame["source"]
            source = SourceLocation(
                path=src.get("path") or src.get("name", "<unknown>"),
                line=frame.get("line", 0),
                column=frame.get("column"),
            )

        return cls(
            id=frame.get("id", 0),
            name=frame.get("name", "<unknown>"),
            source=source,
            line=frame.get("line", 0),
            column=frame.get("column", 0),
            instruction_pointer_reference=frame.get("instructionPointerReference"),
            module_id=frame.get("moduleId"),
            presentation_hint=frame.get("presentationHint"),
        )

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "id": self.id,
            "name": self.name,
            "line": self.line,
            "column": self.column,
        }
        if self.source:
            result["source"] = self.source.to_dict()
        if self.instruction_pointer_reference:
            result["instructionPointerReference"] = self.instruction_pointer_reference
        return result


@dataclass
class Thread:
    """Debug thread."""

    id: int
    name: str = ""

    @classmethod
    def from_dap(cls, thread: Dict[str, Any]) -> "Thread":
        thread_id = thread.get("id", 0)
        return cls(id=thread_id, name=thread.get("name", f"Thread-{thread_id}"))

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "name": self.name}


@dataclass
class Scope:
    """Variable scope."""

    name: str
    variables_reference: int
    expensive: bool = False
    source: Optional[SourceLocation] = None
    line: int = 0
    column: int = 0

    @classmethod
    def from_dap(cls, scope: Dict[str, Any]) -> "Scope":
        source = None
        if scope.get("source"):
            source = SourceLocation(
                path=scope["source"].get("path", ""),
                line=scope.get("line", 0),
            )

        return cls(
            name=scope.get("name", ""),
            variables_reference=scope.get("variablesReference", 0),
            expensive=scope.get("expensive", False),
            source=source,
            line=scope.get("line", 0),
            column=scope.get("column", 0),
        )

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "name": self.name,
            "variablesReference": self.variables_reference,
            "expensive": self.expensive,
        }
        if self.source:
            result["source"] = self.source.to_dict()
        return result


@dataclass
class Variable:
    """DAP variable."""

    name: str
    value: str
    type: Optional[str] = None
    variables_reference: int = 0
    evaluate_name: Optional[str] = None
    memory_reference: Optional[str] = None
    presentation_hint: Optional[Dict] = None

    @classmethod
    def from_dap(cls, var: Dict[str, Any]) -> "Variable":
        return cls(
            name=var.get("name", ""),
            value=var.get("value", ""),
            type=var.get("type"),
            variables_reference=var.get("variablesReference", 0),
            evaluate_name=var.get("evaluateName"),
            memory_reference=var.get("memoryReference"),
            presentation_hint=var.get("presentationHint"),
        )

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "name": self.name,
            "value": self.value,
            "variablesReference": self.variables_reference,
        }
        if self.type:
            result["type"] = self.type
        if self.evaluate_name:
            result["evaluateName"] = self.evaluate_name
        return result

    def has_children(self) -> bool:
        return self.variables_reference > 0


@dataclass
class Breakpoint:
    """Breakpoint state."""

    id: Optional[int] = None
    verified: bool = False
    source: Optional[SourceLocation] = None
    line: int = 0
    column: Optional[int] = None
    condition: Optional[str] = None
    hit_condition: Optional[str] = None
    log_message: Optional[str] = None
    message: Optional[str] = None

    @classmethod
    def from_dap(cls, bp: Dict[str, Any], source_path: str = "") -> "Breakpoint":
        return cls(
            id=bp.get("id"),
            verified=bp.get("verified", False),
            source=SourceLocation(path=source_path, line=bp.get("line", 0)),
            line=bp.get("line", 0) or bp.get("source", {}).get("line", 0),
            message=bp.get("message"),
        )

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "id": self.id,
            "verified": self.verified,
            "line": self.line,
        }
        if self.source:
            result["source"] = self.source.to_dict()
        if self.message:
            result["message"] = self.message
        return result


@dataclass
class DebugSessionInfo:
    """Debug session information."""

    program: str = ""
    args: List[str] = field(default_factory=list)
    cwd: Optional[str] = None
    env: Dict[str, str] = field(default_factory=dict)
    start_time: Optional[float] = None


class DebugState:
    """Complete debug state."""

    def __init__(self):
        self.status: DebugStatus = DebugStatus.IDLE
        self.stop_reason: StopReason = StopReason.UNKNOWN
        self.session_info: DebugSessionInfo = DebugSessionInfo()
        self.current_thread_id: Optional[int] = None
        self.current_frame_id: Optional[int] = None
        self.current_location: Optional[SourceLocation] = None
        self.threads: List[Thread] = []
        self.stack_frames: List[StackFrame] = []
        self.scopes: List[Scope] = []
        self.variables: Dict[int, List[Variable]] = {}
        self.breakpoints: Dict[str, List[Breakpoint]] = {}
        self.function_breakpoints: List[Dict] = []
        self.exception_info: Optional[Dict[str, Any]] = None
        self.output: List[Dict[str, Any]] = []
        self._on_change_callbacks: List = []

    def reset_runtime(self):
        """Reset runtime state while preserving user breakpoints."""
        self.status = DebugStatus.IDLE
        self.stop_reason = StopReason.UNKNOWN
        self.session_info = DebugSessionInfo()
        self.current_thread_id = None
        self.current_frame_id = None
        self.current_location = None
        self.threads = []
        self.stack_frames = []
        self.scopes = []
        self.variables = {}
        self.exception_info = None
        self.output = []
        self._notify_change()

    def reset(self):
        """Reset all state, including breakpoints."""
        self.reset_runtime()
        self.breakpoints = {}
        self.function_breakpoints = []
        self._notify_change()

    def reset_all(self):
        """Explicit full reset alias."""
        self.reset()

    def update_from_event(self, event: str, body: Dict[str, Any]):
        if event == "stopped":
            self._handle_stopped_event(body)
        elif event == "continued":
            self._handle_continued_event(body)
        elif event == "terminated":
            self._handle_terminated_event(body)
        elif event == "exited":
            self._handle_exited_event(body)
        elif event == "output":
            self._handle_output_event(body)
        elif event == "breakpoint":
            self._handle_breakpoint_event(body)
        elif event == "thread":
            self._handle_thread_event(body)

        self._notify_change()

    def _handle_stopped_event(self, body: Dict[str, Any]):
        self.status = DebugStatus.STOPPED
        reason = body.get("reason", "unknown")
        reason_map = {
            "breakpoint": StopReason.BREAKPOINT,
            "step": StopReason.STEP,
            "exception": StopReason.EXCEPTION,
            "pause": StopReason.PAUSE,
            "entry": StopReason.ENTRY,
            "goto": StopReason.GOTO,
            "function breakpoint": StopReason.FUNCTION_BREAKPOINT,
            "data breakpoint": StopReason.DATA_BREAKPOINT,
            "instruction breakpoint": StopReason.INSTRUCTION_BREAKPOINT,
        }
        self.stop_reason = reason_map.get(reason, StopReason.UNKNOWN)
        self.current_thread_id = body.get("threadId")
        if self.current_thread_id is None and len(self.threads) == 1:
            self.current_thread_id = self.threads[0].id
        if reason == "exception":
            self.exception_info = body.get("description", {})
        logger.info(f"Stopped: reason={reason}, thread={self.current_thread_id}")

    def _handle_continued_event(self, body: Dict[str, Any]):
        self.status = DebugStatus.RUNNING
        self.stack_frames = []
        self.scopes = []
        self.variables = {}
        logger.debug("Execution continued")

    def _handle_terminated_event(self, body: Dict[str, Any]):
        self.status = DebugStatus.TERMINATED
        logger.info("Debug session terminated")

    def _handle_exited_event(self, body: Dict[str, Any]):
        self.status = DebugStatus.TERMINATED
        logger.info(f"Program exited with code: {body.get('exitCode', 0)}")

    def _handle_output_event(self, body: Dict[str, Any]):
        self.output.append(
            {
                "category": body.get("category", "console"),
                "output": body.get("output", ""),
                "timestamp": datetime.now().isoformat(),
            }
        )
        if len(self.output) > 1000:
            self.output = self.output[-500:]

    def _handle_breakpoint_event(self, body: Dict[str, Any]):
        reason = body.get("reason", "")
        bp = body.get("breakpoint", {})
        if reason == "changed" and bp.get("id"):
            for path, bps in self.breakpoints.items():
                for i, existing in enumerate(bps):
                    if existing.id == bp.get("id"):
                        self.breakpoints[path][i] = Breakpoint.from_dap(bp, path)
                        break

    def _handle_thread_event(self, body: Dict[str, Any]):
        reason = body.get("reason", "")
        thread_info = body.get("thread", {})
        if reason == "started":
            new_thread = Thread.from_dap(thread_info)
            if not any(t.id == new_thread.id for t in self.threads):
                self.threads.append(new_thread)
        elif reason == "exited":
            thread_id = thread_info.get("id")
            self.threads = [t for t in self.threads if t.id != thread_id]

    def update_threads(self, threads: List[Dict[str, Any]]):
        self.threads = [Thread.from_dap(t) for t in threads]
        self._notify_change()

    def update_stack_frames(self, frames: List[Dict[str, Any]]):
        self.stack_frames = [StackFrame.from_dap(f) for f in frames]
        if frames:
            top_frame = self.stack_frames[0]
            self.current_frame_id = top_frame.id
            if top_frame.source:
                self.current_location = top_frame.source
        self._notify_change()

    def update_scopes(self, scopes: List[Dict[str, Any]]):
        self.scopes = [Scope.from_dap(s) for s in scopes]
        self._notify_change()

    def update_variables(self, variables_reference: int, variables: List[Dict[str, Any]]):
        self.variables[variables_reference] = [Variable.from_dap(v) for v in variables]
        self._notify_change()

    def update_breakpoints(self, source_path: str, breakpoints: List[Dict[str, Any]]):
        self.breakpoints[source_path] = [
            Breakpoint.from_dap(bp, source_path) for bp in breakpoints
        ]
        self._notify_change()

    def clear_breakpoints(self, source_path: str):
        self.breakpoints.pop(source_path, None)
        self._notify_change()

    def get_current_file(self) -> Optional[str]:
        return self.current_location.path if self.current_location else None

    def get_current_line(self) -> int:
        return self.current_location.line if self.current_location else 0

    def get_top_frame(self) -> Optional[StackFrame]:
        return self.stack_frames[0] if self.stack_frames else None

    def get_frame(self, frame_id: int) -> Optional[StackFrame]:
        for frame in self.stack_frames:
            if frame.id == frame_id:
                return frame
        return None

    def get_thread(self, thread_id: int) -> Optional[Thread]:
        for thread in self.threads:
            if thread.id == thread_id:
                return thread
        return None

    def get_local_variables(self) -> List[Variable]:
        for scope in self.scopes:
            if scope.name in ("Locals", "Local"):
                return self.variables.get(scope.variables_reference, [])
        return []

    def get_all_breakpoints(self) -> List[Breakpoint]:
        result = []
        for bps in self.breakpoints.values():
            result.extend(bps)
        return result

    def get_file_breakpoints(self, path: str) -> List[Breakpoint]:
        return self.breakpoints.get(path, [])

    def get_output(self, category: Optional[str] = None, limit: int = 100) -> List[Dict]:
        output = self.output
        if category:
            output = [o for o in output if o.get("category") == category]
        return output[-limit:]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "stopReason": self.stop_reason.value,
            "program": self.session_info.program,
            "currentLocation": self.current_location.to_dict() if self.current_location else None,
            "currentThreadId": self.current_thread_id,
            "currentFrameId": self.current_frame_id,
            "threads": [t.to_dict() for t in self.threads],
            "stackFrames": [f.to_dict() for f in self.stack_frames],
            "scopes": [s.to_dict() for s in self.scopes],
            "breakpoints": {k: [bp.to_dict() for bp in v] for k, v in self.breakpoints.items()},
        }

    def to_summary(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "program": self.session_info.program,
            "currentFile": self.get_current_file(),
            "currentLine": self.get_current_line(),
            "threadCount": len(self.threads),
            "frameCount": len(self.stack_frames),
            "breakpointCount": sum(len(bps) for bps in self.breakpoints.values()),
        }

    def on_change(self, callback):
        self._on_change_callbacks.append(callback)

    def _notify_change(self):
        for callback in self._on_change_callbacks:
            try:
                callback(self)
            except Exception as e:
                logger.error(f"Error in change callback: {e}")

    def __repr__(self) -> str:
        return (
            f"<DebugState status={self.status.value} "
            f"thread={self.current_thread_id} "
            f"file={self.get_current_file()}:{self.get_current_line()}>"
        )

"""
State Model - 状态层

将 DAP 数据转换为统一的调试状态结构。
管理断点、调用栈、变量、线程等状态。
"""

import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)


class DebugStatus(Enum):
    """调试状态"""
    IDLE = "idle"                 # 空闲，未启动
    INITIALIZING = "initializing" # 初始化中
    LAUNCHING = "launching"       # 启动中
    RUNNING = "running"           # 运行中
    STOPPED = "stopped"           # 已停止（断点/异常等）
    PAUSED = "paused"             # 暂停
    TERMINATED = "terminated"     # 已终止
    ERROR = "error"               # 错误状态


class StopReason(Enum):
    """停止原因"""
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
    """源代码位置"""
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
    """调用栈帧"""
    id: int
    name: str
    source: Optional[SourceLocation] = None
    line: int = 0
    column: int = 0
    instruction_pointer_reference: Optional[str] = None
    module_id: Optional[str] = None
    presentation_hint: Optional[str] = None  # 'normal', 'label', 'subtle'
    
    @classmethod
    def from_dap(cls, frame: Dict[str, Any]) -> 'StackFrame':
        """从 DAP 响应创建 StackFrame"""
        source = None
        if 'source' in frame and frame['source']:
            src = frame['source']
            path = src.get('path') or src.get('name', '<unknown>')
            source = SourceLocation(
                path=path,
                line=frame.get('line', 0),
                column=frame.get('column'),
            )
        
        return cls(
            id=frame.get('id', 0),
            name=frame.get('name', '<unknown>'),
            source=source,
            line=frame.get('line', 0),
            column=frame.get('column', 0),
            instruction_pointer_reference=frame.get('instructionPointerReference'),
            module_id=frame.get('moduleId'),
            presentation_hint=frame.get('presentationHint'),
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
    """线程"""
    id: int
    name: str = ""
    
    @classmethod
    def from_dap(cls, thread: Dict[str, Any]) -> 'Thread':
        return cls(
            id=thread.get('id', 0),
            name=thread.get('name', f"Thread-{thread.get('id', 0)}"),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "name": self.name}


@dataclass
class Scope:
    """作用域"""
    name: str
    variables_reference: int
    expensive: bool = False
    source: Optional[SourceLocation] = None
    line: int = 0
    column: int = 0
    
    @classmethod
    def from_dap(cls, scope: Dict[str, Any]) -> 'Scope':
        source = None
        if 'source' in scope and scope['source']:
            src = scope['source']
            source = SourceLocation(
                path=src.get('path', ''),
                line=scope.get('line', 0),
            )
        
        return cls(
            name=scope.get('name', ''),
            variables_reference=scope.get('variablesReference', 0),
            expensive=scope.get('expensive', False),
            source=source,
            line=scope.get('line', 0),
            column=scope.get('column', 0),
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
    """变量"""
    name: str
    value: str
    type: Optional[str] = None
    variables_reference: int = 0  # > 0 表示有子变量
    evaluate_name: Optional[str] = None
    memory_reference: Optional[str] = None
    presentation_hint: Optional[Dict] = None
    
    @classmethod
    def from_dap(cls, var: Dict[str, Any]) -> 'Variable':
        return cls(
            name=var.get('name', ''),
            value=var.get('value', ''),
            type=var.get('type'),
            variables_reference=var.get('variablesReference', 0),
            evaluate_name=var.get('evaluateName'),
            memory_reference=var.get('memoryReference'),
            presentation_hint=var.get('presentationHint'),
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
        """是否有子变量"""
        return self.variables_reference > 0


@dataclass
class Breakpoint:
    """断点"""
    id: Optional[int] = None
    verified: bool = False
    source: Optional[SourceLocation] = None
    line: int = 0
    column: Optional[int] = None
    condition: Optional[str] = None
    hit_condition: Optional[str] = None
    log_message: Optional[str] = None
    message: Optional[str] = None  # 错误消息
    
    @classmethod
    def from_dap(cls, bp: Dict[str, Any], source_path: str = "") -> 'Breakpoint':
        return cls(
            id=bp.get('id'),
            verified=bp.get('verified', False),
            source=SourceLocation(path=source_path, line=bp.get('line', 0)),
            line=bp.get('line', 0) or bp.get('source', {}).get('line', 0),
            message=bp.get('message'),
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
    """调试会话信息"""
    program: str = ""
    args: List[str] = field(default_factory=list)
    cwd: Optional[str] = None
    env: Dict[str, str] = field(default_factory=dict)
    start_time: Optional[datetime] = None


class DebugState:
    """
    蟲试状态管理器
    
    管理调试会话的完整状态，包括：
    - 当前执行位置
    - 调用栈
    - 线程列表
    - 变量
    - 断点
    
    这是整个调试器的状态中心。
    """
    
    def __init__(self):
        # 状态
        self.status: DebugStatus = DebugStatus.IDLE
        self.stop_reason: StopReason = StopReason.UNKNOWN
        
        # 程序信息
        self.session_info: DebugSessionInfo = DebugSessionInfo()
        
        # 当前位置
        self.current_thread_id: int = 0
        self.current_frame_id: int = 0
        self.current_location: Optional[SourceLocation] = None
        
        # 线程和栈
        self.threads: List[Thread] = []
        self.stack_frames: List[StackFrame] = []
        
        # 作用域和变量
        self.scopes: List[Scope] = []
        self.variables: Dict[int, List[Variable]] = {}  # variables_reference -> variables
        
        # 断点
        self.breakpoints: Dict[str, List[Breakpoint]] = {}  # path -> breakpoints
        self.function_breakpoints: List[Dict] = []
        
        # 异常信息
        self.exception_info: Optional[Dict[str, Any]] = None
        
        # 输出
        self.output: List[Dict[str, Any]] = []
        
        # 状态变更回调
        self._on_change_callbacks: List = []
    
    def reset(self):
        """重置状态"""
        self.status = DebugStatus.IDLE
        self.stop_reason = StopReason.UNKNOWN
        self.session_info = DebugSessionInfo()
        self.current_thread_id = 0
        self.current_frame_id = 0
        self.current_location = None
        self.threads = []
        self.stack_frames = []
        self.scopes = []
        self.variables = {}
        self.breakpoints = {}
        self.function_breakpoints = []
        self.exception_info = None
        self.output = []
        self._notify_change()
    
    # ============ 状态更新方法 ============
    
    def update_from_event(self, event: str, body: Dict[str, Any]):
        """
        从 DAP 事件更新状态
        
        Args:
            event: 事件名称
            body: 事件体
        """
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
        """处理 stopped 事件"""
        self.status = DebugStatus.STOPPED
        reason = body.get('reason', 'unknown')
        
        # 映射停止原因
        reason_map = {
            'breakpoint': StopReason.BREAKPOINT,
            'step': StopReason.STEP,
            'exception': StopReason.EXCEPTION,
            'pause': StopReason.PAUSE,
            'entry': StopReason.ENTRY,
            'goto': StopReason.GOTO,
            'function breakpoint': StopReason.FUNCTION_BREAKPOINT,
            'data breakpoint': StopReason.DATA_BREAKPOINT,
            'instruction breakpoint': StopReason.INSTRUCTION_BREAKPOINT,
        }
        self.stop_reason = reason_map.get(reason, StopReason.UNKNOWN)
        
        # 更新当前线程
        self.current_thread_id = body.get('threadId', 0)
        
        # 异常信息
        if reason == 'exception':
            self.exception_info = body.get('description', {})
        
        logger.info(f"Stopped: reason={reason}, thread={self.current_thread_id}")
    
    def _handle_continued_event(self, body: Dict[str, Any]):
        """处理 continued 事件"""
        self.status = DebugStatus.RUNNING
        self.stack_frames = []
        self.scopes = []
        self.variables = {}
        logger.debug("Execution continued")
    
    def _handle_terminated_event(self, body: Dict[str, Any]):
        """处理 terminated 事件"""
        self.status = DebugStatus.TERMINATED
        logger.info("Debug session terminated")
    
    def _handle_exited_event(self, body: Dict[str, Any]):
        """处理 exited 事件"""
        self.status = DebugStatus.TERMINATED
        exit_code = body.get('exitCode', 0)
        logger.info(f"Program exited with code: {exit_code}")
    
    def _handle_output_event(self, body: Dict[str, Any]):
        """处理 output 事件"""
        output_entry = {
            "category": body.get('category', 'console'),
            "output": body.get('output', ''),
            "timestamp": datetime.now().isoformat(),
        }
        self.output.append(output_entry)
        
        # 保持输出在合理范围内
        if len(self.output) > 1000:
            self.output = self.output[-500:]
    
    def _handle_breakpoint_event(self, body: Dict[str, Any]):
        """处理 breakpoint 事件"""
        reason = body.get('reason', '')
        bp = body.get('breakpoint', {})
        
        if reason == 'changed' and bp.get('id'):
            # 更新断点
            for path, bps in self.breakpoints.items():
                for i, existing in enumerate(bps):
                    if existing.id == bp.get('id'):
                        self.breakpoints[path][i] = Breakpoint.from_dap(bp, path)
                        break
    
    def _handle_thread_event(self, body: Dict[str, Any]):
        """处理 thread 事件"""
        reason = body.get('reason', '')
        thread_info = body.get('thread', {})
        
        if reason == 'started':
            new_thread = Thread.from_dap(thread_info)
            if not any(t.id == new_thread.id for t in self.threads):
                self.threads.append(new_thread)
        elif reason == 'exited':
            thread_id = thread_info.get('id')
            self.threads = [t for t in self.threads if t.id != thread_id]
    
    # ============ 响应处理方法 ============
    
    def update_threads(self, threads: List[Dict[str, Any]]):
        """更新线程列表"""
        self.threads = [Thread.from_dap(t) for t in threads]
        self._notify_change()
    
    def update_stack_frames(self, frames: List[Dict[str, Any]]):
        """更新调用栈"""
        self.stack_frames = [StackFrame.from_dap(f) for f in frames]
        
        # 更新当前位置
        if frames:
            top_frame = self.stack_frames[0]
            self.current_frame_id = top_frame.id
            if top_frame.source:
                self.current_location = top_frame.source
        
        self._notify_change()
    
    def update_scopes(self, scopes: List[Dict[str, Any]]):
        """更新作用域"""
        self.scopes = [Scope.from_dap(s) for s in scopes]
        self._notify_change()
    
    def update_variables(self, variables_reference: int, variables: List[Dict[str, Any]]):
        """更新变量"""
        self.variables[variables_reference] = [Variable.from_dap(v) for v in variables]
        self._notify_change()
    
    def update_breakpoints(self, source_path: str, breakpoints: List[Dict[str, Any]]):
        """更新断点"""
        self.breakpoints[source_path] = [
            Breakpoint.from_dap(bp, source_path) for bp in breakpoints
        ]
        self._notify_change()
    
    def clear_breakpoints(self, source_path: str):
        """清除指定文件的断点"""
        self.breakpoints.pop(source_path, None)
        self._notify_change()
    
    # ============ 查询方法 ============
    
    def get_current_file(self) -> Optional[str]:
        """获取当前文件路径"""
        if self.current_location:
            return self.current_location.path
        return None
    
    def get_current_line(self) -> int:
        """获取当前行号"""
        if self.current_location:
            return self.current_location.line
        return 0
    
    def get_top_frame(self) -> Optional[StackFrame]:
        """获取栈顶帧"""
        if self.stack_frames:
            return self.stack_frames[0]
        return None
    
    def get_frame(self, frame_id: int) -> Optional[StackFrame]:
        """根据 ID 获取栈帧"""
        for frame in self.stack_frames:
            if frame.id == frame_id:
                return frame
        return None
    
    def get_thread(self, thread_id: int) -> Optional[Thread]:
        """根据 ID 获取线程"""
        for thread in self.threads:
            if thread.id == thread_id:
                return thread
        return None
    
    def get_local_variables(self) -> List[Variable]:
        """获取局部变量"""
        for scope in self.scopes:
            if scope.name == 'Locals' or scope.name == 'Local':
                return self.variables.get(scope.variables_reference, [])
        return []
    
    def get_all_breakpoints(self) -> List[Breakpoint]:
        """获取所有断点"""
        result = []
        for bps in self.breakpoints.values():
            result.extend(bps)
        return result
    
    def get_file_breakpoints(self, path: str) -> List[Breakpoint]:
        """获取指定文件的断点"""
        return self.breakpoints.get(path, [])
    
    def get_output(self, category: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """获取输出"""
        output = self.output
        if category:
            output = [o for o in output if o.get('category') == category]
        return output[-limit:]
    
    # ============ 序列化方法 ============
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于 JSON 序列化）"""
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
            "breakpoints": {k: [bp.to_dict() for bp in v] 
                          for k, v in self.breakpoints.items()},
        }
    
    def to_summary(self) -> Dict[str, Any]:
        """转换为摘要（用于轻量级状态查询）"""
        return {
            "status": self.status.value,
            "program": self.session_info.program,
            "currentFile": self.get_current_file(),
            "currentLine": self.get_current_line(),
            "threadCount": len(self.threads),
            "frameCount": len(self.stack_frames),
            "breakpointCount": sum(len(bps) for bps in self.breakpoints.values()),
        }
    
    # ============ 回调注册 ============
    
    def on_change(self, callback):
        """注册状态变更回调"""
        self._on_change_callbacks.append(callback)
    
    def _notify_change(self):
        """通知状态变更"""
        for callback in self._on_change_callbacks:
            try:
                callback(self)
            except Exception as e:
                logger.error(f"Error in change callback: {e}")
    
    def __repr__(self) -> str:
        return (f"<DebugState status={self.status.value} "
                f"thread={self.current_thread_id} "
                f"file={self.get_current_file()}:{self.get_current_line()}>")

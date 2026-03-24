"""
Controller - 调度核心

这是 Magic Debug 的"灵魂"，负责协调各个组件。
将 Vim / AI 的命令转换为 DAP 请求，管理调试流程。
"""

import logging
import threading
import time
from typing import Optional, Dict, Any, List, Callable
from pathlib import Path
from dataclasses import dataclass, field

from .session import DebugSession
from .dap import DAPClient, DAPError
from .state import DebugState, DebugStatus, StopReason

logger = logging.getLogger(__name__)


@dataclass
class DebugConfig:
    """调试配置"""
    program: str
    args: List[str] = field(default_factory=list)
    cwd: Optional[str] = None
    env: Dict[str, str] = field(default_factory=dict)
    stop_on_entry: bool = False
    source_maps: Dict[str, str] = field(default_factory=dict)
    pre_launch_task: Optional[str] = None


class DebugController:
    """
    调试控制器
    
    协调 DAP 客户端和状态管理，提供统一的调试控制接口。
    这是 Vim 插件和 AI 接口与调试器交互的主要入口。
    
    职责：
    1. 管理调试生命周期（启动、停止、重启）
    2. 处理调试命令（继续、单步、断点等）
    3. 协调状态更新
    4. 提供事件通知机制
    """
    
    def __init__(self, dap: DAPClient, state: DebugState):
        """
        初始化调试控制器
        
        Args:
            dap: DAP 客户端实例
            state: 调试状态实例
        """
        self.dap = dap
        self.state = state
        
        # 配置
        self._config: Optional[DebugConfig] = None
        
        # 事件回调
        self._event_callbacks: Dict[str, List[Callable]] = {
            "started": [],
            "stopped": [],
            "continued": [],
            "terminated": [],
            "breakpoint_changed": [],
            "error": [],
            "state_changed": [],
        }
        
        # 初始化状态
        self._initialized = False
        self._launching = False
        
        # 注册 DAP 事件处理器
        self._register_dap_handlers()
        
        # 注册状态变更监听
        self.state.on_change(self._on_state_change)
    
    def _register_dap_handlers(self):
        """注册 DAP 事件处理器"""
        self.dap.on_event("stopped", self._on_stopped)
        self.dap.on_event("continued", self._on_continued)
        self.dap.on_event("terminated", self._on_terminated)
        self.dap.on_event("exited", self._on_exited)
        self.dap.on_event("output", self._on_output)
        self.dap.on_event("breakpoint", self._on_breakpoint_event)
        self.dap.on_event("thread", self._on_thread_event)
        self.dap.on_event("initialized", self._on_initialized)
    
    # ============ 生命周期管理 ============
    
    def start(self, config: DebugConfig) -> bool:
        """
        启动调试会话
        
        Args:
            config: 调试配置
        
        Returns:
            bool: 启动是否成功
        """
        if self._launching:
            logger.warning("Already launching a debug session")
            return False
        
        self._launching = True
        self._config = config
        
        try:
            logger.info(f"Starting debug session for: {config.program}")
            
            # 重置状态
            self.state.reset()
            self.state.status = DebugStatus.INITIALIZING
            self.state.session_info.program = config.program
            self.state.session_info.args = config.args
            self.state.session_info.cwd = config.cwd
            self.state.session_info.env = config.env
            self.state.session_info.start_time = time.time()
            
            # 启动 DAP 读取器
            self.dap.start_reader()
            
            # 1. 发送 initialize 请求
            response = self.dap.initialize()
            if not response or not response.get('success'):
                error_msg = response.get('message', 'Unknown error') if response else 'No response'
                logger.error(f"Initialize failed: {error_msg}")
                self._emit("error", {"phase": "initialize", "message": error_msg})
                return False
            
            self._initialized = True
            logger.debug("DAP initialized")
            
            # 2. 发送 launch 请求
            self.state.status = DebugStatus.LAUNCHING
            response = self.dap.launch(
                program=config.program,
                args=config.args,
                cwd=config.cwd,
                env=config.env if config.env else None,
                stop_on_entry=config.stop_on_entry,
            )
            
            if not response or not response.get('success'):
                error_msg = response.get('message', 'Unknown error') if response else 'No response'
                logger.error(f"Launch failed: {error_msg}")
                self._emit("error", {"phase": "launch", "message": error_msg})
                self.state.status = DebugStatus.ERROR
                return False
            
            logger.debug("Launch request sent successfully")
            
            # 3. 发送 configurationDone
            # 注意：某些调试器需要这个请求来开始执行
            response = self.dap.configuration_done()
            if response and not response.get('success'):
                logger.warning(f"ConfigurationDone failed: {response.get('message')}")
            
            self.state.status = DebugStatus.RUNNING
            self._emit("started", {"program": config.program})
            
            logger.info(f"Debug session started for: {config.program}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start debug session: {e}")
            self.state.status = DebugStatus.ERROR
            self._emit("error", {"phase": "start", "message": str(e)})
            return False
        finally:
            self._launching = False
    
    def attach(self, pid: int, **kwargs) -> bool:
        """
        附加到已运行的进程
        
        Args:
            pid: 进程 ID
            **kwargs: 附加参数
        
        Returns:
            bool: 是否成功
        """
        try:
            logger.info(f"Attaching to process: {pid}")
            
            self.state.reset()
            self.state.status = DebugStatus.INITIALIZING
            
            self.dap.start_reader()
            
            # 初始化
            response = self.dap.initialize()
            if not response or not response.get('success'):
                return False
            
            self._initialized = True
            
            # 附加
            response = self.dap.attach(pid=pid, **kwargs)
            if not response or not response.get('success'):
                return False
            
            self.state.status = DebugStatus.STOPPED
            self._emit("started", {"pid": pid})
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to attach: {e}")
            return False
    
    def stop(self, terminate_debuggee: bool = True) -> bool:
        """
        停止调试会话
        
        Args:
            terminate_debuggee: 是否终止被调试进程
        
        Returns:
            bool: 是否成功
        """
        try:
            logger.info("Stopping debug session")
            
            # 发送 disconnect 请求
            response = self.dap.disconnect(terminate_debuggee=terminate_debuggee)
            
            self.state.status = DebugStatus.TERMINATED
            self._initialized = False
            self._emit("terminated", {})
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to stop: {e}")
            return False
    
    def restart(self) -> bool:
        """
        重启调试会话
        
        Returns:
            bool: 是否成功
        """
        if not self._config:
            logger.warning("No config to restart")
            return False
        
        logger.info("Restarting debug session")
        self.stop(terminate_debuggee=True)
        time.sleep(0.5)  # 等待清理
        return self.start(self._config)
    
    # ============ 执行控制 ============
    
    def continue_(self) -> bool:
        """
        继续执行
        
        Returns:
            bool: 是否成功
        """
        if not self._can_control():
            return False
        
        response = self.dap.continue_(self.state.current_thread_id)
        if response and response.get('success'):
            self.state.status = DebugStatus.RUNNING
            logger.debug("Execution continued")
            return True
        return False
    
    def pause(self) -> bool:
        """
        暂停执行
        
        Returns:
            bool: 是否成功
        """
        if not self._can_control():
            return False
        
        response = self.dap.pause(self.state.current_thread_id)
        return response and response.get('success', False)
    
    def step_over(self) -> bool:
        """
        单步跳过 (next)
        
        Returns:
            bool: 是否成功
        """
        if not self._can_control():
            return False
        
        response = self.dap.step_over(self.state.current_thread_id)
        if response and response.get('success'):
            self.state.status = DebugStatus.RUNNING
            logger.debug("Step over")
            return True
        return False
    
    def step_into(self) -> bool:
        """
        单步进入 (stepIn)
        
        Returns:
            bool: 是否成功
        """
        if not self._can_control():
            return False
        
        response = self.dap.step_into(self.state.current_thread_id)
        if response and response.get('success'):
            self.state.status = DebugStatus.RUNNING
            logger.debug("Step into")
            return True
        return False
    
    def step_out(self) -> bool:
        """
        单步跳出 (stepOut)
        
        Returns:
            bool: 是否成功
        """
        if not self._can_control():
            return False
        
        response = self.dap.step_out(self.state.current_thread_id)
        if response and response.get('success'):
            self.state.status = DebugStatus.RUNNING
            logger.debug("Step out")
            return True
        return False
    
    def _can_control(self) -> bool:
        """检查是否可以执行控制命令"""
        if not self._initialized:
            logger.warning("Debug session not initialized")
            return False
        if self.state.status != DebugStatus.STOPPED:
            logger.warning(f"Cannot control in status: {self.state.status.value}")
            return False
        return True
    
    # ============ 断点管理 ============
    
    def set_breakpoint(self, file_path: str, line: int,
                       condition: Optional[str] = None,
                       hit_condition: Optional[str] = None,
                       log_message: Optional[str] = None) -> bool:
        """
        设置断点
        
        Args:
            file_path: 文件路径
            line: 行号
            condition: 条件表达式
            hit_condition: 命中条件
            log_message: 日志消息
        
        Returns:
            bool: 是否成功
        """
        if not self._initialized:
            logger.warning("Debug session not initialized")
            return False
        
        # 构造断点
        bp = {"line": line}
        if condition:
            bp["condition"] = condition
        if hit_condition:
            bp["hitCondition"] = hit_condition
        if log_message:
            bp["logMessage"] = log_message
        
        # 获取该文件已有的断点
        existing = self.state.get_file_breakpoints(file_path)
        breakpoints = [{"line": b.line} for b in existing if b.line != line]
        breakpoints.append(bp)
        
        # 发送请求
        response = self.dap.set_breakpoints(
            source={"path": file_path},
            breakpoints=breakpoints,
        )
        
        if response and response.get('success'):
            # 更新状态
            body = response.get('body', {})
            self.state.update_breakpoints(file_path, body.get('breakpoints', []))
            logger.debug(f"Breakpoint set: {file_path}:{line}")
            self._emit("breakpoint_changed", {"file": file_path, "action": "set"})
            return True
        
        return False
    
    def remove_breakpoint(self, file_path: str, line: int) -> bool:
        """
        移除断点
        
        Args:
            file_path: 文件路径
            line: 行号
        
        Returns:
            bool: 是否成功
        """
        if not self._initialized:
            return False
        
        # 获取该文件已有的断点（排除要删除的）
        existing = self.state.get_file_breakpoints(file_path)
        breakpoints = [{"line": b.line} for b in existing if b.line != line]
        
        if not breakpoints:
            # 清除该文件的所有断点
            self.state.clear_breakpoints(file_path)
            response = self.dap.set_breakpoints(
                source={"path": file_path},
                breakpoints=[],
            )
        else:
            response = self.dap.set_breakpoints(
                source={"path": file_path},
                breakpoints=breakpoints,
            )
        
        if response and response.get('success'):
            body = response.get('body', {})
            self.state.update_breakpoints(file_path, body.get('breakpoints', []))
            logger.debug(f"Breakpoint removed: {file_path}:{line}")
            self._emit("breakpoint_changed", {"file": file_path, "action": "remove"})
            return True
        
        return False
    
    def toggle_breakpoint(self, file_path: str, line: int) -> bool:
        """
        切换断点状态
        
        Args:
            file_path: 文件路径
            line: 行号
        
        Returns:
            bool: 是否成功
        """
        existing = self.state.get_file_breakpoints(file_path)
        has_bp = any(b.line == line for b in existing)
        
        if has_bp:
            return self.remove_breakpoint(file_path, line)
        else:
            return self.set_breakpoint(file_path, line)
    
    def clear_all_breakpoints(self) -> bool:
        """清除所有断点"""
        if not self._initialized:
            return False
        
        for file_path in list(self.state.breakpoints.keys()):
            response = self.dap.set_breakpoints(
                source={"path": file_path},
                breakpoints=[],
            )
            if response and response.get('success'):
                self.state.clear_breakpoints(file_path)
        
        self._emit("breakpoint_changed", {"action": "clear_all"})
        return True
    
    # ============ 状态查询 ============
    
    def refresh_state(self):
        """刷新调试状态"""
        if not self._initialized or self.state.status != DebugStatus.STOPPED:
            return
        
        # 刷新线程
        self._refresh_threads()
        
        # 刷新调用栈
        if self.state.current_thread_id:
            self._refresh_stack_frames()
    
    def _refresh_threads(self):
        """刷新线程列表"""
        response = self.dap.threads()
        if response and response.get('success'):
            body = response.get('body', {})
            self.state.update_threads(body.get('threads', []))
    
    def _refresh_stack_frames(self):
        """刷新调用栈"""
        response = self.dap.stack_trace(self.state.current_thread_id)
        if response and response.get('success'):
            body = response.get('body', {})
            self.state.update_stack_frames(body.get('stackFrames', []))
            
            # 刷新作用域
            if self.state.stack_frames:
                self._refresh_scopes(self.state.stack_frames[0].id)
    
    def _refresh_scopes(self, frame_id: int):
        """刷新作用域"""
        response = self.dap.scopes(frame_id)
        if response and response.get('success'):
            body = response.get('body', {})
            self.state.update_scopes(body.get('scopes', []))
            
            # 刷新变量
            for scope in self.state.scopes:
                self._refresh_variables(scope.variables_reference)
    
    def _refresh_variables(self, variables_reference: int):
        """刷新变量"""
        response = self.dap.variables(variables_reference)
        if response and response.get('success'):
            body = response.get('body', {})
            self.state.update_variables(
                variables_reference,
                body.get('variables', [])
            )
    
    def get_variables(self, variables_reference: int) -> List[Dict]:
        """
        获取变量
        
        Args:
            variables_reference: 变量引用 ID
        
        Returns:
            变量列表
        """
        # 如果已缓存，直接返回
        if variables_reference in self.state.variables:
            return [v.to_dict() for v in self.state.variables[variables_reference]]
        
        # 否则请求
        response = self.dap.variables(variables_reference)
        if response and response.get('success'):
            body = response.get('body', {})
            self.state.update_variables(
                variables_reference,
                body.get('variables', [])
            )
            return body.get('variables', [])
        
        return []
    
    def evaluate(self, expression: str, frame_id: Optional[int] = None,
                 context: str = "repl") -> Optional[Dict]:
        """
        求值表达式
        
        Args:
            expression: 表达式
            frame_id: 栈帧 ID
            context: 上下文
        
        Returns:
            求值结果
        """
        if not self._initialized:
            return None
        
        if frame_id is None:
            frame_id = self.state.current_frame_id
        
        response = self.dap.evaluate(expression, frame_id, context)
        if response and response.get('success'):
            return response.get('body', {})
        
        return None
    
    def set_variable(self, variables_reference: int, name: str, 
                     value: str) -> Optional[Dict]:
        """
        设置变量值
        
        Args:
            variables_reference: 变量引用
            name: 变量名
            value: 新值
        
        Returns:
            结果
        """
        if not self._initialized:
            return None
        
        response = self.dap.set_variable(variables_reference, name, value)
        if response and response.get('success'):
            # 刷新变量
            self._refresh_variables(variables_reference)
            return response.get('body', {})
        
        return None
    
    # ============ DAP 事件处理 ============
    
    def _on_initialized(self, body: Dict):
        """处理 initialized 事件"""
        logger.debug("Received initialized event")
    
    def _on_stopped(self, body: Dict):
        """处理 stopped 事件"""
        self.state.update_from_event("stopped", body)
        
        # 刷新状态
        self._refresh_threads()
        if self.state.current_thread_id:
            self._refresh_stack_frames()
        
        self._emit("stopped", {
            "reason": body.get('reason', 'unknown'),
            "threadId": body.get('threadId'),
            "file": self.state.get_current_file(),
            "line": self.state.get_current_line(),
        })
    
    def _on_continued(self, body: Dict):
        """处理 continued 事件"""
        self.state.update_from_event("continued", body)
        self._emit("continued", {})
    
    def _on_terminated(self, body: Dict):
        """处理 terminated 事件"""
        self.state.update_from_event("terminated", body)
        self._initialized = False
        self._emit("terminated", {})
    
    def _on_exited(self, body: Dict):
        """处理 exited 事件"""
        self.state.update_from_event("exited", body)
        self._emit("terminated", {"exitCode": body.get('exitCode')})
    
    def _on_output(self, body: Dict):
        """处理 output 事件"""
        self.state.update_from_event("output", body)
    
    def _on_breakpoint_event(self, body: Dict):
        """处理 breakpoint 事件"""
        self.state.update_from_event("breakpoint", body)
        self._emit("breakpoint_changed", body)
    
    def _on_thread_event(self, body: Dict):
        """处理 thread 事件"""
        self.state.update_from_event("thread", body)
    
    def _on_state_change(self, state: DebugState):
        """处理状态变更"""
        self._emit("state_changed", state.to_summary())
    
    # ============ 事件系统 ============
    
    def on(self, event: str, callback: Callable):
        """
        注册事件回调
        
        Args:
            event: 事件名称
            callback: 回调函数
        """
        if event in self._event_callbacks:
            self._event_callbacks[event].append(callback)
    
    def off(self, event: str, callback: Callable):
        """
        移除事件回调
        
        Args:
            event: 事件名称
            callback: 回调函数
        """
        if event in self._event_callbacks:
            self._event_callbacks[event].remove(callback)
    
    def _emit(self, event: str, data: Any):
        """
        触发事件
        
        Args:
            event: 事件名称
            data: 事件数据
        """
        if event in self._event_callbacks:
            for callback in self._event_callbacks[event]:
                try:
                    callback(data)
                except Exception as e:
                    logger.error(f"Error in event callback: {e}")
    
    # ============ 便捷方法 ============
    
    def get_status(self) -> Dict[str, Any]:
        """获取当前状态摘要"""
        return self.state.to_summary()
    
    def get_full_state(self) -> Dict[str, Any]:
        """获取完整状态"""
        return self.state.to_dict()
    
    def is_debugging(self) -> bool:
        """是否正在调试"""
        return self._initialized and self.state.status not in [
            DebugStatus.IDLE,
            DebugStatus.TERMINATED,
            DebugStatus.ERROR,
        ]
    
    def __repr__(self):
        return f"<DebugController status={self.state.status.value} initialized={self._initialized}>"

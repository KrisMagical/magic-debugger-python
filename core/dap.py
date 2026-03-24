"""
DAP Client - Debug Adapter Protocol 通信层

实现 DAP 协议的客户端，处理 Content-Length 头 + JSON 消息格式。
DAP 是一个流式协议，需要正确处理消息边界。
"""

import json
import logging
import threading
import queue
from typing import Optional, Dict, Any, Callable, Union
from dataclasses import dataclass, field
from enum import Enum
from .session import DebugSession

logger = logging.getLogger(__name__)


class MessageType(Enum):
    """DAP 消息类型"""
    REQUEST = "request"
    RESPONSE = "response"
    EVENT = "event"


@dataclass
class DAPMessage:
    """DAP 消息基类"""
    type: str
    raw: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return self.raw


@dataclass
class DAPRequest(DAPMessage):
    """DAP 请求消息"""
    seq: int = 0
    command: str = ""
    arguments: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DAPResponse(DAPMessage):
    """DAP 响应消息"""
    request_seq: int = 0
    success: bool = True
    command: str = ""
    message: Optional[str] = None
    body: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DAPEvent(DAPMessage):
    """DAP 事件消息"""
    event: str = ""
    body: Dict[str, Any] = field(default_factory=dict)


class DAPError(Exception):
    """DAP 协议错误"""
    pass


class DAPClient:
    """
    DAP 协议客户端
    
    实现 Debug Adapter Protocol 的核心通信功能。
    支持发送请求、接收响应和事件。
    
    DAP 消息格式:
        Content-Length: <length>\r\n
        \r\n
        <json payload>
    """
    
    # DAP 初始化参数
    DEFAULT_INIT_PARAMS = {
        "clientID": "magic-debug",
        "clientName": "Magic Debug",
        "adapterID": "lldb-dap",
        "locale": "en-us",
        "linesStartAt1": True,
        "columnsStartAt1": True,
        "pathFormat": "path",
        "supportsVariableType": True,
        "supportsVariablePaging": True,
        "supportsRunInTerminalRequest": True,
        "supportsMemoryReferences": True,
        "supportsProgressReporting": True,
        "supportsInvalidatedEvent": True,
        "supportsMemoryEvent": True,
    }
    
    def __init__(self, session: DebugSession):
        """
        初始化 DAP 客户端
        
        Args:
            session: 调试会话对象
        """
        self.session = session
        self.seq = 1  # 请求序列号
        self._lock = threading.Lock()
        
        # 响应等待机制
        self._pending_requests: Dict[int, queue.Queue] = {}
        self._response_timeout = 30.0
        
        # 事件处理器
        self._event_handlers: Dict[str, Callable] = {}
        
        # 消息处理器
        self._message_callback: Optional[Callable] = None
        
        # 消息队列
        self._message_queue: queue.Queue = queue.Queue()
        
        # 事件循环线程
        self._reader_thread: Optional[threading.Thread] = None
        self._running = False
        
        # 初始化状态
        self._initialized = False
        self._capabilities: Dict[str, Any] = {}
    
    def start_reader(self):
        """启动消息读取线程"""
        if self._reader_thread and self._reader_thread.is_alive():
            return
        
        self._running = True
        self._reader_thread = threading.Thread(
            target=self._event_loop,
            daemon=True,
            name="DAP-EventLoop"
        )
        self._reader_thread.start()
        logger.info("DAP reader thread started")
    
    def stop_reader(self):
        """停止消息读取线程"""
        self._running = False
    
    def _event_loop(self):
        """
        事件循环 - 核心读取逻辑
        
        持续从 session 读取 DAP 消息并分发处理。
        这是理解 DAP 协议的关键：它是一个流式协议。
        """
        logger.info("DAP event loop started")
        
        while self._running and self.session.is_alive():
            try:
                msg = self.read_message(timeout=1.0)
                if msg:
                    self._dispatch_message(msg)
            except Exception as e:
                if self._running:
                    logger.error(f"Error in event loop: {e}")
        
        logger.info("DAP event loop stopped")
    
    def read_message(self, timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """
        读取一条完整的 DAP 消息
        
        DAP 消息格式:
            Content-Length: <length>\r\n
            \r\n
            <json body>
        
        Args:
            timeout: 读取超时时间
        
        Returns:
            解析后的 JSON 消息字典，超时返回 None
        """
        # 1. 读取 header
        headers = {}
        while True:
            line = self.session.readline(timeout=timeout)
            if line is None:
                return None
            
            line = line.strip()
            if not line:  # 空行表示 header 结束
                break
            
            # 解析 header
            if ':' in line:
                key, value = line.split(':', 1)
                headers[key.strip()] = value.strip()
        
        # 2. 获取 Content-Length
        content_length_str = headers.get('Content-Length')
        if not content_length_str:
            raise DAPError("Missing Content-Length header")
        
        try:
            content_length = int(content_length_str)
        except ValueError:
            raise DAPError(f"Invalid Content-Length: {content_length_str}")
        
        # 3. 读取 body
        body = ""
        remaining = content_length
        while remaining > 0:
            chunk = self.session.read(remaining, timeout=timeout)
            if chunk is None:
                raise DAPError("Incomplete message body")
            body += chunk
            remaining -= len(chunk)
        
        # 4. 解析 JSON
        try:
            return json.loads(body)
        except json.JSONDecodeError as e:
            raise DAPError(f"Invalid JSON: {e}")
    
    def _dispatch_message(self, msg: Dict[str, Any]):
        """
        分发消息到对应的处理器
        
        Args:
            msg: 解析后的消息字典
        """
        msg_type = msg.get('type')
        
        # 放入消息队列
        self._message_queue.put(msg)
        
        # 调用消息回调
        if self._message_callback:
            try:
                self._message_callback(msg)
            except Exception as e:
                logger.error(f"Error in message callback: {e}")
        
        if msg_type == 'response':
            self._handle_response(msg)
        elif msg_type == 'event':
            self._handle_event(msg)
        elif msg_type == 'request':
            self._handle_reverse_request(msg)
        else:
            logger.warning(f"Unknown message type: {msg_type}")
    
    def _handle_response(self, msg: Dict[str, Any]):
        """处理响应消息"""
        request_seq = msg.get('request_seq')
        if request_seq in self._pending_requests:
            # 通知等待的请求
            self._pending_requests[request_seq].put(msg)
    
    def _handle_event(self, msg: Dict[str, Any]):
        """处理事件消息"""
        event = msg.get('event', '')
        
        # 调用注册的事件处理器
        if event in self._event_handlers:
            try:
                self._event_handlers[event](msg)
            except Exception as e:
                logger.error(f"Error in event handler for '{event}': {e}")
        
        logger.debug(f"DAP Event: {event}")
    
    def _handle_reverse_request(self, msg: Dict[str, Any]):
        """处理反向请求（调试器主动发起的请求）"""
        command = msg.get('command', '')
        seq = msg.get('seq', 0)
        
        logger.debug(f"Reverse request: {command}")
        
        # 处理 runInTerminal 请求
        if command == 'runInTerminal':
            # 返回成功响应
            self.send_response(seq, command, True, body={
                "processId": None
            })
    
    def send(self, command: str, arguments: Optional[Dict[str, Any]] = None,
             wait_response: bool = True, timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """
        发送 DAP 请求
        
        Args:
            command: 命令名称
            arguments: 命令参数
            wait_response: 是否等待响应
            timeout: 响应超时时间
        
        Returns:
            响应消息（如果 wait_response=True）
        """
        with self._lock:
            seq = self.seq
            self.seq += 1
        
        # 构造请求消息
        request = {
            "seq": seq,
            "type": "request",
            "command": command,
        }
        if arguments:
            request["arguments"] = arguments
        
        # 注册等待队列
        if wait_response:
            self._pending_requests[seq] = queue.Queue()
        
        # 发送消息
        self._send_raw(request)
        logger.debug(f"Sent request: {command} (seq={seq})")
        
        # 等待响应
        if wait_response:
            try:
                actual_timeout = timeout or self._response_timeout
                response = self._pending_requests[seq].get(timeout=actual_timeout)
                return response
            except queue.Empty:
                logger.error(f"Timeout waiting for response to '{command}'")
                return None
            finally:
                del self._pending_requests[seq]
        
        return None
    
    def send_response(self, request_seq: int, command: str, success: bool,
                      message: Optional[str] = None, body: Optional[Dict] = None):
        """
        发送响应消息（用于反向请求）
        
        Args:
            request_seq: 对应请求的序列号
            command: 命令名称
            success: 是否成功
            message: 错误消息（如果失败）
            body: 响应体
        """
        response = {
            "seq": self.seq,
            "type": "response",
            "request_seq": request_seq,
            "command": command,
            "success": success,
        }
        if message:
            response["message"] = message
        if body:
            response["body"] = body
        
        self.seq += 1
        self._send_raw(response)
    
    def _send_raw(self, msg: Dict[str, Any]):
        """
        发送原始 DAP 消息
        
        Args:
            msg: 消息字典
        """
        body = json.dumps(msg, ensure_ascii=False)
        header = f"Content-Length: {len(body)}\r\n\r\n"
        self.session.write(header + body)
    
    def on_event(self, event: str, handler: Callable):
        """
        注册事件处理器
        
        Args:
            event: 事件名称
            handler: 处理函数
        """
        self._event_handlers[event] = handler
    
    def on_message(self, callback: Callable):
        """
        设置消息回调
        
        Args:
            callback: 回调函数，接收所有消息
        """
        self._message_callback = callback
    
    def get_message(self, timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """
        从消息队列获取一条消息
        
        Args:
            timeout: 超时时间
        
        Returns:
            消息字典
        """
        try:
            return self._message_queue.get(timeout=timeout)
        except queue.Empty:
            return None
    
    # ============ DAP 协议常用命令封装 ============
    
    def initialize(self, params: Optional[Dict] = None) -> Optional[Dict]:
        """
        发送 initialize 请求
        
        Args:
            params: 初始化参数，默认使用 DEFAULT_INIT_PARAMS
        
        Returns:
            响应，包含调试器能力
        """
        actual_params = self.DEFAULT_INIT_PARAMS.copy()
        if params:
            actual_params.update(params)
        
        response = self.send("initialize", actual_params)
        
        if response and response.get('success'):
            self._initialized = True
            self._capabilities = response.get('body', {})
            logger.info("DAP initialized successfully")
        
        return response
    
    def launch(self, program: str, args: Optional[list] = None,
               cwd: Optional[str] = None, env: Optional[dict] = None,
               stop_on_entry: bool = False, **kwargs) -> Optional[Dict]:
        """
        发送 launch 请求
        
        Args:
            program: 程序路径
            args: 命令行参数
            cwd: 工作目录
            env: 环境变量
            stop_on_entry: 是否在入口处停止
            **kwargs: 其他参数
        
        Returns:
            响应
        """
        arguments = {
            "program": program,
            "stopOnEntry": stop_on_entry,
        }
        if args:
            arguments["args"] = args
        if cwd:
            arguments["cwd"] = cwd
        if env:
            arguments["env"] = env
        arguments.update(kwargs)
        
        return self.send("launch", arguments)
    
    def attach(self, pid: int, **kwargs) -> Optional[Dict]:
        """
        发送 attach 请求（附加到进程）
        
        Args:
            pid: 进程 ID
            **kwargs: 其他参数
        
        Returns:
            响应
        """
        arguments = {"pid": pid}
        arguments.update(kwargs)
        return self.send("attach", arguments)
    
    def set_breakpoints(self, source: Dict, breakpoints: list,
                        source_modified: bool = False) -> Optional[Dict]:
        """
        设置断点
        
        Args:
            source: 源文件信息 {"path": "/path/to/file"}
            breakpoints: 断点列表 [{"line": 10}, {"line": 20, "condition": "x > 5"}]
            source_modified: 源文件是否已修改
        
        Returns:
            响应
        """
        arguments = {
            "source": source,
            "breakpoints": breakpoints,
            "sourceModified": source_modified,
        }
        return self.send("setBreakpoints", arguments)
    
    def set_function_breakpoints(self, breakpoints: list) -> Optional[Dict]:
        """
        设置函数断点
        
        Args:
            breakpoints: 函数断点列表 [{"name": "func_name"}]
        
        Returns:
            响应
        """
        return self.send("setFunctionBreakpoints", {"breakpoints": breakpoints})
    
    def configuration_done(self) -> Optional[Dict]:
        """
        发送 configurationDone 请求
        表示配置完成，可以开始调试
        """
        return self.send("configurationDone")
    
    def continue_(self, thread_id: int = 0) -> Optional[Dict]:
        """
        继续执行
        
        Args:
            thread_id: 线程 ID，0 表示所有线程
        """
        return self.send("continue", {"threadId": thread_id})
    
    def step_over(self, thread_id: int, single_thread: bool = False) -> Optional[Dict]:
        """
        单步跳过 (next)
        
        Args:
            thread_id: 线程 ID
            single_thread: 是否只执行当前线程
        """
        return self.send("next", {
            "threadId": thread_id,
            "singleThread": single_thread,
        })
    
    def step_into(self, thread_id: int, single_thread: bool = False,
                  target_id: Optional[int] = None) -> Optional[Dict]:
        """
        单步进入 (stepIn)
        
        Args:
            thread_id: 线程 ID
            single_thread: 是否只执行当前线程
            target_id: 目标调用栈帧 ID
        """
        args = {
            "threadId": thread_id,
            "singleThread": single_thread,
        }
        if target_id is not None:
            args["targetId"] = target_id
        return self.send("stepIn", args)
    
    def step_out(self, thread_id: int, single_thread: bool = False) -> Optional[Dict]:
        """
        单步跳出 (stepOut)
        
        Args:
            thread_id: 线程 ID
            single_thread: 是否只执行当前线程
        """
        return self.send("stepOut", {
            "threadId": thread_id,
            "singleThread": single_thread,
        })
    
    def pause(self, thread_id: int) -> Optional[Dict]:
        """
        暂停执行
        
        Args:
            thread_id: 线程 ID
        """
        return self.send("pause", {"threadId": thread_id})
    
    def disconnect(self, restart: bool = False,
                   terminate_debuggee: Optional[bool] = None) -> Optional[Dict]:
        """
        断开连接
        
        Args:
            restart: 是否重启
            terminate_debuggee: 是否终止被调试进程
        """
        args = {"restart": restart}
        if terminate_debuggee is not None:
            args["terminateDebuggee"] = terminate_debuggee
        return self.send("disconnect", args)
    
    def terminate(self, restart: bool = False) -> Optional[Dict]:
        """
        终止调试
        
        Args:
            restart: 是否重启
        """
        return self.send("terminate", {"restart": restart})
    
    def threads(self) -> Optional[Dict]:
        """获取线程列表"""
        return self.send("threads")
    
    def stack_trace(self, thread_id: int, start_frame: int = 0,
                    levels: int = 20) -> Optional[Dict]:
        """
        获取调用栈
        
        Args:
            thread_id: 线程 ID
            start_frame: 起始帧索引
            levels: 帧数量
        """
        return self.send("stackTrace", {
            "threadId": thread_id,
            "startFrame": start_frame,
            "levels": levels,
        })
    
    def scopes(self, frame_id: int) -> Optional[Dict]:
        """
        获取作用域
        
        Args:
            frame_id: 栈帧 ID
        """
        return self.send("scopes", {"frameId": frame_id})
    
    def variables(self, variables_reference: int, 
                  filter_type: Optional[str] = None,
                  start: Optional[int] = None,
                  count: Optional[int] = None) -> Optional[Dict]:
        """
        获取变量
        
        Args:
            variables_reference: 变量引用 ID
            filter_type: 过滤类型 ('indexed'|'named')
            start: 起始索引
            count: 数量
        """
        args = {"variablesReference": variables_reference}
        if filter_type:
            args["filter"] = filter_type
        if start is not None:
            args["start"] = start
        if count is not None:
            args["count"] = count
        return self.send("variables", args)
    
    def evaluate(self, expression: str, frame_id: Optional[int] = None,
                 context: str = "repl") -> Optional[Dict]:
        """
        求值表达式
        
        Args:
            expression: 表达式
            frame_id: 栈帧 ID
            context: 上下文 ('watch'|'repl'|'hover')
        """
        args = {
            "expression": expression,
            "context": context,
        }
        if frame_id is not None:
            args["frameId"] = frame_id
        return self.send("evaluate", args)
    
    def set_variable(self, variables_reference: int, name: str,
                     value: str, frame_id: Optional[int] = None) -> Optional[Dict]:
        """
        设置变量值
        
        Args:
            variables_reference: 变量引用
            name: 变量名
            value: 新值
            frame_id: 栈帧 ID
        """
        args = {
            "variablesReference": variables_reference,
            "name": name,
            "value": value,
        }
        if frame_id is not None:
            args["frameId"] = frame_id
        return self.send("setVariable", args)
    
    def source(self, source: Dict, source_reference: int) -> Optional[Dict]:
        """
        获取源代码内容
        
        Args:
            source: 源文件信息
            source_reference: 源引用 ID
        """
        return self.send("source", {
            "source": source,
            "sourceReference": source_reference,
        })
    
    def disassemble(self, memory_reference: str, instruction_count: int,
                    offset: int = 0, instruction_offset: int = 0) -> Optional[Dict]:
        """
        反汇编
        
        Args:
            memory_reference: 内存引用
            instruction_count: 指令数量
            offset: 字节偏移
            instruction_offset: 指令偏移
        """
        return self.send("disassemble", {
            "memoryReference": memory_reference,
            "instructionCount": instruction_count,
            "offset": offset,
            "instructionOffset": instruction_offset,
        })
    
    @property
    def capabilities(self) -> Dict[str, Any]:
        """获取调试器能力"""
        return self._capabilities
    
    @property
    def is_initialized(self) -> bool:
        """是否已初始化"""
        return self._initialized


def parse_dap_message(msg: Dict[str, Any]) -> Union[DAPRequest, DAPResponse, DAPEvent]:
    """
    解析 DAP 消息为对应的数据类
    
    Args:
        msg: 原始消息字典
    
    Returns:
        对应的消息数据类实例
    """
    msg_type = msg.get('type', '')
    
    if msg_type == 'request':
        return DAPRequest(
            type=msg_type,
            raw=msg,
            seq=msg.get('seq', 0),
            command=msg.get('command', ''),
            arguments=msg.get('arguments', {}),
        )
    elif msg_type == 'response':
        return DAPResponse(
            type=msg_type,
            raw=msg,
            request_seq=msg.get('request_seq', 0),
            success=msg.get('success', False),
            command=msg.get('command', ''),
            message=msg.get('message'),
            body=msg.get('body', {}),
        )
    elif msg_type == 'event':
        return DAPEvent(
            type=msg_type,
            raw=msg,
            event=msg.get('event', ''),
            body=msg.get('body', {}),
        )
    else:
        raise DAPError(f"Unknown message type: {msg_type}")

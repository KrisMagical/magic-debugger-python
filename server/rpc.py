"""
RPC Server - Vim 通信层

通过 Unix Domain Socket 提供 RPC 服务，供 Vim 插件调用。
"""

import os
import json
import socket
import stat
import threading
import logging
import queue
from typing import Optional, Dict, Any, Callable, List
from dataclasses import dataclass, field
from pathlib import Path

from server.errors import (
    exception_to_error,
    normalize_controller_result,
    normalize_error,
)

logger = logging.getLogger(__name__)


DEFAULT_RPC_HOST = "127.0.0.1"
DEFAULT_RPC_PORT = 8766
DEFAULT_RPC_SOCKET_NAME = "magic-debug.sock"


class RPCTransportError(Exception):
    """Raised when an RPC transport cannot be resolved or started."""


@dataclass
class RPCEndpoint:
    transport: str
    host: str = DEFAULT_RPC_HOST
    port: int = DEFAULT_RPC_PORT
    socket_path: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    requested_transport: str = "auto"

    def url(self) -> str:
        if self.transport == "tcp":
            return f"tcp://{self.host}:{self.port}"
        return f"unix:{self.socket_path}"


def _is_windows(platform_name: Optional[str] = None) -> bool:
    name = platform_name or os.name
    return name.lower().startswith(("win", "windows", "nt"))


def default_rpc_socket_path(env: Optional[Dict[str, str]] = None) -> str:
    env = env or os.environ
    runtime_dir = env.get("XDG_RUNTIME_DIR")
    if runtime_dir and os.path.isdir(runtime_dir) and os.access(runtime_dir, os.W_OK):
        return os.path.join(runtime_dir, DEFAULT_RPC_SOCKET_NAME)
    return os.path.join("/tmp", DEFAULT_RPC_SOCKET_NAME)


def resolve_rpc_endpoint(
    transport: str = "auto",
    host: str = DEFAULT_RPC_HOST,
    port: int = DEFAULT_RPC_PORT,
    socket_path: Optional[str] = None,
    platform_name: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
) -> RPCEndpoint:
    requested = transport or "auto"
    if requested not in {"auto", "unix", "tcp"}:
        raise RPCTransportError(f"Unsupported RPC transport: {requested}")

    if requested == "auto":
        resolved = "tcp" if _is_windows(platform_name) else "unix"
    else:
        resolved = requested

    if resolved == "unix":
        if _is_windows(platform_name) or (platform_name is None and not hasattr(socket, "AF_UNIX")):
            raise RPCTransportError("Unix socket is not supported on this platform")
        return RPCEndpoint(
            transport="unix",
            host=host,
            port=port,
            socket_path=socket_path or default_rpc_socket_path(env),
            requested_transport=requested,
        )

    return RPCEndpoint(
        transport="tcp",
        host=host or DEFAULT_RPC_HOST,
        port=int(port or DEFAULT_RPC_PORT),
        socket_path=socket_path,
        requested_transport=requested,
    )


def should_remove_stale_socket(path: str) -> bool:
    if not os.path.exists(path):
        return False
    try:
        return stat.S_ISSOCK(os.stat(path).st_mode)
    except OSError:
        return False


def encode_rpc_message(message: Dict[str, Any]) -> bytes:
    return (json.dumps(message) + "\n").encode("utf-8")


@dataclass
class RPCRequest:
    """RPC 请求"""
    id: Optional[int] = None
    method: str = ""
    params: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.params is None:
            self.params = {}


@dataclass
class RPCResponse:
    """RPC 响应"""
    id: Optional[int] = None
    result: Any = None
    error: Optional[Dict] = None
    
    def to_dict(self) -> Dict:
        d = {
            "type": "response",
            "id": self.id,
            "success": self.error is None,
        }
        if self.error:
            d["error"] = normalize_error(self.error)
        else:
            d["result"] = self.result
        return d


class RPCServer:
    """
    RPC 服务器
    
    使用 Unix Domain Socket 接收 Vim 的命令请求。
    支持 JSON-RPC 2.0 风格的消息格式。
    
    Example:
        server = RPCServer(controller)
        server.start("/tmp/magic-debug.sock")
    """
    
    def __init__(self, controller):
        """
        初始化 RPC 服务器
        
        Args:
            controller: DebugController 实例
        """
        self.controller = controller
        self.socket_path: Optional[str] = None
        self.endpoint: Optional[RPCEndpoint] = None
        self._server: Optional[socket.socket] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        
        # 客户端连接
        self._clients: List[socket.socket] = []
        self._clients_lock = threading.Lock()
        
        # 注册的方法
        self._methods: Dict[str, Callable] = {}
        self._register_default_methods()
        
        # 事件广播队列
        self._event_queue: queue.Queue = queue.Queue()
        self._broadcaster_thread: Optional[threading.Thread] = None
    
    def _register_default_methods(self):
        """注册默认的 RPC 方法"""
        # 生命周期
        self.register("start", self._method_start)
        self.register("stop", self._method_stop)
        self.register("restart", self._method_restart)
        self.register("attach", self._method_attach)
        
        # 执行控制
        self.register("continue", self._method_continue)
        self.register("pause", self._method_pause)
        self.register("stepOver", self._method_step_over)
        self.register("stepInto", self._method_step_into)
        self.register("stepOut", self._method_step_out)
        
        # 断点
        self.register("setBreakpoint", self._method_set_breakpoint)
        self.register("removeBreakpoint", self._method_remove_breakpoint)
        self.register("toggleBreakpoint", self._method_toggle_breakpoint)
        self.register("clearBreakpoints", self._method_clear_breakpoints)
        self.register("listBreakpoints", self._method_list_breakpoints)
        
        # 状态查询
        self.register("getState", self._method_get_state)
        self.register("getStatus", self._method_get_status)
        self.register("getThreads", self._method_get_threads)
        self.register("getStackFrames", self._method_get_stack_frames)
        self.register("getVariables", self._method_get_variables)
        self.register("getScopes", self._method_get_scopes)
        self.register("getOutput", self._method_get_output)
        
        # 求值
        self.register("evaluate", self._method_evaluate)
        self.register("setVariable", self._method_set_variable)
        
        # 刷新
        self.register("refresh", self._method_refresh)
        
        # 连接检查
        self.register("ping", self._method_ping)
    
    def register(self, method: str, handler: Callable):
        """
        注册 RPC 方法
        
        Args:
            method: 方法名称
            handler: 处理函数
        """
        self._methods[method] = handler
    
    # ============ 默认方法实现 ============
    
    def _method_start(self, params: Dict) -> Dict:
        """启动调试"""
        from core.controller import DebugConfig
        
        program = params.get("program")
        if not program:
            return {"success": False, "error": "Missing 'program' parameter"}
        
        config = DebugConfig(
            program=program,
            args=params.get("args", []),
            cwd=params.get("cwd"),
            env=params.get("env", {}),
            stop_on_entry=params.get("stopOnEntry", False),
        )
        
        success = self.controller.start(config)
        return {"success": success}
    
    def _method_stop(self, params: Dict) -> Dict:
        """停止调试"""
        success = self.controller.stop(
            terminate_debuggee=params.get("terminateDebuggee", True)
        )
        return {"success": success}
    
    def _method_restart(self, params: Dict) -> Dict:
        """重启调试"""
        success = self.controller.restart()
        return {"success": success}
    
    def _method_attach(self, params: Dict) -> Dict:
        """附加到进程"""
        pid = params.get("pid")
        if not pid:
            return {"success": False, "error": "Missing 'pid' parameter"}
        
        success = self.controller.attach(pid)
        return {"success": success}
    
    def _method_continue(self, params: Dict) -> Dict:
        """继续执行"""
        success = self.controller.continue_()
        return {"success": success}
    
    def _method_pause(self, params: Dict) -> Dict:
        """暂停执行"""
        success = self.controller.pause()
        return {"success": success}
    
    def _method_step_over(self, params: Dict) -> Dict:
        """单步跳过"""
        success = self.controller.step_over()
        return {"success": success}
    
    def _method_step_into(self, params: Dict) -> Dict:
        """单步进入"""
        success = self.controller.step_into()
        return {"success": success}
    
    def _method_step_out(self, params: Dict) -> Dict:
        """单步跳出"""
        success = self.controller.step_out()
        return {"success": success}
    
    def _method_set_breakpoint(self, params: Dict) -> Dict:
        """设置断点"""
        file_path = params.get("file")
        line = params.get("line")
        
        if not file_path or not line:
            return {"success": False, "error": "Missing 'file' or 'line'"}
        
        success = self.controller.set_breakpoint(
            file_path, line,
            condition=params.get("condition"),
            hit_condition=params.get("hitCondition"),
            log_message=params.get("logMessage"),
        )
        return {"success": success}
    
    def _method_remove_breakpoint(self, params: Dict) -> Dict:
        """移除断点"""
        file_path = params.get("file")
        line = params.get("line")
        
        if not file_path or not line:
            return {"success": False, "error": "Missing 'file' or 'line'"}
        
        success = self.controller.remove_breakpoint(file_path, line)
        return {"success": success}
    
    def _method_toggle_breakpoint(self, params: Dict) -> Dict:
        """切换断点"""
        file_path = params.get("file")
        line = params.get("line")
        
        if not file_path or not line:
            return {"success": False, "error": "Missing 'file' or 'line'"}
        
        success = self.controller.toggle_breakpoint(file_path, line)
        return {"success": success}
    
    def _method_clear_breakpoints(self, params: Dict) -> Dict:
        """清除所有断点"""
        success = self.controller.clear_all_breakpoints()
        return {"success": success}
    
    def _method_list_breakpoints(self, params: Dict) -> Dict:
        """列出断点"""
        breakpoints = self.controller.state.get_all_breakpoints()
        return {
            "success": True,
            "breakpoints": [bp.to_dict() for bp in breakpoints]
        }
    
    def _method_get_state(self, params: Dict) -> Dict:
        """获取完整状态"""
        return {
            "success": True,
            "state": self.controller.get_full_state()
        }
    
    def _method_get_status(self, params: Dict) -> Dict:
        """获取状态摘要"""
        return {
            "success": True,
            "status": self.controller.get_status()
        }
    
    def _method_get_threads(self, params: Dict) -> Dict:
        """获取线程列表"""
        return {
            "success": True,
            "threads": [t.to_dict() for t in self.controller.state.threads]
        }
    
    def _method_get_stack_frames(self, params: Dict) -> Dict:
        """获取调用栈"""
        return {
            "success": True,
            "stackFrames": [f.to_dict() for f in self.controller.state.stack_frames]
        }
    
    def _method_get_variables(self, params: Dict) -> Dict:
        """获取变量"""
        var_ref = params.get("variablesReference")
        if var_ref is None:
            return {"success": False, "error": "Missing 'variablesReference'"}
        
        variables = self.controller.get_variables(var_ref)
        return {
            "success": True,
            "variables": variables
        }
    
    def _method_get_scopes(self, params: Dict) -> Dict:
        """获取作用域"""
        return {
            "success": True,
            "scopes": [s.to_dict() for s in self.controller.state.scopes]
        }
    
    def _method_get_output(self, params: Dict) -> Dict:
        """获取输出"""
        output = self.controller.state.get_output(
            category=params.get("category"),
            limit=params.get("limit", 100)
        )
        return {
            "success": True,
            "output": output
        }
    
    def _method_evaluate(self, params: Dict) -> Dict:
        """求值表达式"""
        expression = params.get("expression")
        if not expression:
            return {"success": False, "error": "Missing 'expression'"}
        
        result = self.controller.evaluate(
            expression,
            frame_id=params.get("frameId"),
            context=params.get("context", "repl")
        )
        
        if result:
            return {"success": True, "result": result}
        return {"success": False, "error": "Evaluation failed"}
    
    def _method_set_variable(self, params: Dict) -> Dict:
        """设置变量"""
        var_ref = params.get("variablesReference")
        name = params.get("name")
        value = params.get("value")
        
        if not all([var_ref, name, value]):
            return {"success": False, "error": "Missing parameters"}
        
        result = self.controller.set_variable(var_ref, name, value)
        if result:
            return {"success": True, "result": result}
        return {"success": False, "error": "Failed to set variable"}
    
    def _method_refresh(self, params: Dict) -> Dict:
        """刷新状态"""
        self.controller.refresh_state()
        return {"success": True}
    
    def _method_ping(self, params: Dict) -> Dict:
        """Ping 命令"""
        return {"success": True, "pong": True}
    
    # ============ 服务器管理 ============
    
    def _start_unix_legacy(self, socket_path: Optional[str] = None) -> bool:
        """
        启动 RPC 服务器
        
        Args:
            socket_path: Unix Socket 路径，默认 /tmp/magic-debug.sock
        
        Returns:
            bool: 是否启动成功
        """
        if self._running:
            logger.warning("RPC server already running")
            return True
        
        self.socket_path = socket_path or "/tmp/magic-debug.sock"
        
        # 确保目录存在
        socket_dir = os.path.dirname(self.socket_path)
        if socket_dir:
            os.makedirs(socket_dir, exist_ok=True)
        
        # 删除已存在的 socket 文件
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)
        
        try:
            # 创建 Unix Socket
            self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._server.bind(self.socket_path)
            self._server.listen(5)
            self._server.settimeout(1.0)  # 允许周期性检查
            
            self._running = True
            
            # 启动接受连接的线程
            self._thread = threading.Thread(
                target=self._accept_loop,
                daemon=True,
                name="RPC-Accept"
            )
            self._thread.start()
            
            # 启动事件广播线程
            self._broadcaster_thread = threading.Thread(
                target=self._broadcast_loop,
                daemon=True,
                name="RPC-Broadcast"
            )
            self._broadcaster_thread.start()
            
            # 注册控制器事件
            self.controller.on("stopped", self._on_debug_event)
            self.controller.on("continued", self._on_debug_event)
            self.controller.on("terminated", self._on_debug_event)
            self.controller.on("breakpoint_changed", self._on_debug_event)
            self.controller.on("state_changed", self._on_debug_event)
            
            logger.info(f"RPC server started at {self.socket_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start RPC server: {e}")
            return False

    def start(
        self,
        socket_path: Optional[str] = None,
        transport: str = "auto",
        host: str = DEFAULT_RPC_HOST,
        port: int = DEFAULT_RPC_PORT,
        endpoint: Optional[RPCEndpoint] = None,
    ) -> bool:
        """Start the RPC server using auto/unix/tcp transport."""
        if self._running:
            logger.warning("RPC server already running")
            return True

        if endpoint is None:
            if socket_path is not None and transport == "auto":
                transport = "unix"
            try:
                endpoint = resolve_rpc_endpoint(
                    transport=transport,
                    host=host,
                    port=port,
                    socket_path=socket_path,
                )
            except RPCTransportError as exc:
                logger.error(str(exc))
                return False

        try:
            self._bind_endpoint(endpoint)
        except Exception as exc:
            if endpoint.requested_transport == "auto" and endpoint.transport == "unix":
                fallback = resolve_rpc_endpoint(transport="tcp", host=host, port=port)
                warning = (
                    f"Failed to create Unix socket, falling back to TCP "
                    f"{fallback.host}:{fallback.port}: {exc}"
                )
                fallback.warnings.append(warning)
                logger.warning(warning)
                try:
                    self._bind_endpoint(fallback)
                except Exception as fallback_exc:
                    logger.error(f"Failed to start RPC server: {fallback_exc}")
                    return False
            else:
                logger.error(f"Failed to start RPC server: {exc}")
                return False

        self._running = True
        self._thread = threading.Thread(
            target=self._accept_loop,
            daemon=True,
            name="RPC-Accept",
        )
        self._thread.start()

        self._broadcaster_thread = threading.Thread(
            target=self._broadcast_loop,
            daemon=True,
            name="RPC-Broadcast",
        )
        self._broadcaster_thread.start()

        self.controller.on("stopped", self._on_debug_event)
        self.controller.on("continued", self._on_debug_event)
        self.controller.on("terminated", self._on_debug_event)
        self.controller.on("breakpoint_changed", self._on_debug_event)
        self.controller.on("state_changed", self._on_debug_event)

        logger.info(f"RPC listening on {self.endpoint.url()}")
        return True

    def _bind_endpoint(self, endpoint: RPCEndpoint):
        self.endpoint = endpoint
        self.socket_path = endpoint.socket_path if endpoint.transport == "unix" else None

        if endpoint.transport == "unix":
            self._server = self._create_unix_server(endpoint.socket_path)
        else:
            self._server = self._create_tcp_server(endpoint.host, endpoint.port)

        self._server.listen(5)
        self._server.settimeout(1.0)

    def _create_unix_server(self, socket_path: str) -> socket.socket:
        socket_dir = os.path.dirname(socket_path)
        if socket_dir:
            os.makedirs(socket_dir, exist_ok=True)

        if os.path.exists(socket_path):
            if should_remove_stale_socket(socket_path):
                os.unlink(socket_path)
            else:
                raise RPCTransportError(
                    f"Refusing to remove non-socket file at RPC socket path: {socket_path}"
                )

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(socket_path)
        return server

    def _create_tcp_server(self, host: str, port: int) -> socket.socket:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((host, int(port)))
        return server
    
    def stop(self):
        """停止 RPC 服务器"""
        self._running = False
        
        # 关闭所有客户端连接
        with self._clients_lock:
            for client in self._clients:
                try:
                    client.close()
                except:
                    pass
            self._clients.clear()
        
        # 关闭服务器
        if self._server:
            try:
                self._server.close()
            except:
                pass
            self._server = None
        
        # 删除 socket 文件
        if self.socket_path and os.path.exists(self.socket_path):
            try:
                os.unlink(self.socket_path)
            except:
                pass
        
        logger.info("RPC server stopped")
    
    def _accept_loop(self):
        """接受连接循环"""
        while self._running:
            try:
                client, _ = self._server.accept()
                client.settimeout(None)  # 阻塞模式
                
                with self._clients_lock:
                    self._clients.append(client)
                
                # 为每个客户端启动处理线程
                thread = threading.Thread(
                    target=self._handle_client,
                    args=(client,),
                    daemon=True,
                    name=f"RPC-Client-{id(client)}"
                )
                thread.start()
                
            except socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    logger.error(f"Error accepting connection: {e}")
    
    def _handle_client(self, client: socket.socket):
        """处理客户端连接"""
        buffer = b""
        
        try:
            while self._running:
                # 接收数据
                try:
                    data = client.recv(4096)
                    if not data:
                        break
                    buffer += data
                except Exception:
                    break
                
                # 处理消息（支持多条消息）
                while b'\n' in buffer:
                    line, buffer = buffer.split(b'\n', 1)
                    if not line.strip():
                        continue
                    
                    try:
                        # 解析请求
                        request = json.loads(line.decode('utf-8'))
                        response = self._handle_request(request)
                        
                        # 发送响应
                        client.sendall(encode_rpc_message(response.to_dict()))
                        
                    except json.JSONDecodeError as e:
                        error_response = RPCResponse(
                            id=None,
                            error={"code": "BAD_REQUEST", "message": "Parse error"}
                        )
                        client.sendall(
                            encode_rpc_message(error_response.to_dict())
                        )
                    except Exception as e:
                        logger.error(f"Error handling request: {e}")
                        error_response = RPCResponse(
                            id=None,
                            error={"code": "INTERNAL_ERROR", "message": "Internal error"}
                        )
                        client.sendall(
                            encode_rpc_message(error_response.to_dict())
                        )
        
        finally:
            # 移除客户端
            with self._clients_lock:
                if client in self._clients:
                    self._clients.remove(client)
            try:
                client.close()
            except:
                pass
    
    def _handle_request(self, request: Dict) -> RPCResponse:
        """处理单个请求"""
        request_id = request.get("id")
        method = request.get("method", "")
        params = request.get("params", {})
        
        if not method:
            return RPCResponse(
                id=request_id,
                error={"code": "BAD_REQUEST", "message": "Invalid request"}
            )
        
        handler = self._methods.get(method)
        if not handler:
            return RPCResponse(
                id=request_id,
                error={"code": "METHOD_NOT_FOUND", "message": f"Method not found: {method}"}
            )
        
        try:
            result = handler(params)
            _, payload = normalize_controller_result(result)
            if payload.get("success") is False:
                return RPCResponse(id=request_id, error=payload["error"])
            return RPCResponse(id=request_id, result=result)
        except Exception as e:
            logger.error(f"Error in method {method}: {e}")
            _, payload = exception_to_error(e)
            return RPCResponse(id=request_id, error=payload["error"])
    
    def _on_debug_event(self, data: Any):
        """处理调试事件"""
        # 将事件放入广播队列
        self._event_queue.put(data)
    
    def _broadcast_loop(self):
        """事件广播循环"""
        while self._running:
            try:
                event = self._event_queue.get(timeout=1.0)
                self._broadcast_event(event)
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error in broadcast loop: {e}")
    
    def _broadcast_event(self, event: Any):
        """广播事件给所有客户端"""
        message_bytes = encode_rpc_message(self._format_event(event))
        
        with self._clients_lock:
            dead_clients = []
            for client in self._clients:
                try:
                    client.sendall(message_bytes)
                except:
                    dead_clients.append(client)
            
            # 移除断开的客户端
            for client in dead_clients:
                self._clients.remove(client)
    
    def _format_event(self, event: Any) -> Dict[str, Any]:
        """Return the stable RPC event envelope."""
        event_name = "debug"
        body = event
        if isinstance(event, dict):
            event_name = event.get("event") or event.get("type") or event_name
            body = event.get("body", event)
        return {
            "type": "event",
            "event": event_name,
            "body": body,
        }

    @property
    def is_running(self) -> bool:
        """服务器是否运行中"""
        return self._running


class RPCClient:
    """
    RPC 客户端
    
    用于测试和调试 RPC 服务器。
    """
    
    def __init__(self, socket_path: str):
        """
        初始化 RPC 客户端
        
        Args:
            socket_path: Unix Socket 路径
        """
        self.socket_path = socket_path
        self._socket: Optional[socket.socket] = None
        self._request_id = 0
    
    def connect(self) -> bool:
        """连接到服务器"""
        try:
            self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._socket.connect(self.socket_path)
            return True
        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            return False
    
    def disconnect(self):
        """断开连接"""
        if self._socket:
            self._socket.close()
            self._socket = None
    
    def call(self, method: str, params: Optional[Dict] = None) -> Dict:
        """
        调用 RPC 方法
        
        Args:
            method: 方法名称
            params: 参数
        
        Returns:
            响应
        """
        if not self._socket:
            raise RuntimeError("Not connected")
        
        self._request_id += 1
        request = {
            "id": self._request_id,
            "method": method,
            "params": params or {}
        }
        
        # 发送请求
        self._socket.sendall((json.dumps(request) + '\n').encode())
        
        # 接收响应
        response_data = b""
        while b'\n' not in response_data:
            chunk = self._socket.recv(4096)
            if not chunk:
                break
            response_data += chunk
        
        return json.loads(response_data.decode())
    
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, *args):
        self.disconnect()

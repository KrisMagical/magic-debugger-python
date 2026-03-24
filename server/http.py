"""
HTTP Server - AI 接口层

提供 HTTP REST API，供 AI 或其他工具调用。
"""

import json
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Optional, Dict, Any, Callable, Type

logger = logging.getLogger(__name__)


class HTTPRequestHandler(BaseHTTPRequestHandler):
    """
    HTTP 请求处理器
    
    处理 REST API 请求。
    """
    
    # 类变量，由 HTTPServer 设置
    controller = None
    router = None
    
    def log_message(self, format, *args):
        """自定义日志格式"""
        logger.debug(f"HTTP: {args[0]}")
    
    def do_GET(self):
        """处理 GET 请求"""
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        
        handler = self.router.get_handler("GET", path)
        if handler:
            try:
                result = handler(query)
                self._send_json(200, result)
            except Exception as e:
                logger.error(f"Error handling GET {path}: {e}")
                self._send_json(500, {"error": str(e)})
        else:
            self._send_json(404, {"error": "Not found"})
    
    def do_POST(self):
        """处理 POST 请求"""
        parsed = urlparse(self.path)
        path = parsed.path
        
        # 读取请求体
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length > 0 else b''
        
        try:
            data = json.loads(body.decode('utf-8')) if body else {}
        except json.JSONDecodeError:
            self._send_json(400, {"error": "Invalid JSON"})
            return
        
        handler = self.router.get_handler("POST", path)
        if handler:
            try:
                result = handler(data)
                self._send_json(200, result)
            except Exception as e:
                logger.error(f"Error handling POST {path}: {e}")
                self._send_json(500, {"error": str(e)})
        else:
            self._send_json(404, {"error": "Not found"})
    
    def do_OPTIONS(self):
        """处理 CORS 预检请求"""
        self.send_response(200)
        self._send_cors_headers()
        self.end_headers()
    
    def _send_json(self, status: int, data: Any):
        """发送 JSON 响应"""
        self.send_response(status)
        self._send_cors_headers()
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))
    
    def _send_cors_headers(self):
        """发送 CORS 头"""
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')


class Router:
    """
    路由器，支持装饰器风格的 URL 路由注册。
    """
    def __init__(self):
        self._routes: Dict[str, Dict[str, Callable]] = {}
    
    def add(self, method: str, path: str, handler: Callable):
        """直接添加路由"""
        if path not in self._routes:
            self._routes[path] = {}
        self._routes[path][method] = handler
    
    def get(self, path: str):
        """装饰器：注册 GET 路由"""
        def decorator(handler):
            self.add("GET", path, handler)
            return handler
        return decorator
    
    def post(self, path: str):
        """装饰器：注册 POST 路由"""
        def decorator(handler):
            self.add("POST", path, handler)
            return handler
        return decorator
    
    def get_handler(self, method: str, path: str) -> Optional[Callable]:
        """获取匹配的路由处理器"""
        if path in self._routes:
            return self._routes[path].get(method)
        return None


class HTTPAPIServer:
    """
    HTTP API 服务器
    
    提供 REST API 接口供 AI 或其他客户端调用。
    
    Example:
        server = HTTPAPIServer(controller)
        server.start(port=8765)
    """
    
    def __init__(self, controller):
        """
        初始化 HTTP API 服务器
        
        Args:
            controller: DebugController 实例
        """
        self.controller = controller
        self.router = Router()
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._port: int = 0
        
        # 注册路由
        self._register_routes()
    
    def _register_routes(self):
        """注册 API 路由"""
        
        # ============ 状态查询 ============
        
        @self.router.get("/api/status")
        def get_status(query):
            """获取调试状态"""
            return {
                "success": True,
                "data": self.controller.get_status()
            }
        
        @self.router.get("/api/state")
        def get_state(query):
            """获取完整状态"""
            return {
                "success": True,
                "data": self.controller.get_full_state()
            }
        
        @self.router.get("/api/threads")
        def get_threads(query):
            """获取线程列表"""
            return {
                "success": True,
                "data": [t.to_dict() for t in self.controller.state.threads]
            }
        
        @self.router.get("/api/stack")
        def get_stack(query):
            """获取调用栈"""
            thread_id = query.get("threadId", [self.controller.state.current_thread_id])
            thread_id = int(thread_id[0]) if thread_id else 0
            
            return {
                "success": True,
                "data": [f.to_dict() for f in self.controller.state.stack_frames]
            }
        
        @self.router.get("/api/scopes")
        def get_scopes(query):
            """获取作用域"""
            frame_id = query.get("frameId", [self.controller.state.current_frame_id])
            frame_id = int(frame_id[0]) if frame_id else 0
            
            return {
                "success": True,
                "data": [s.to_dict() for s in self.controller.state.scopes]
            }
        
        @self.router.get("/api/variables")
        def get_variables(query):
            """获取变量"""
            var_ref = query.get("variablesReference")
            if not var_ref:
                return {"success": False, "error": "Missing variablesReference"}
            
            var_ref = int(var_ref[0])
            variables = self.controller.get_variables(var_ref)
            
            return {
                "success": True,
                "data": variables
            }
        
        @self.router.get("/api/breakpoints")
        def get_breakpoints(query):
            """获取断点列表"""
            file_path = query.get("file", [None])[0]
            
            if file_path:
                bps = self.controller.state.get_file_breakpoints(file_path)
            else:
                bps = self.controller.state.get_all_breakpoints()
            
            return {
                "success": True,
                "data": [bp.to_dict() for bp in bps]
            }
        
        @self.router.get("/api/output")
        def get_output(query):
            """获取输出"""
            category = query.get("category", [None])[0]
            limit = int(query.get("limit", [100])[0])
            
            output = self.controller.state.get_output(category=category, limit=limit)
            
            return {
                "success": True,
                "data": output
            }
        
        # ============ 执行控制 ============
        
        @self.router.post("/api/start")
        def start_debug(data):
            """启动调试"""
            from core.controller import DebugConfig
            
            program = data.get("program")
            if not program:
                return {"success": False, "error": "Missing program"}
            
            config = DebugConfig(
                program=program,
                args=data.get("args", []),
                cwd=data.get("cwd"),
                env=data.get("env", {}),
                stop_on_entry=data.get("stopOnEntry", False),
            )
            
            success = self.controller.start(config)
            return {"success": success}
        
        @self.router.post("/api/stop")
        def stop_debug(data):
            """停止调试"""
            success = self.controller.stop(
                terminate_debuggee=data.get("terminateDebuggee", True)
            )
            return {"success": success}
        
        @self.router.post("/api/restart")
        def restart_debug(data):
            """重启调试"""
            success = self.controller.restart()
            return {"success": success}
        
        @self.router.post("/api/continue")
        def continue_exec(data):
            """继续执行"""
            success = self.controller.continue_()
            return {"success": success}
        
        @self.router.post("/api/pause")
        def pause_exec(data):
            """暂停执行"""
            success = self.controller.pause()
            return {"success": success}
        
        @self.router.post("/api/step/over")
        def step_over(data):
            """单步跳过"""
            success = self.controller.step_over()
            return {"success": success}
        
        @self.router.post("/api/step/into")
        def step_into(data):
            """单步进入"""
            success = self.controller.step_into()
            return {"success": success}
        
        @self.router.post("/api/step/out")
        def step_out(data):
            """单步跳出"""
            success = self.controller.step_out()
            return {"success": success}
        
        # ============ 断点管理 ============
        
        @self.router.post("/api/breakpoint/set")
        def set_breakpoint(data):
            """设置断点"""
            file_path = data.get("file")
            line = data.get("line")
            
            if not file_path or not line:
                return {"success": False, "error": "Missing file or line"}
            
            success = self.controller.set_breakpoint(
                file_path, line,
                condition=data.get("condition"),
                hit_condition=data.get("hitCondition"),
                log_message=data.get("logMessage"),
            )
            return {"success": success}
        
        @self.router.post("/api/breakpoint/remove")
        def remove_breakpoint(data):
            """移除断点"""
            file_path = data.get("file")
            line = data.get("line")
            
            if not file_path or not line:
                return {"success": False, "error": "Missing file or line"}
            
            success = self.controller.remove_breakpoint(file_path, line)
            return {"success": success}
        
        @self.router.post("/api/breakpoint/toggle")
        def toggle_breakpoint(data):
            """切换断点"""
            file_path = data.get("file")
            line = data.get("line")
            
            if not file_path or not line:
                return {"success": False, "error": "Missing file or line"}
            
            success = self.controller.toggle_breakpoint(file_path, line)
            return {"success": success}
        
        @self.router.post("/api/breakpoint/clear")
        def clear_breakpoints(data):
            """清除所有断点"""
            success = self.controller.clear_all_breakpoints()
            return {"success": success}
        
        # ============ 求值和变量 ============
        
        @self.router.post("/api/evaluate")
        def evaluate_expr(data):
            """求值表达式"""
            expression = data.get("expression")
            if not expression:
                return {"success": False, "error": "Missing expression"}
            
            result = self.controller.evaluate(
                expression,
                frame_id=data.get("frameId"),
                context=data.get("context", "repl")
            )
            
            if result:
                return {"success": True, "data": result}
            return {"success": False, "error": "Evaluation failed"}
        
        @self.router.post("/api/variable/set")
        def set_variable(data):
            """设置变量值"""
            var_ref = data.get("variablesReference")
            name = data.get("name")
            value = data.get("value")
            
            if not all([var_ref, name, value]):
                return {"success": False, "error": "Missing parameters"}
            
            result = self.controller.set_variable(var_ref, name, value)
            if result:
                return {"success": True, "data": result}
            return {"success": False, "error": "Failed to set variable"}
        
        # ============ 刷新 ============
        
        @self.router.post("/api/refresh")
        def refresh_state(data):
            """刷新状态"""
            self.controller.refresh_state()
            return {"success": True}
    
    def start(self, host: str = "127.0.0.1", port: int = 8765) -> bool:
        """
        启动 HTTP 服务器
        
        Args:
            host: 监听地址
            port: 监听端口
        
        Returns:
            bool: 是否启动成功
        """
        if self._running:
            logger.warning("HTTP server already running")
            return True
        
        try:
            # 设置请求处理器的类变量
            HTTPRequestHandler.controller = self.controller
            HTTPRequestHandler.router = self.router
            
            # 创建服务器
            self._server = HTTPServer((host, port), HTTPRequestHandler)
            self._port = port
            self._running = True
            
            # 启动服务器线程
            self._thread = threading.Thread(
                target=self._run_server,
                daemon=True,
                name="HTTP-Server"
            )
            self._thread.start()
            
            logger.info(f"HTTP API server started at http://{host}:{port}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start HTTP server: {e}")
            return False
    
    def _run_server(self):
        """运行服务器"""
        try:
            self._server.serve_forever()
        except Exception as e:
            if self._running:
                logger.error(f"HTTP server error: {e}")
    
    def stop(self):
        """停止 HTTP 服务器"""
        self._running = False
        
        if self._server:
            self._server.shutdown()
            self._server = None
        
        logger.info("HTTP API server stopped")
    
    @property
    def is_running(self) -> bool:
        """服务器是否运行中"""
        return self._running
    
    @property
    def port(self) -> int:
        """服务器端口"""
        return self._port
    
    def get_url(self) -> str:
        """获取服务器 URL"""
        return f"http://127.0.0.1:{self._port}"


# API 文档
API_DOCS = """
# Magic Debug HTTP API 文档

## 状态查询

### GET /api/status
获取调试状态摘要

### GET /api/state
获取完整调试状态

### GET /api/threads
获取线程列表

### GET /api/stack
获取调用栈
参数: threadId (可选)

### GET /api/scopes
获取作用域
参数: frameId (可选)

### GET /api/variables
获取变量
参数: variablesReference (必需)

### GET /api/breakpoints
获取断点列表
参数: file (可选)

### GET /api/output
获取输出
参数: category, limit (可选)

## 执行控制

### POST /api/start
启动调试
Body: {program, args, cwd, env, stopOnEntry}

### POST /api/stop
停止调试
Body: {terminateDebuggee}

### POST /api/restart
重启调试

### POST /api/continue
继续执行

### POST /api/pause
暂停执行

### POST /api/step/over
单步跳过

### POST /api/step/into
单步进入

### POST /api/step/out
单步跳出

## 断点管理

### POST /api/breakpoint/set
设置断点
Body: {file, line, condition, hitCondition, logMessage}

### POST /api/breakpoint/remove
移除断点
Body: {file, line}

### POST /api/breakpoint/toggle
切换断点
Body: {file, line}

### POST /api/breakpoint/clear
清除所有断点

## 求值

### POST /api/evaluate
求值表达式
Body: {expression, frameId, context}

### POST /api/variable/set
设置变量
Body: {variablesReference, name, value}

### POST /api/refresh
刷新状态
"""

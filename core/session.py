"""
Session Manager - 进程控制层

负责启动并控制 lldb-dap 进程，管理其标准输入输出。
"""

import subprocess
import os
import threading
import queue
import logging
from typing import Optional, Callable, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ProcessInfo:
    """进程信息"""
    pid: int
    command: List[str]
    is_running: bool = True
    exit_code: Optional[int] = None


class DebugSession:
    """
    调试会话管理器
    
    负责启动、管理和监控调试适配器进程（如 lldb-dap）。
    使用非缓冲 I/O 确保实时通信。
    
    Attributes:
        proc: 子进程对象
        info: 进程信息
        output_queue: 输出队列，用于线程间通信
        error_queue: 错误输出队列
    """
    
    def __init__(self, command: List[str], env: Optional[dict] = None):
        """
        初始化调试会话
        
        Args:
            command: 启动命令及参数列表，如 ['lldb-dap']
            env: 可选的环境变量字典
        """
        self.command = command
        self.proc: Optional[subprocess.Popen] = None
        self.info: Optional[ProcessInfo] = None
        self.output_queue: queue.Queue = queue.Queue()
        self.error_queue: queue.Queue = queue.Queue()
        self._reader_thread: Optional[threading.Thread] = None
        self._error_thread: Optional[threading.Thread] = None
        self._running = False
        self._on_exit: Optional[Callable[[int], None]] = None
        
        # 合并环境变量
        self.env = os.environ.copy()
        if env:
            self.env.update(env)
    
    def start(self) -> bool:
        """
        启动调试适配器进程
        
        Returns:
            bool: 启动是否成功
        """
        try:
            logger.info(f"Starting debug adapter: {' '.join(self.command)}")
            
            # 使用非缓冲模式启动进程
            # bufsize=0 确保无缓冲，text=True 使 I/O 为字符串模式
            self.proc = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=0,  # 无缓冲，关键！
                env=self.env
            )
            
            self.info = ProcessInfo(
                pid=self.proc.pid,
                command=self.command,
                is_running=True
            )
            
            self._running = True
            
            # 启动输出读取线程
            self._reader_thread = threading.Thread(
                target=self._read_output,
                daemon=True,
                name="DAP-Reader"
            )
            self._reader_thread.start()
            
            # 启动错误输出读取线程
            self._error_thread = threading.Thread(
                target=self._read_error,
                daemon=True,
                name="DAP-Error"
            )
            self._error_thread.start()
            
            logger.info(f"Debug adapter started with PID: {self.proc.pid}")
            return True
            
        except FileNotFoundError:
            logger.error(f"Debug adapter not found: {self.command[0]}")
            return False
        except Exception as e:
            logger.error(f"Failed to start debug adapter: {e}")
            return False
    
    def _read_output(self):
        """读取进程标准输出的线程函数"""
        try:
            while self._running and self.proc and self.proc.stdout:
                line = self.proc.stdout.readline()
                if not line:
                    break
                self.output_queue.put(line)
        except Exception as e:
            logger.debug(f"Output reader stopped: {e}")
        finally:
            self._check_exit()
    
    def _read_error(self):
        """读取进程错误输出的线程函数"""
        try:
            while self._running and self.proc and self.proc.stderr:
                line = self.proc.stderr.readline()
                if not line:
                    break
                self.error_queue.put(line)
                logger.debug(f"Debugger stderr: {line.strip()}")
        except Exception as e:
            logger.debug(f"Error reader stopped: {e}")
    
    def _check_exit(self):
        """检查进程是否退出"""
        if self.proc and self.proc.poll() is not None:
            self._running = False
            if self.info:
                self.info.is_running = False
                self.info.exit_code = self.proc.returncode
            logger.info(f"Debug adapter exited with code: {self.proc.returncode}")
            if self._on_exit:
                self._on_exit(self.proc.returncode)
    
    def write(self, data: str) -> bool:
        """
        向进程写入数据
        
        Args:
            data: 要写入的字符串数据
        
        Returns:
            bool: 写入是否成功
        """
        if not self.is_alive():
            logger.warning("Cannot write: process is not running")
            return False
        
        try:
            self.proc.stdin.write(data)
            self.proc.stdin.flush()
            logger.debug(f"Sent {len(data)} bytes")
            return True
        except Exception as e:
            logger.error(f"Write failed: {e}")
            return False
    
    def read(self, n: int, timeout: Optional[float] = None) -> Optional[str]:
        """
        从输出队列读取指定数量的字符
        
        Args:
            n: 要读取的字符数
            timeout: 超时时间（秒）
        
        Returns:
            读取到的字符串，超时返回 None
        """
        result = []
        remaining = n
        
        while remaining > 0:
            try:
                line = self.output_queue.get(timeout=timeout)
                result.append(line)
                remaining -= len(line)
            except queue.Empty:
                break
        
        return ''.join(result) if result else None
    
    def readline(self, timeout: Optional[float] = None) -> Optional[str]:
        """
        读取一行输出
        
        Args:
            timeout: 超时时间（秒）
        
        Returns:
            读取到的行，超时返回 None
        """
        try:
            return self.output_queue.get(timeout=timeout)
        except queue.Empty:
            return None
    
    def read_available(self, timeout: float = 0.1) -> str:
        """
        读取当前所有可用的输出
        
        Args:
            timeout: 等待超时时间
        
        Returns:
            所有可用的输出内容
        """
        result = []
        while True:
            try:
                line = self.output_queue.get(timeout=timeout)
                result.append(line)
            except queue.Empty:
                break
        return ''.join(result)
    
    def read_error(self, timeout: float = 0.1) -> str:
        """
        读取错误输出
        
        Args:
            timeout: 等待超时时间
        
        Returns:
            错误输出内容
        """
        result = []
        while True:
            try:
                line = self.error_queue.get(timeout=timeout)
                result.append(line)
            except queue.Empty:
                break
        return ''.join(result)
    
    def is_alive(self) -> bool:
        """检查进程是否存活"""
        if self.proc is None:
            return False
        return self.proc.poll() is None
    
    def terminate(self):
        """终止进程"""
        if self.proc and self.is_alive():
            logger.info("Terminating debug adapter...")
            self._running = False
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
            
            if self.info:
                self.info.is_running = False
    
    def on_exit(self, callback: Callable[[int], None]):
        """设置进程退出回调"""
        self._on_exit = callback
    
    def __enter__(self):
        """上下文管理器入口"""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.terminate()
        return False
    
    def __repr__(self):
        status = "running" if self.is_alive() else "stopped"
        return f"<DebugSession pid={self.info.pid if self.info else 'N/A'} status={status}>"


class SessionManager:
    """
    会话管理器
    
    管理多个调试会话，提供统一的创建、查询和销毁接口。
    """
    
    def __init__(self):
        self.sessions: dict[str, DebugSession] = {}
        self._lock = threading.Lock()
    
    def create_session(self, name: str, command: List[str], 
                       env: Optional[dict] = None) -> DebugSession:
        """
        创建新的调试会话
        
        Args:
            name: 会话名称
            command: 启动命令
            env: 环境变量
        
        Returns:
            创建的调试会话
        """
        with self._lock:
            if name in self.sessions:
                raise ValueError(f"Session '{name}' already exists")
            
            session = DebugSession(command, env)
            self.sessions[name] = session
            return session
    
    def get_session(self, name: str) -> Optional[DebugSession]:
        """获取指定名称的会话"""
        return self.sessions.get(name)
    
    def remove_session(self, name: str):
        """移除并终止指定会话"""
        with self._lock:
            session = self.sessions.pop(name, None)
            if session:
                session.terminate()
    
    def list_sessions(self) -> List[str]:
        """列出所有会话名称"""
        return list(self.sessions.keys())
    
    def terminate_all(self):
        """终止所有会话"""
        with self._lock:
            for session in self.sessions.values():
                session.terminate()
            self.sessions.clear()

#!/usr/bin/env python3
"""
Magic Debug - 主程序入口

AI 驱动的调试器，支持 Vim 插件和 AI 接口。
"""

import sys
import os
import argparse
import logging
import signal
import json
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

from core.session import DebugSession
from core.dap import DAPClient
from core.state import DebugState
from core.controller import DebugController, DebugConfig
from adapters.gdb import GDBAdapter, check_gdb_installation
from server.rpc import RPCServer
from server.http import HTTPAPIServer


def setup_logging(verbose: bool = False, log_file: str = None):
    """
    配置日志
    
    Args:
        verbose: 是否启用详细日志
        log_file: 日志文件路径
    """
    level = logging.DEBUG if verbose else logging.INFO
    
    handlers = [logging.StreamHandler()]
    if log_file:
        handlers.append(logging.FileHandler(log_file))
    
    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=handlers
    )


class MagicDebug:
    """
    Magic Debug 应用
    
    整合所有组件，管理调试器生命周期。
    """
    
    def __init__(self, config: dict):
        """
        初始化 Magic Debug
        
        Args:
            config: 配置字典
        """
        self.config = config
        
        # 核心组件
        self.session: DebugSession = None
        self.dap: DAPClient = None
        self.state: DebugState = None
        self.controller: DebugController = None
        
        # 服务器
        self.rpc_server: RPCServer = None
        self.http_server: HTTPAPIServer = None
        
        # GDB 适配器
        self.gdb_adapter: GDBAdapter = None
        
        # 运行状态
        self._running = False
    
    def initialize(self) -> bool:
        """
        初始化所有组件
        
        Returns:
            bool: 是否成功
        """
        logger = logging.getLogger(__name__)
        
        # 检查 GDB
        gdb_status = check_gdb_installation()
        if not gdb_status["available"]:
            logger.error("GDB not found. Please install GDB (version >= 11 for DAP support).")
            logger.error("On macOS: brew install gdb")
            logger.error("On Linux: apt install gdb")
            return False
        
        logger.info(f"Found GDB at: {gdb_status['gdb_path']}")
        logger.info(f"GDB version: {gdb_status['version']}")
        
        # 创建 GDB 适配器
        self.gdb_adapter = GDBAdapter()
        self.gdb_adapter.gdb_path = gdb_status["gdb_path"]
        
        # 获取 GDB DAP 启动命令
        command = self.gdb_adapter.command
        logger.info(f"Starting GDB DAP with command: {' '.join(command)}")
        
        # 创建调试会话
        self.session = DebugSession(command)
        
        # 启动 GDB 进程
        if not self.session.start():
            logger.error("Failed to start GDB DAP")
            return False
        
        # 创建 DAP 客户端
        self.dap = DAPClient(self.session)
        
        # 创建状态管理
        self.state = DebugState()
        
        # 创建控制器
        self.controller = DebugController(self.dap, self.state)
        
        # 启动 RPC 服务器
        self.rpc_server = RPCServer(self.controller)
        socket_path = self.config.get("socket_path", "/tmp/magic-debug.sock")
        if not self.rpc_server.start(socket_path):
            logger.error("Failed to start RPC server")
            return False
        
        # 启动 HTTP 服务器
        self.http_server = HTTPAPIServer(self.controller)
        http_port = self.config.get("http_port", 8765)
        if not self.http_server.start(port=http_port):
            logger.error("Failed to start HTTP server")
            return False
        
        logger.info(f"RPC socket: {socket_path}")
        logger.info(f"HTTP API: http://127.0.0.1:{http_port}")
        
        self._running = True
        return True
    
    def run(self):
        """运行主循环"""
        logger = logging.getLogger(__name__)
        logger.info("Magic Debug is running. Press Ctrl+C to stop.")
        
        try:
            # 主循环 - 等待信号
            while self._running:
                import time
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Shutting down...")
        finally:
            self.shutdown()
    
    def shutdown(self):
        """关闭所有组件"""
        logger = logging.getLogger(__name__)
        logger.info("Shutting down Magic Debug...")
        
        self._running = False
        
        # 停止服务器
        if self.rpc_server:
            self.rpc_server.stop()
        
        if self.http_server:
            self.http_server.stop()
        
        # 停止调试会话
        if self.session:
            self.session.terminate()
        
        logger.info("Magic Debug stopped")
    
    def debug_program(self, program: str, args: list = None,
                      stop_on_entry: bool = False):
        """
        启动调试（便捷方法）
        
        Args:
            program: 程序路径
            args: 命令行参数
            stop_on_entry: 是否在入口处停止
        """
        config = DebugConfig(
            program=program,
            args=args or [],
            stop_on_entry=stop_on_entry
        )
        return self.controller.start(config)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="Magic Debug - AI-powered debugger",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Start server
  %(prog)s --debug ./myapp          # Start and debug program
  %(prog)s --socket /tmp/md.sock    # Custom socket path
  %(prog)s --port 9000              # Custom HTTP port
        """
    )
    
    parser.add_argument(
        "--debug", "-d",
        metavar="PROGRAM",
        help="Program to debug"
    )
    parser.add_argument(
        "--args", "-a",
        metavar="ARGS",
        help="Program arguments (comma-separated)"
    )
    parser.add_argument(
        "--stop-on-entry",
        action="store_true",
        help="Stop at program entry"
    )
    parser.add_argument(
        "--socket", "-s",
        default="/tmp/magic-debug.sock",
        metavar="PATH",
        help="Unix socket path for Vim RPC (default: /tmp/magic-debug.sock)"
    )
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=8765,
        metavar="PORT",
        help="HTTP API port (default: 8765)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    parser.add_argument(
        "--log-file",
        metavar="FILE",
        help="Log file path"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check GDB installation and exit"
    )
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 1.0.0"
    )
    
    args = parser.parse_args()
    
    # 配置日志
    setup_logging(verbose=args.verbose, log_file=args.log_file)
    logger = logging.getLogger(__name__)
    
    # 检查安装
    if args.check:
        status = check_gdb_installation()
        print(json.dumps(status, indent=2))
        return 0 if status["available"] else 1
    
    # 创建配置
    config = {
        "socket_path": args.socket,
        "http_port": args.port,
    }
    
    # 创建应用
    app = MagicDebug(config)
    
    # 设置信号处理
    def signal_handler(sig, frame):
        logger.info("Received signal to terminate")
        app._running = False
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 初始化
    if not app.initialize():
        logger.error("Failed to initialize Magic Debug")
        return 1
    
    # 如果指定了要调试的程序
    if args.debug:
        prog_args = args.args.split(",") if args.args else []
        if not app.debug_program(args.debug, prog_args, args.stop_on_entry):
            logger.error(f"Failed to start debugging: {args.debug}")
    
    # 运行
    app.run()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
"""
GDB DAP Adapter - GDB 调试适配器封装

提供 GDB 特定的配置和命令封装。
"""

import os
import shutil
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class GDBConfig:
    """GDB 配置"""
    # GDB 可执行文件路径
    gdb_path: str = "gdb"

    # GDB DAP 模式参数
    dap_args: List[str] = field(default_factory=lambda: ["--interpreter=dap"])

    # 预运行命令 (GDB 特有，在启动时执行)
    init_commands: List[str] = field(default_fault=list)

    # 源码映射 (GDB 特有)
    source_map: Dict[str, str] = field(default_factory=dict)

    # 是否显示反汇编
    disassembly_display: str = "auto"  # "auto", "always", "never"

    # 自定义格式化器
    custom_formatters: Dict[str, str] = field(default_factory=dict)


class GDBAdapter:
    """
    GDB 调试适配器

    封装 GDB 特定的功能和配置。
    """

    def __init__(self, config: Optional[GDBConfig] = None):
        """
        初始化 GDB 适配器

        Args:
            config: GDB 配置
        """
        self.config = config or GDBConfig()
        self._gdb_path: Optional[str] = None

    def find_gdb(self) -> Optional[str]:
        """
        查找 gdb 可执行文件

        Returns:
            gdb 路径，未找到返回 None
        """
        # 1. 检查配置的路径
        if self.config.gdb_path:
            if os.path.isabs(self.config.gdb_path):
                if os.path.isfile(self.config.gdb_path):
                    return self.config.gdb_path
            else:
                found = shutil.which(self.config.gdb_path)
                if found:
                    return found

        # 2. 常见位置
        common_paths = [
            "gdb",
            "/usr/bin/gdb",
            "/usr/local/bin/gdb",
            "/opt/homebrew/bin/gdb",
            "/opt/local/bin/gdb",
        ]

        for path in common_paths:
            if os.path.isabs(path):
                if os.path.isfile(path):
                    return path
            else:
                found = shutil.which(path)
                if found:
                    return found

        return None

    def get_launch_arguments(self, program: str, **kwargs) -> Dict[str, Any]:
        """
        获取 GDB 特定的 launch 参数

        Args:
            program: 程序路径
            **kwargs: 额外参数

        Returns:
            launch 参数字典
        """
        args = {
            "program": program,
        }

        # 基础参数
        if "args" in kwargs:
            args["args"] = kwargs["args"]
        if "cwd" in kwargs:
            args["cwd"] = kwargs["cwd"]
        if "env" in kwargs:
            args["env"] = kwargs["env"]

        # GDB 特定参数
        if self.config.init_commands:
            args["initCommands"] = self.config.init_commands

        if self.config.source_map:
            args["sourceMap"] = self.config.source_map

        # 停止选项
        args["stopOnEntry"] = kwargs.get("stop_on_entry", False)

        # 合并其他参数
        for key, value in kwargs.items():
            if key not in ["args", "cwd", "env", "stop_on_entry"]:
                args[key] = value

        return args

    def get_attach_arguments(self, pid: Optional[int] = None,
                             program: Optional[str] = None,
                             **kwargs) -> Dict[str, Any]:
        """
        获取 GDB 特定的 attach 参数

        Args:
            pid: 进程 ID
            program: 程序路径
            **kwargs: 额外参数

        Returns:
            attach 参数字典
        """
        args = {}

        if pid is not None:
            args["pid"] = pid
        elif program:
            args["program"] = program

        if self.config.init_commands:
            args["initCommands"] = self.config.init_commands

        args.update(kwargs)
        return args

    def is_available(self) -> bool:
        """检查 GDB 是否可用"""
        return self.find_gdb() is not None

    def get_version(self) -> Optional[str]:
        """获取 GDB 版本"""
        import subprocess

        gdb_path = self.find_gdb()
        if not gdb_path:
            return None

        try:
            result = subprocess.run(
                [gdb_path, "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass

        return None

    @property
    def command(self) -> List[str]:
        """获取完整的 GDB DAP 启动命令"""
        gdb_path = self.find_gdb() or "gdb"
        return [gdb_path] + self.config.dap_args

    @property
    def gdb_path(self) -> str:
        """获取 gdb 路径"""
        if self._gdb_path is None:
            self._gdb_path = self.find_gdb() or "gdb"
        return self._gdb_path

    @gdb_path.setter
    def gdb_path(self, path: str):
        """设置 gdb 路径"""
        self._gdb_path = path
        self.config.gdb_path = path


class GDBCommandBuilder:
    """
    GDB 命令构建器

    辅助构建 GDB 命令字符串。
    """

    @staticmethod
    def breakpoint_set(file: str, line: int, condition: Optional[str] = None) -> str:
        """构建设置断点命令"""
        cmd = f"break {file}:{line}"
        if condition:
            cmd += f" if {condition}"
        return cmd

    @staticmethod
    def breakpoint_set_by_name(name: str) -> str:
        """构建设置函数断点命令"""
        return f"break {name}"

    @staticmethod
    def breakpoint_delete(bpid: int) -> str:
        """构建删除断点命令"""
        return f"delete {bpid}"

    @staticmethod
    def breakpoint_list() -> str:
        """构建列出断点命令"""
        return "info breakpoints"

    @staticmethod
    def expression(expr: str) -> str:
        """构建表达式求值命令"""
        return f"print {expr}"

    @staticmethod
    def frame_variable(var_name: Optional[str] = None) -> str:
        """构建打印变量命令"""
        if var_name:
            return f"print {var_name}"
        return "info locals"

    @staticmethod
    def thread_list() -> str:
        """构建列出线程命令"""
        return "info threads"

    @staticmethod
    def thread_backtrace() -> str:
        """构建打印调用栈命令"""
        return "backtrace"

    @staticmethod
    def target_create(program: str) -> str:
        """构建创建目标命令"""
        return f"file {program}"

    @staticmethod
    def process_launch(args: Optional[List[str]] = None) -> str:
        """构建启动进程命令"""
        cmd = "run"
        if args:
            cmd += " " + " ".join(args)
        return cmd

    @staticmethod
    def process_attach(pid: int) -> str:
        """构建附加进程命令"""
        return f"attach {pid}"

    @staticmethod
    def process_detach() -> str:
        """构建分离进程命令"""
        return "detach"

    @staticmethod
    def run() -> str:
        """构建运行命令"""
        return "run"

    @staticmethod
    def continue_() -> str:
        """构建继续命令"""
        return "continue"

    @staticmethod
    def next() -> str:
        """构建单步跳过命令"""
        return "next"

    @staticmethod
    def step() -> str:
        """构建单步进入命令"""
        return "step"

    @staticmethod
    def finish() -> str:
        """构建单步跳出命令"""
        return "finish"


# 常用 GDB 配置预设
GDB_PRESETS = {
    "default": GDBConfig(),

    "cpp": GDBConfig(
        init_commands=[
            "set print pretty on",
        ],
    ),

    "rust": GDBConfig(
        init_commands=[
            # Rust 特定设置
            "set print pretty on",
            "set print elements 1000",
        ],
    ),
}


def get_adapter(preset: str = "default") -> GDBAdapter:
    """
    获取 GDB 适配器实例

    Args:
        preset: 预设名称

    Returns:
        GDBAdapter 实例
    """
    config = GDB_PRESETS.get(preset, GDBConfig())
    return GDBAdapter(config)


def check_gdb_installation() -> Dict[str, Any]:
    """
    检查 GDB 安装状态

    Returns:
        检查结果
    """
    adapter = GDBAdapter()
    gdb_path = adapter.find_gdb()

    result = {
        "available": gdb_path is not None,
        "gdb_path": gdb_path,
        "version": None,
    }

    if gdb_path:
        result["version"] = adapter.get_version()

    return result
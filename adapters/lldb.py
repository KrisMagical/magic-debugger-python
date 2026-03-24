"""
LLDB DAP Adapter - LLDB 调试适配器封装

提供 LLDB 特定的配置和命令封装。
"""

import os
import shutil
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class LLDBConfig:
    """LLDB 配置"""
    # lldb-dap 可执行文件路径
    dap_path: str = "lldb-dap"
    
    # LLDB 命令（在启动时执行）
    init_commands: List[str] = field(default_factory=list)
    
    # 预运行命令
    pre_run_commands: List[str] = field(default_factory=list)
    
    # 源码映射 (LLDB 特有)
    source_map: Dict[str, str] = field(default_factory=dict)
    
    # 是否自动展开非公共成员
    display_extended_backtrace: bool = False
    
    # 是否显示反汇编
    disassembly_display: str = "auto"  # "auto", "always", "never"
    
    # 自定义格式化器
    custom_formatters: Dict[str, str] = field(default_factory=dict)


class LLDBAdapter:
    """
    LLDB 调试适配器
    
    封装 LLDB 特定的功能和配置。
    """
    
    def __init__(self, config: Optional[LLDBConfig] = None):
        """
        初始化 LLDB 适配器
        
        Args:
            config: LLDB 配置
        """
        self.config = config or LLDBConfig()
        self._dap_path: Optional[str] = None
    
    def find_lldb_dap(self) -> Optional[str]:
        """
        查找 lldb-dap 可执行文件
        
        Returns:
            lldb-dap 路径，未找到返回 None
        """
        # 1. 检查配置的路径
        if self.config.dap_path:
            if os.path.isabs(self.config.dap_path):
                if os.path.isfile(self.config.dap_path):
                    return self.config.dap_path
            else:
                found = shutil.which(self.config.dap_path)
                if found:
                    return found
        
        # 2. 常见位置
        common_paths = [
            "lldb-dap",
            "/usr/local/bin/lldb-dap",
            "/opt/homebrew/bin/lldb-dap",
            "/usr/bin/lldb-dap",
            "/opt/local/bin/lldb-dap",
        ]
        
        # 3. Xcode 路径 (macOS)
        xcode_path = self._find_xcode_lldb_dap()
        if xcode_path:
            common_paths.insert(0, xcode_path)
        
        for path in common_paths:
            if os.path.isabs(path):
                if os.path.isfile(path):
                    return path
            else:
                found = shutil.which(path)
                if found:
                    return found
        
        return None
    
    def _find_xcode_lldb_dap(self) -> Optional[str]:
        """查找 Xcode 中的 lldb-dap"""
        import subprocess
        
        try:
            # 获取 Xcode 开发者目录
            result = subprocess.run(
                ["xcode-select", "-p"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                xcode_dev = result.stdout.strip()
                lldb_dap = os.path.join(
                    xcode_dev,
                    "usr",
                    "bin",
                    "lldb-dap"
                )
                if os.path.isfile(lldb_dap):
                    return lldb_dap
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        
        return None
    
    def get_launch_arguments(self, program: str, **kwargs) -> Dict[str, Any]:
        """
        获取 LLDB 特定的 launch 参数
        
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
        
        # LLDB 特定参数
        if self.config.init_commands:
            args["initCommands"] = self.config.init_commands
        
        if self.config.pre_run_commands:
            args["preRunCommands"] = self.config.pre_run_commands
        
        if self.config.source_map:
            args["sourceMap"] = self.config.source_map
        
        if self.config.display_extended_backtrace:
            args["displayExtendedBacktrace"] = True
        
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
        获取 LLDB 特定的 attach 参数
        
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
        """检查 LLDB 是否可用"""
        return self.find_lldb_dap() is not None
    
    def get_version(self) -> Optional[str]:
        """获取 LLDB 版本"""
        import subprocess
        
        lldb_dap = self.find_lldb_dap()
        if not lldb_dap:
            return None
        
        try:
            result = subprocess.run(
                [lldb_dap, "--version"],
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
    def dap_path(self) -> str:
        """获取 lldb-dap 路径"""
        if self._dap_path is None:
            self._dap_path = self.find_lldb_dap() or "lldb-dap"
        return self._dap_path
    
    @dap_path.setter
    def dap_path(self, path: str):
        """设置 lldb-dap 路径"""
        self._dap_path = path
        self.config.dap_path = path


class LLDBCommandBuilder:
    """
    LLDB 命令构建器
    
    辅助构建 LLDB 命令字符串。
    """
    
    @staticmethod
    def breakpoint_set(file: str, line: int, condition: Optional[str] = None) -> str:
        """构建设置断点命令"""
        cmd = f"breakpoint set --file {file} --line {line}"
        if condition:
            cmd += f" --condition '{condition}'"
        return cmd
    
    @staticmethod
    def breakpoint_set_by_name(name: str) -> str:
        """构建设置函数断点命令"""
        return f"breakpoint set --name {name}"
    
    @staticmethod
    def breakpoint_delete(bpid: int) -> str:
        """构建删除断点命令"""
        return f"breakpoint delete {bpid}"
    
    @staticmethod
    def breakpoint_list() -> str:
        """构建列出断点命令"""
        return "breakpoint list"
    
    @staticmethod
    def expression(expr: str) -> str:
        """构建表达式求值命令"""
        return f"expression {expr}"
    
    @staticmethod
    def frame_variable(var_name: Optional[str] = None) -> str:
        """构建打印变量命令"""
        if var_name:
            return f"frame variable {var_name}"
        return "frame variable"
    
    @staticmethod
    def thread_list() -> str:
        """构建列出线程命令"""
        return "thread list"
    
    @staticmethod
    def thread_backtrace() -> str:
        """构建打印调用栈命令"""
        return "thread backtrace"
    
    @staticmethod
    def target_create(program: str) -> str:
        """构建创建目标命令"""
        return f"target create {program}"
    
    @staticmethod
    def process_launch(args: Optional[List[str]] = None) -> str:
        """构建启动进程命令"""
        cmd = "process launch"
        if args:
            cmd += " -- " + " ".join(args)
        return cmd
    
    @staticmethod
    def process_attach(pid: int) -> str:
        """构建附加进程命令"""
        return f"process attach --pid {pid}"
    
    @staticmethod
    def process_detach() -> str:
        """构建分离进程命令"""
        return "process detach"
    
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


# 常用 LLDB 配置预设
LLDB_PRESETS = {
    "default": LLDBConfig(),
    
    "cpp": LLDBConfig(
        init_commands=[
            "settings set target.x86-disassembly-flavor intel",
        ],
    ),
    
    "rust": LLDBConfig(
        init_commands=[
            # Rust 特定设置
            "settings set target.max-string-summary-length 1000",
            "settings set target.max-children-count 256",
        ],
    ),
    
    "swift": LLDBConfig(
        init_commands=[
            # Swift 特定设置
            "settings set target.max-string-summary-length 1000",
        ],
    ),
}


def get_adapter(preset: str = "default") -> LLDBAdapter:
    """
    获取 LLDB 适配器实例
    
    Args:
        preset: 预设名称
    
    Returns:
        LLDBAdapter 实例
    """
    config = LLDB_PRESETS.get(preset, LLDBConfig())
    return LLDBAdapter(config)


def check_lldb_installation() -> Dict[str, Any]:
    """
    检查 LLDB 安装状态
    
    Returns:
        检查结果
    """
    adapter = LLDBAdapter()
    dap_path = adapter.find_lldb_dap()
    
    result = {
        "available": dap_path is not None,
        "dap_path": dap_path,
        "version": None,
        "lldb_path": None,
    }
    
    if dap_path:
        result["version"] = adapter.get_version()
    
    # 检查 lldb 命令
    lldb_path = shutil.which("lldb")
    if lldb_path:
        result["lldb_path"] = lldb_path
    
    return result

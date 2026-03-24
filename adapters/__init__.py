"""
Magic Debug Adapters Package
"""

from .lldb import LLDBAdapter, LLDBConfig, check_lldb_installation

__all__ = [
    "LLDBAdapter",
    "LLDBConfig",
    "check_lldb_installation",
]

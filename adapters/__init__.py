"""
Magic Debug Adapters Package
"""

from .gdb import GDBAdapter, GDBConfig, check_gdb_installation

__all__ = [
    "GDBAdapter",
    "GDBConfig",
    "check_gdb_installation",
]
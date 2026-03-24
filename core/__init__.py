"""
Magic Debug Core Package
"""

from .session import DebugSession, SessionManager
from .dap import DAPClient, DAPError
from .state import DebugState, DebugStatus
from .controller import DebugController, DebugConfig

__all__ = [
    "DebugSession",
    "SessionManager",
    "DAPClient",
    "DAPError",
    "DebugState",
    "DebugStatus",
    "DebugController",
    "DebugConfig",
]

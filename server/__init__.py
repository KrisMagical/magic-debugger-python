"""
Magic Debug Server Package
"""

from .rpc import RPCServer, RPCClient
from .http import HTTPAPIServer

__all__ = [
    "RPCServer",
    "RPCClient",
    "HTTPAPIServer",
]

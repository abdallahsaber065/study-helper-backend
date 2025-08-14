"""
WebSocket module for real-time communications.
"""

from .manager import ConnectionManager, websocket_manager
from .routes import router

__all__ = ["ConnectionManager", "websocket_manager", "router"]

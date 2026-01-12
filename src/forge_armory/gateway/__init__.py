"""Gateway layer for connecting to backend MCP servers."""

from forge_armory.gateway.connection import BackendConnection
from forge_armory.gateway.exceptions import (
    BackendConnectionError,
    BackendNotFoundError,
    GatewayError,
    ToolCallError,
    ToolNotFoundError,
)
from forge_armory.gateway.manager import BackendManager, RequestContext

__all__ = [
    "BackendConnection",
    "BackendManager",
    "RequestContext",
    "GatewayError",
    "BackendNotFoundError",
    "BackendConnectionError",
    "ToolNotFoundError",
    "ToolCallError",
]

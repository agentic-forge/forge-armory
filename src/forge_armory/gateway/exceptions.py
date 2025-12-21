"""Gateway exceptions."""


class GatewayError(Exception):
    """Base exception for gateway errors."""


class BackendNotFoundError(GatewayError):
    """Backend not found in active connections."""


class BackendConnectionError(GatewayError):
    """Failed to connect to backend."""


class ToolNotFoundError(GatewayError):
    """Tool not found in registry (database)."""


class ToolCallError(GatewayError):
    """Failed to call tool on backend."""

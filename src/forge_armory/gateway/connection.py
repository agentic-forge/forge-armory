"""Single backend MCP client connection."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastmcp import Client

from forge_armory.db import Backend, ToolInfo
from forge_armory.gateway.exceptions import BackendConnectionError

if TYPE_CHECKING:
    from mcp.types import Tool as MCPTool


class BackendConnection:
    """Wrapper for a single MCP backend client.

    Handles connection lifecycle and tool operations for one backend.
    """

    def __init__(self, backend: Backend) -> None:
        self.backend = backend
        self._client: Client | None = None

    @property
    def name(self) -> str:
        """Backend name."""
        return self.backend.name

    @property
    def is_connected(self) -> bool:
        """Check if client is initialized."""
        return self._client is not None

    async def connect(self) -> None:
        """Establish connection to the backend MCP server.

        Creates the client and verifies connectivity with a ping.
        Note: Only HTTP URLs are currently supported. Stdio transports are not yet implemented.
        """
        if not self.backend.url:
            raise BackendConnectionError(f"Backend {self.name} has no url configured")

        self._client = Client(self.backend.url)

        # Test connection by pinging
        try:
            async with self._client:
                await self._client.ping()
        except Exception as e:
            self._client = None
            raise BackendConnectionError(f"Failed to connect to {self.name}: {e}") from e

    async def disconnect(self) -> None:
        """Close connection."""
        self._client = None

    async def list_tools(self) -> list[ToolInfo]:
        """Fetch available tools from this backend.

        Returns:
            List of ToolInfo with tool metadata.

        Raises:
            BackendConnectionError: If not connected.
        """
        if not self._client:
            raise BackendConnectionError(f"Backend {self.name} not connected")

        async with self._client as client:
            tools: list[MCPTool] = await client.list_tools()
            return [
                ToolInfo(
                    name=tool.name,
                    description=tool.description,
                    input_schema=tool.inputSchema,
                )
                for tool in tools
            ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Call a tool on this backend.

        Args:
            name: Original tool name (not prefixed).
            arguments: Tool arguments.

        Returns:
            Tool result.

        Raises:
            BackendConnectionError: If not connected.
        """
        if not self._client:
            raise BackendConnectionError(f"Backend {self.name} not connected")

        async with self._client as client:
            return await client.call_tool(name, arguments)

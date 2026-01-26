"""Single backend MCP client connection with session support."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from forge_armory.db import Backend, ToolInfo
from forge_armory.gateway.exceptions import BackendConnectionError
from forge_armory.gateway.session import (
    MCPSessionError,
    SessionState,
    call_tool_with_session,
    initialize_session,
    list_tools_with_session,
    refresh_session,
)

logger = logging.getLogger(__name__)


class BackendConnection:
    """Wrapper for a single MCP backend client with session support.

    Handles connection lifecycle, session management, and tool operations
    for one backend. Uses direct HTTP requests to support the MCP Streamable
    HTTP protocol with session IDs.
    """

    def __init__(self, backend: Backend) -> None:
        self.backend = backend
        self._client: httpx.AsyncClient | None = None
        self._session_state: SessionState | None = None

    @property
    def name(self) -> str:
        """Backend name."""
        return self.backend.name

    @property
    def is_connected(self) -> bool:
        """Check if client is initialized and session is ready."""
        return self._client is not None and self._session_state is not None

    @property
    def session_id(self) -> str | None:
        """Get current session ID."""
        return self._session_state.session_id if self._session_state else None

    @property
    def requires_session(self) -> bool:
        """Check if backend requires session management."""
        return self._session_state.requires_session if self._session_state else False

    async def connect(self) -> None:
        """Establish connection to the backend MCP server.

        Performs the full MCP initialization handshake:
        1. Creates an httpx AsyncClient
        2. Sends `initialize` request
        3. Captures session ID from response headers (if any)
        4. Sends `notifications/initialized` (if session-based)

        Note: Only HTTP URLs are currently supported.
        """
        if not self.backend.url:
            raise BackendConnectionError(f"Backend {self.name} has no url configured")

        # Create persistent HTTP client
        self._client = httpx.AsyncClient(follow_redirects=True)

        try:
            # Initialize MCP session
            self._session_state = await initialize_session(self.backend, self._client)

            # Update backend model with session state
            self.backend.session_id = self._session_state.session_id
            self.backend.session_initialized = self._session_state.initialized
            self.backend.requires_session = self._session_state.requires_session

            logger.info(
                "Connected to backend %s (session: %s)",
                self.name,
                "required" if self._session_state.requires_session else "not required",
            )
        except MCPSessionError as e:
            await self._cleanup()
            raise BackendConnectionError(f"Failed to connect to {self.name}: {e}") from e
        except Exception as e:
            await self._cleanup()
            raise BackendConnectionError(f"Failed to connect to {self.name}: {e}") from e

    async def _cleanup(self) -> None:
        """Clean up client resources."""
        if self._client:
            await self._client.aclose()
            self._client = None
        self._session_state = None

    async def disconnect(self) -> None:
        """Close connection and clear session state."""
        await self._cleanup()
        # Clear session state on backend model
        self.backend.session_id = None
        self.backend.session_initialized = False
        logger.debug("Disconnected from backend %s", self.name)

    async def _refresh_session(self) -> None:
        """Refresh the session if it has expired."""
        if not self._client:
            raise BackendConnectionError(f"Backend {self.name} not connected")

        self._session_state = await refresh_session(self.backend, self._client)
        self.backend.session_id = self._session_state.session_id
        self.backend.session_initialized = self._session_state.initialized

    async def list_tools(self) -> list[ToolInfo]:
        """Fetch available tools from this backend.

        Returns:
            List of ToolInfo with tool metadata.

        Raises:
            BackendConnectionError: If not connected or request fails.
        """
        if not self._client or not self._session_state:
            raise BackendConnectionError(f"Backend {self.name} not connected")

        try:
            response = await list_tools_with_session(
                self.backend,
                self._session_state.session_id,
                self._client,
            )
        except MCPSessionError as e:
            # Try refreshing session and retrying once
            if "session" in str(e).lower():
                await self._refresh_session()
                response = await list_tools_with_session(
                    self.backend,
                    self._session_state.session_id,
                    self._client,
                )
            else:
                raise BackendConnectionError(f"Failed to list tools: {e}") from e

        # Extract tools from response
        if "error" in response:
            raise BackendConnectionError(
                f"Backend returned error: {response['error']}"
            )

        tools_data = response.get("result", {}).get("tools", [])
        return [
            ToolInfo(
                name=tool["name"],
                description=tool.get("description"),
                input_schema=tool.get("inputSchema", {}),
            )
            for tool in tools_data
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Call a tool on this backend with automatic session retry.

        Args:
            name: Original tool name (not prefixed).
            arguments: Tool arguments.

        Returns:
            Tool result.

        Raises:
            BackendConnectionError: If not connected or call fails.
        """
        if not self._client or not self._session_state:
            raise BackendConnectionError(f"Backend {self.name} not connected")

        try:
            response = await call_tool_with_session(
                self.backend,
                name,
                arguments,
                self._session_state.session_id,
                self._client,
            )
        except MCPSessionError as e:
            # Check if this is a session expiry error
            if "session" in str(e).lower():
                logger.info("Session expired for %s, refreshing...", self.name)
                await self._refresh_session()
                # Retry the call with new session
                response = await call_tool_with_session(
                    self.backend,
                    name,
                    arguments,
                    self._session_state.session_id,
                    self._client,
                )
            else:
                raise BackendConnectionError(f"Tool call failed: {e}") from e

        # Check for JSON-RPC error
        if "error" in response:
            error = response["error"]
            raise BackendConnectionError(
                f"Tool call returned error: {error.get('message', error)}"
            )

        return response.get("result")

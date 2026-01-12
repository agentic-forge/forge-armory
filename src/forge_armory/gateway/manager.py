"""Backend connection manager."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from forge_armory.db import (
    Backend,
    BackendRepository,
    Tool,
    ToolCallCreate,
    ToolCallRepository,
    ToolInfo,
    ToolRepository,
)
from forge_armory.gateway.connection import BackendConnection
from forge_armory.gateway.exceptions import (
    BackendNotFoundError,
    ToolCallError,
    ToolNotFoundError,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)


@dataclass
class RequestContext:
    """Context information about the incoming request.

    Used to track where tool calls originate from.
    """

    client_ip: str | None = None
    request_id: str | None = None
    session_id: str | None = None
    caller: str | None = None


class BackendManager:
    """Manages active connections to backend MCP servers.

    - Reads configurations from database
    - Maintains runtime connections
    - Routes tool calls to correct backend
    - Records metrics
    """

    def __init__(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        self._session_maker = session_maker
        self._connections: dict[str, BackendConnection] = {}

    @property
    def connected_backends(self) -> list[str]:
        """List of connected backend names."""
        return list(self._connections.keys())

    async def initialize(self) -> None:
        """Load enabled backends from DB and connect to all."""
        async with self._session_maker() as session:
            repo = BackendRepository(session)
            backends = await repo.list_all(enabled_only=True)

            for backend in backends:
                try:
                    await self._connect_backend(backend)
                    logger.info("Connected to backend: %s", backend.name)
                except Exception as e:
                    # Log error but continue with other backends
                    logger.error("Failed to connect to %s: %s", backend.name, e)

    async def shutdown(self) -> None:
        """Disconnect all backends."""
        for name in list(self._connections.keys()):
            await self.remove_backend(name)
        logger.info("All backends disconnected")

    async def _connect_backend(self, backend: Backend) -> BackendConnection:
        """Internal: Create connection and add to active connections."""
        conn = BackendConnection(backend)
        await conn.connect()
        self._connections[backend.name] = conn
        return conn

    async def add_backend(self, backend: Backend) -> list[ToolInfo]:
        """Connect to a backend and refresh its tools in the database.

        Args:
            backend: Backend configuration from database.

        Returns:
            List of tools from the backend.
        """
        # Connect
        conn = await self._connect_backend(backend)

        # Fetch tools from backend
        tools = await conn.list_tools()

        # Save tools to database
        async with self._session_maker() as session:
            tool_repo = ToolRepository(session)
            await tool_repo.refresh_backend_tools(backend, tools)
            await session.commit()

        logger.info("Added backend %s with %d tools", backend.name, len(tools))
        return tools

    async def remove_backend(self, name: str) -> None:
        """Disconnect and remove a backend."""
        if name in self._connections:
            await self._connections[name].disconnect()
            del self._connections[name]
            logger.info("Removed backend: %s", name)

    async def refresh_backend(self, name: str) -> list[ToolInfo]:
        """Re-fetch tools from a backend and update database.

        Backend must already be connected.

        Args:
            name: Backend name.

        Returns:
            Updated list of tools.

        Raises:
            BackendNotFoundError: If backend not connected or not in database.
        """
        if name not in self._connections:
            raise BackendNotFoundError(f"Backend {name} not connected")

        conn = self._connections[name]
        tools = await conn.list_tools()

        async with self._session_maker() as session:
            backend_repo = BackendRepository(session)
            backend = await backend_repo.get_by_name(name)
            if not backend:
                raise BackendNotFoundError(f"Backend {name} not in database")

            tool_repo = ToolRepository(session)
            await tool_repo.refresh_backend_tools(backend, tools)
            await session.commit()

        logger.info("Refreshed backend %s with %d tools", name, len(tools))
        return tools

    async def get_tool(self, prefixed_name: str) -> Tool | None:
        """Look up a tool in the database by prefixed name."""
        async with self._session_maker() as session:
            repo = ToolRepository(session)
            return await repo.get_by_prefixed_name(prefixed_name)

    async def list_tools(self) -> list[Tool]:
        """List all tools from database."""
        async with self._session_maker() as session:
            repo = ToolRepository(session)
            return await repo.list_all()

    async def call_tool(
        self,
        prefixed_name: str,
        arguments: dict[str, Any],
        context: RequestContext | None = None,
    ) -> Any:
        """Route a tool call to the correct backend.

        1. Look up tool in DB by prefixed_name
        2. Find the backend connection
        3. Call the tool with original name
        4. Record metrics in DB

        Args:
            prefixed_name: Prefixed tool name (e.g., "weather__get_forecast").
            arguments: Tool arguments.
            context: Optional request context for tracking origin.

        Returns:
            Tool result.

        Raises:
            ToolNotFoundError: If tool not in database.
            BackendNotFoundError: If backend not connected.
            ToolCallError: If tool call fails.
        """
        start_time = time.perf_counter()

        # Look up tool in database
        async with self._session_maker() as session:
            tool_repo = ToolRepository(session)
            tool = await tool_repo.get_by_prefixed_name(prefixed_name)

            if not tool:
                raise ToolNotFoundError(f"Tool {prefixed_name} not found")

            # Get backend name from tool's backend relationship
            backend_repo = BackendRepository(session)
            backend = await backend_repo.get_by_id(tool.backend_id)
            if not backend:
                raise BackendNotFoundError(f"Backend for tool {prefixed_name} not found")

            backend_name = backend.name
            original_tool_name = tool.name
            tool_id = tool.id

        # Check connection exists
        if backend_name not in self._connections:
            raise BackendNotFoundError(f"Backend {backend_name} not connected")

        conn = self._connections[backend_name]

        # Call the tool
        success = True
        error_message: str | None = None
        result = None

        try:
            result = await conn.call_tool(original_tool_name, arguments)
        except Exception as e:
            success = False
            error_message = str(e)
            raise ToolCallError(f"Tool call failed: {e}") from e
        finally:
            # Record metrics
            latency_ms = int((time.perf_counter() - start_time) * 1000)

            async with self._session_maker() as session:
                call_repo = ToolCallRepository(session)
                await call_repo.create(
                    ToolCallCreate(
                        backend_name=backend_name,
                        tool_name=original_tool_name,
                        arguments=arguments,
                        success=success,
                        error_message=error_message,
                        latency_ms=latency_ms,
                        client_ip=context.client_ip if context else None,
                        request_id=context.request_id if context else None,
                        session_id=context.session_id if context else None,
                        caller=context.caller if context else None,
                    ),
                    tool_id=tool_id,
                )
                await session.commit()

        return result

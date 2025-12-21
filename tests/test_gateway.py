"""Tests for the gateway layer."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from forge_armory.db.models import Backend, Base
from forge_armory.db.repository import (
    BackendCreate,
    BackendRepository,
    ToolCallRepository,
    ToolInfo,
    ToolRepository,
)
from forge_armory.gateway import (
    BackendConnection,
    BackendConnectionError,
    BackendManager,
    BackendNotFoundError,
    ToolCallError,
    ToolNotFoundError,
)


@pytest.fixture
async def async_session() -> AsyncSession:
    """Create an in-memory SQLite database for testing."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with maker() as session:
        yield session

    await engine.dispose()


@pytest.fixture
async def session_maker() -> async_sessionmaker[AsyncSession]:
    """Create a session maker for BackendManager tests."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    yield maker

    await engine.dispose()


@pytest.fixture
def mock_backend() -> Backend:
    """Create a mock backend for testing."""
    return Backend(
        name="weather",
        url="http://localhost:8000/mcp",
        enabled=True,
        timeout=30.0,
    )


class TestBackendConnection:
    """Tests for BackendConnection."""

    def test_name_property(self, mock_backend: Backend) -> None:
        """Connection exposes backend name."""
        conn = BackendConnection(mock_backend)
        assert conn.name == "weather"

    def test_is_connected_initially_false(self, mock_backend: Backend) -> None:
        """Connection is not connected initially."""
        conn = BackendConnection(mock_backend)
        assert conn.is_connected is False

    async def test_connect_with_url(self, mock_backend: Backend) -> None:
        """Connection can connect using URL."""
        conn = BackendConnection(mock_backend)

        with patch("forge_armory.gateway.connection.Client") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.ping = AsyncMock()

            await conn.connect()

            assert conn.is_connected is True
            mock_client_class.assert_called_once_with("http://localhost:8000/mcp")
            mock_client.ping.assert_called_once()

    async def test_connect_no_url_raises(self) -> None:
        """Connection raises if backend has no url configured."""
        backend = Backend(name="invalid", enabled=True, timeout=30.0)
        conn = BackendConnection(backend)

        with pytest.raises(BackendConnectionError, match="no url configured"):
            await conn.connect()

    async def test_connect_failure_raises(self, mock_backend: Backend) -> None:
        """Connection raises on connection failure."""
        conn = BackendConnection(mock_backend)

        with patch("forge_armory.gateway.connection.Client") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.ping = AsyncMock(side_effect=ConnectionError("Connection refused"))

            with pytest.raises(BackendConnectionError, match="Failed to connect"):
                await conn.connect()

            assert conn.is_connected is False

    async def test_disconnect(self, mock_backend: Backend) -> None:
        """Connection can disconnect."""
        conn = BackendConnection(mock_backend)

        with patch("forge_armory.gateway.connection.Client") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.ping = AsyncMock()

            await conn.connect()
            assert conn.is_connected is True

            await conn.disconnect()
            assert conn.is_connected is False

    async def test_list_tools(self, mock_backend: Backend) -> None:
        """Connection can list tools from backend."""
        conn = BackendConnection(mock_backend)

        with patch("forge_armory.gateway.connection.Client") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.ping = AsyncMock()

            # Mock list_tools response
            mock_tool = MagicMock()
            mock_tool.name = "get_forecast"
            mock_tool.description = "Get weather forecast"
            mock_tool.inputSchema = {"type": "object"}
            mock_client.list_tools = AsyncMock(return_value=[mock_tool])

            await conn.connect()
            tools = await conn.list_tools()

            assert len(tools) == 1
            assert tools[0].name == "get_forecast"
            assert tools[0].description == "Get weather forecast"
            assert tools[0].input_schema == {"type": "object"}

    async def test_list_tools_not_connected_raises(self, mock_backend: Backend) -> None:
        """list_tools raises if not connected."""
        conn = BackendConnection(mock_backend)

        with pytest.raises(BackendConnectionError, match="not connected"):
            await conn.list_tools()

    async def test_call_tool(self, mock_backend: Backend) -> None:
        """Connection can call a tool."""
        conn = BackendConnection(mock_backend)

        with patch("forge_armory.gateway.connection.Client") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.ping = AsyncMock()
            mock_client.call_tool = AsyncMock(return_value={"temperature": 20})

            await conn.connect()
            result = await conn.call_tool("get_forecast", {"city": "London"})

            assert result == {"temperature": 20}
            mock_client.call_tool.assert_called_once_with("get_forecast", {"city": "London"})

    async def test_call_tool_not_connected_raises(self, mock_backend: Backend) -> None:
        """call_tool raises if not connected."""
        conn = BackendConnection(mock_backend)

        with pytest.raises(BackendConnectionError, match="not connected"):
            await conn.call_tool("get_forecast", {})


class TestBackendManager:
    """Tests for BackendManager."""

    async def test_connected_backends_initially_empty(
        self, session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """Manager starts with no connected backends."""
        manager = BackendManager(session_maker)
        assert manager.connected_backends == []

    async def test_add_backend(
        self, session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """Manager can add a backend and refresh its tools."""
        # Create backend in DB
        async with session_maker() as session:
            repo = BackendRepository(session)
            backend = await repo.create(
                BackendCreate(name="weather", url="http://localhost:8000/mcp")
            )
            await session.commit()

        manager = BackendManager(session_maker)

        with (
            patch.object(BackendConnection, "connect", new_callable=AsyncMock) as mock_connect,
            patch.object(BackendConnection, "list_tools", new_callable=AsyncMock) as mock_list,
        ):
            mock_list.return_value = [
                ToolInfo(name="get_forecast", description="Get forecast", input_schema={})
            ]

            tools = await manager.add_backend(backend)

            mock_connect.assert_called_once()
            mock_list.assert_called_once()
            assert len(tools) == 1
            assert "weather" in manager.connected_backends

        # Verify tools were saved to DB
        async with session_maker() as session:
            tool_repo = ToolRepository(session)
            db_tools = await tool_repo.list_all()
            assert len(db_tools) == 1
            assert db_tools[0].prefixed_name == "weather__get_forecast"

    async def test_remove_backend(
        self, session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """Manager can remove a backend."""
        async with session_maker() as session:
            repo = BackendRepository(session)
            backend = await repo.create(
                BackendCreate(name="weather", url="http://localhost:8000/mcp")
            )
            await session.commit()

        manager = BackendManager(session_maker)

        with (
            patch.object(BackendConnection, "connect", new_callable=AsyncMock),
            patch.object(BackendConnection, "list_tools", new_callable=AsyncMock) as mock_list,
        ):
            mock_list.return_value = []
            await manager.add_backend(backend)

        assert "weather" in manager.connected_backends

        await manager.remove_backend("weather")
        assert "weather" not in manager.connected_backends

    async def test_refresh_backend(
        self, session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """Manager can refresh a backend's tools."""
        async with session_maker() as session:
            repo = BackendRepository(session)
            backend = await repo.create(
                BackendCreate(name="weather", url="http://localhost:8000/mcp")
            )
            await session.commit()

        manager = BackendManager(session_maker)

        with (
            patch.object(BackendConnection, "connect", new_callable=AsyncMock),
            patch.object(BackendConnection, "list_tools", new_callable=AsyncMock) as mock_list,
        ):
            # Initial add
            mock_list.return_value = [ToolInfo(name="old_tool", input_schema={})]
            await manager.add_backend(backend)

            # Refresh with new tools
            mock_list.return_value = [ToolInfo(name="new_tool", input_schema={})]
            tools = await manager.refresh_backend("weather")

        assert len(tools) == 1
        assert tools[0].name == "new_tool"

        # Verify DB was updated
        async with session_maker() as session:
            tool_repo = ToolRepository(session)
            db_tools = await tool_repo.list_all()
            assert len(db_tools) == 1
            assert db_tools[0].name == "new_tool"

    async def test_refresh_backend_not_connected_raises(
        self, session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """refresh_backend raises if backend not connected."""
        manager = BackendManager(session_maker)

        with pytest.raises(BackendNotFoundError, match="not connected"):
            await manager.refresh_backend("nonexistent")

    async def test_get_tool(
        self, session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """Manager can get a tool by prefixed name."""
        async with session_maker() as session:
            repo = BackendRepository(session)
            backend = await repo.create(
                BackendCreate(name="weather", url="http://localhost:8000/mcp")
            )
            await session.commit()

        manager = BackendManager(session_maker)

        with (
            patch.object(BackendConnection, "connect", new_callable=AsyncMock),
            patch.object(BackendConnection, "list_tools", new_callable=AsyncMock) as mock_list,
        ):
            mock_list.return_value = [ToolInfo(name="get_forecast", input_schema={})]
            await manager.add_backend(backend)

        tool = await manager.get_tool("weather__get_forecast")
        assert tool is not None
        assert tool.name == "get_forecast"

        missing = await manager.get_tool("nonexistent__tool")
        assert missing is None

    async def test_list_tools(
        self, session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """Manager can list all tools."""
        async with session_maker() as session:
            repo = BackendRepository(session)
            backend = await repo.create(
                BackendCreate(name="weather", url="http://localhost:8000/mcp")
            )
            await session.commit()

        manager = BackendManager(session_maker)

        with (
            patch.object(BackendConnection, "connect", new_callable=AsyncMock),
            patch.object(BackendConnection, "list_tools", new_callable=AsyncMock) as mock_list,
        ):
            mock_list.return_value = [
                ToolInfo(name="get_forecast", input_schema={}),
                ToolInfo(name="get_current", input_schema={}),
            ]
            await manager.add_backend(backend)

        tools = await manager.list_tools()
        assert len(tools) == 2

    async def test_call_tool(
        self, session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """Manager can call a tool and record metrics."""
        async with session_maker() as session:
            repo = BackendRepository(session)
            backend = await repo.create(
                BackendCreate(name="weather", url="http://localhost:8000/mcp")
            )
            await session.commit()

        manager = BackendManager(session_maker)

        with (
            patch.object(BackendConnection, "connect", new_callable=AsyncMock),
            patch.object(BackendConnection, "list_tools", new_callable=AsyncMock) as mock_list,
        ):
            mock_list.return_value = [ToolInfo(name="get_forecast", input_schema={})]
            await manager.add_backend(backend)

        with patch.object(BackendConnection, "call_tool", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {"temperature": 20}

            result = await manager.call_tool("weather__get_forecast", {"city": "London"})

            assert result == {"temperature": 20}
            mock_call.assert_called_once_with("get_forecast", {"city": "London"})

        # Verify metrics were recorded
        async with session_maker() as session:
            call_repo = ToolCallRepository(session)
            calls = await call_repo.list_recent()
            assert len(calls) == 1
            assert calls[0].tool_name == "get_forecast"
            assert calls[0].success is True

    async def test_call_tool_not_found_raises(
        self, session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """call_tool raises if tool not in database."""
        manager = BackendManager(session_maker)

        with pytest.raises(ToolNotFoundError, match="not found"):
            await manager.call_tool("nonexistent__tool", {})

    async def test_call_tool_backend_not_connected_raises(
        self, session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """call_tool raises if backend not connected."""
        # Create backend and tool in DB, but don't connect
        async with session_maker() as session:
            backend_repo = BackendRepository(session)
            backend = await backend_repo.create(
                BackendCreate(name="weather", url="http://localhost:8000/mcp")
            )
            tool_repo = ToolRepository(session)
            await tool_repo.refresh_backend_tools(
                backend, [ToolInfo(name="get_forecast", input_schema={})]
            )
            await session.commit()

        manager = BackendManager(session_maker)

        with pytest.raises(BackendNotFoundError, match="not connected"):
            await manager.call_tool("weather__get_forecast", {})

    async def test_call_tool_failure_records_error(
        self, session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """call_tool records error in metrics on failure."""
        async with session_maker() as session:
            repo = BackendRepository(session)
            backend = await repo.create(
                BackendCreate(name="weather", url="http://localhost:8000/mcp")
            )
            await session.commit()

        manager = BackendManager(session_maker)

        with (
            patch.object(BackendConnection, "connect", new_callable=AsyncMock),
            patch.object(BackendConnection, "list_tools", new_callable=AsyncMock) as mock_list,
        ):
            mock_list.return_value = [ToolInfo(name="get_forecast", input_schema={})]
            await manager.add_backend(backend)

        with patch.object(BackendConnection, "call_tool", new_callable=AsyncMock) as mock_call:
            mock_call.side_effect = Exception("Backend error")

            with pytest.raises(ToolCallError, match="Tool call failed"):
                await manager.call_tool("weather__get_forecast", {})

        # Verify error was recorded
        async with session_maker() as session:
            call_repo = ToolCallRepository(session)
            calls = await call_repo.list_recent()
            assert len(calls) == 1
            assert calls[0].success is False
            assert "Backend error" in calls[0].error_message

    async def test_initialize(
        self, session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """Manager can initialize from database."""
        # Create enabled and disabled backends
        async with session_maker() as session:
            repo = BackendRepository(session)
            await repo.create(
                BackendCreate(name="weather", url="http://localhost:8000/mcp", enabled=True)
            )
            await repo.create(
                BackendCreate(name="disabled", url="http://localhost:8001/mcp", enabled=False)
            )
            await session.commit()

        manager = BackendManager(session_maker)

        with (
            patch.object(BackendConnection, "connect", new_callable=AsyncMock),
            patch.object(BackendConnection, "list_tools", new_callable=AsyncMock) as mock_list,
        ):
            mock_list.return_value = []
            await manager.initialize()

        # Only enabled backend should be connected
        assert "weather" in manager.connected_backends
        assert "disabled" not in manager.connected_backends

    async def test_shutdown(
        self, session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """Manager can shutdown all connections."""
        async with session_maker() as session:
            repo = BackendRepository(session)
            backend = await repo.create(
                BackendCreate(name="weather", url="http://localhost:8000/mcp")
            )
            await session.commit()

        manager = BackendManager(session_maker)

        with (
            patch.object(BackendConnection, "connect", new_callable=AsyncMock),
            patch.object(BackendConnection, "list_tools", new_callable=AsyncMock) as mock_list,
        ):
            mock_list.return_value = []
            await manager.add_backend(backend)

        assert len(manager.connected_backends) == 1

        await manager.shutdown()
        assert len(manager.connected_backends) == 0

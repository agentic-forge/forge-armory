"""Tests for the database layer."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from forge_armory.db.models import Backend, Base
from forge_armory.db.repository import (
    BackendCreate,
    BackendRepository,
    BackendUpdate,
    ToolCallCreate,
    ToolCallRepository,
    ToolInfo,
    ToolRepository,
)


@pytest.fixture
async def async_session() -> AsyncSession:
    """Create an in-memory SQLite database for testing."""
    # Use SQLite for testing (faster, no external dependencies)
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_maker() as session:
        yield session

    await engine.dispose()


class TestBackendModel:
    """Tests for Backend model."""

    async def test_create_backend(self, async_session: AsyncSession) -> None:
        """Backend can be created with required fields."""
        backend = Backend(
            name="weather",
            url="http://localhost:8000/mcp",
            enabled=True,
            timeout=30.0,
        )
        async_session.add(backend)
        await async_session.flush()

        assert backend.id is not None
        assert backend.name == "weather"
        assert backend.url == "http://localhost:8000/mcp"
        assert backend.enabled is True

    def test_effective_prefix_uses_name(self) -> None:
        """Effective prefix defaults to name when prefix is None."""
        backend = Backend(name="weather", url="http://localhost:8000/mcp")
        assert backend.effective_prefix == "weather"

    def test_effective_prefix_uses_custom(self) -> None:
        """Effective prefix uses custom prefix when set."""
        backend = Backend(
            name="weather",
            url="http://localhost:8000/mcp",
            prefix="wx",
        )
        assert backend.effective_prefix == "wx"


class TestBackendRepository:
    """Tests for BackendRepository."""

    async def test_create_backend(self, async_session: AsyncSession) -> None:
        """Repository can create a backend."""
        repo = BackendRepository(async_session)
        data = BackendCreate(
            name="weather",
            url="http://localhost:8000/mcp",
        )

        backend = await repo.create(data)

        assert backend.id is not None
        assert backend.name == "weather"
        assert backend.url == "http://localhost:8000/mcp"
        assert backend.enabled is True

    async def test_get_by_name(self, async_session: AsyncSession) -> None:
        """Repository can get backend by name."""
        repo = BackendRepository(async_session)
        await repo.create(BackendCreate(name="weather", url="http://localhost:8000/mcp"))

        backend = await repo.get_by_name("weather")

        assert backend is not None
        assert backend.name == "weather"

    async def test_get_by_name_not_found(self, async_session: AsyncSession) -> None:
        """Repository returns None for non-existent backend."""
        repo = BackendRepository(async_session)

        backend = await repo.get_by_name("nonexistent")

        assert backend is None

    async def test_list_all(self, async_session: AsyncSession) -> None:
        """Repository can list all backends."""
        repo = BackendRepository(async_session)
        await repo.create(BackendCreate(name="weather", url="http://localhost:8000/mcp"))
        await repo.create(BackendCreate(name="search", url="http://localhost:8001/mcp"))

        backends = await repo.list_all()

        assert len(backends) == 2
        names = {b.name for b in backends}
        assert names == {"weather", "search"}

    async def test_list_all_enabled_only(self, async_session: AsyncSession) -> None:
        """Repository can filter by enabled status."""
        repo = BackendRepository(async_session)
        await repo.create(BackendCreate(name="weather", url="http://localhost:8000/mcp"))
        await repo.create(
            BackendCreate(name="search", url="http://localhost:8001/mcp", enabled=False)
        )

        backends = await repo.list_all(enabled_only=True)

        assert len(backends) == 1
        assert backends[0].name == "weather"

    async def test_update_backend(self, async_session: AsyncSession) -> None:
        """Repository can update a backend."""
        repo = BackendRepository(async_session)
        await repo.create(BackendCreate(name="weather", url="http://localhost:8000/mcp"))

        backend = await repo.update("weather", BackendUpdate(timeout=60.0))

        assert backend is not None
        assert backend.timeout == 60.0

    async def test_delete_backend(self, async_session: AsyncSession) -> None:
        """Repository can delete a backend."""
        repo = BackendRepository(async_session)
        await repo.create(BackendCreate(name="weather", url="http://localhost:8000/mcp"))

        result = await repo.delete("weather")
        assert result is True

        backend = await repo.get_by_name("weather")
        assert backend is None

    async def test_set_enabled(self, async_session: AsyncSession) -> None:
        """Repository can enable/disable a backend."""
        repo = BackendRepository(async_session)
        await repo.create(BackendCreate(name="weather", url="http://localhost:8000/mcp"))

        backend = await repo.set_enabled("weather", False)

        assert backend is not None
        assert backend.enabled is False


class TestToolRepository:
    """Tests for ToolRepository."""

    async def test_refresh_backend_tools(self, async_session: AsyncSession) -> None:
        """Repository can refresh tools for a backend."""
        backend_repo = BackendRepository(async_session)
        tool_repo = ToolRepository(async_session)

        backend = await backend_repo.create(
            BackendCreate(name="weather", url="http://localhost:8000/mcp")
        )

        tools = [
            ToolInfo(name="get_forecast", description="Get forecast", input_schema={}),
            ToolInfo(name="get_current", description="Get current", input_schema={}),
        ]

        result = await tool_repo.refresh_backend_tools(backend, tools)

        assert len(result) == 2
        names = {t.prefixed_name for t in result}
        assert names == {"weather__get_forecast", "weather__get_current"}

    async def test_refresh_replaces_existing_tools(self, async_session: AsyncSession) -> None:
        """Refreshing tools replaces existing tools."""
        backend_repo = BackendRepository(async_session)
        tool_repo = ToolRepository(async_session)

        backend = await backend_repo.create(
            BackendCreate(name="weather", url="http://localhost:8000/mcp")
        )

        # First refresh
        await tool_repo.refresh_backend_tools(
            backend,
            [ToolInfo(name="old_tool", input_schema={})],
        )

        # Second refresh
        await tool_repo.refresh_backend_tools(
            backend,
            [ToolInfo(name="new_tool", input_schema={})],
        )

        tools = await tool_repo.list_by_backend(backend.id)
        assert len(tools) == 1
        assert tools[0].name == "new_tool"

    async def test_get_by_prefixed_name(self, async_session: AsyncSession) -> None:
        """Repository can get tool by prefixed name."""
        backend_repo = BackendRepository(async_session)
        tool_repo = ToolRepository(async_session)

        backend = await backend_repo.create(
            BackendCreate(name="weather", url="http://localhost:8000/mcp")
        )
        await tool_repo.refresh_backend_tools(
            backend,
            [ToolInfo(name="get_forecast", input_schema={})],
        )

        tool = await tool_repo.get_by_prefixed_name("weather__get_forecast")

        assert tool is not None
        assert tool.name == "get_forecast"


class TestToolCallRepository:
    """Tests for ToolCallRepository."""

    async def test_create_tool_call(self, async_session: AsyncSession) -> None:
        """Repository can record a tool call."""
        repo = ToolCallRepository(async_session)
        data = ToolCallCreate(
            backend_name="weather",
            tool_name="get_forecast",
            arguments={"city": "London"},
            success=True,
            latency_ms=150,
        )

        tool_call = await repo.create(data)

        assert tool_call.id is not None
        assert tool_call.backend_name == "weather"
        assert tool_call.success is True

    async def test_list_recent(self, async_session: AsyncSession) -> None:
        """Repository can list recent tool calls."""
        repo = ToolCallRepository(async_session)

        for i in range(5):
            await repo.create(
                ToolCallCreate(
                    backend_name="weather",
                    tool_name=f"tool_{i}",
                    arguments={},
                    success=True,
                    latency_ms=100,
                )
            )

        calls = await repo.list_recent(limit=3)
        assert len(calls) == 3

    async def test_get_stats(self, async_session: AsyncSession) -> None:
        """Repository can get call statistics."""
        repo = ToolCallRepository(async_session)

        # Create some successful calls
        for _ in range(3):
            await repo.create(
                ToolCallCreate(
                    backend_name="weather",
                    tool_name="get_forecast",
                    arguments={},
                    success=True,
                    latency_ms=100,
                )
            )

        # Create some failed calls
        await repo.create(
            ToolCallCreate(
                backend_name="weather",
                tool_name="get_forecast",
                arguments={},
                success=False,
                error_message="Connection refused",
                latency_ms=50,
            )
        )

        stats = await repo.get_stats()

        assert stats["total_calls"] == 4
        assert stats["success_count"] == 3
        assert stats["error_count"] == 1
        assert stats["success_rate"] == 0.75

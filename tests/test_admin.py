"""Tests for the Admin API."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from starlette.applications import Starlette
from starlette.testclient import TestClient

from forge_armory.admin import get_admin_routes
from forge_armory.db.models import Base
from forge_armory.db.repository import (
    BackendCreate,
    BackendRepository,
    ToolCallCreate,
    ToolCallRepository,
    ToolInfo,
    ToolRepository,
)
from forge_armory.gateway import BackendManager


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
def app(session_maker: async_sessionmaker[AsyncSession]) -> Starlette:
    """Create a test Starlette app with admin routes."""
    app = Starlette(routes=get_admin_routes())
    app.state.session_maker = session_maker
    app.state.backend_manager = BackendManager(session_maker)
    return app


@pytest.fixture
def client(app: Starlette) -> TestClient:
    """Create a test client."""
    return TestClient(app)


class TestBackendRoutes:
    """Tests for backend CRUD routes."""

    async def test_list_backends_empty(
        self, session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """List backends returns empty list when no backends exist."""
        app = Starlette(routes=get_admin_routes())
        app.state.session_maker = session_maker
        app.state.backend_manager = BackendManager(session_maker)

        with TestClient(app) as client:
            response = client.get("/admin/backends")

        assert response.status_code == 200
        data = response.json()
        assert data["backends"] == []
        assert data["total"] == 0

    async def test_list_backends_with_data(
        self, session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """List backends returns all backends."""
        # Create test data
        async with session_maker() as session:
            repo = BackendRepository(session)
            await repo.create(BackendCreate(name="weather", url="http://localhost:8000/mcp"))
            await repo.create(BackendCreate(name="search", url="http://localhost:8001/mcp"))
            await session.commit()

        app = Starlette(routes=get_admin_routes())
        app.state.session_maker = session_maker
        app.state.backend_manager = BackendManager(session_maker)

        with TestClient(app) as client:
            response = client.get("/admin/backends")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        names = {b["name"] for b in data["backends"]}
        assert names == {"weather", "search"}

    async def test_create_backend(
        self, session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """Create backend creates and connects."""
        app = Starlette(routes=get_admin_routes())
        app.state.session_maker = session_maker
        manager = BackendManager(session_maker)
        app.state.backend_manager = manager

        with (
            patch.object(manager, "add_backend", new_callable=AsyncMock) as mock_add,
            TestClient(app) as client,
        ):
            mock_add.return_value = [ToolInfo(name="get_forecast", input_schema={})]

            response = client.post(
                "/admin/backends",
                json={
                    "name": "weather",
                    "url": "http://localhost:8000/mcp",
                },
            )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "weather"
        assert data["url"] == "http://localhost:8000/mcp"
        assert data["enabled"] is True

    async def test_create_backend_duplicate(
        self, session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """Create backend fails for duplicate name."""
        async with session_maker() as session:
            repo = BackendRepository(session)
            await repo.create(BackendCreate(name="weather", url="http://localhost:8000/mcp"))
            await session.commit()

        app = Starlette(routes=get_admin_routes())
        app.state.session_maker = session_maker
        app.state.backend_manager = BackendManager(session_maker)

        with TestClient(app) as client:
            response = client.post(
                "/admin/backends",
                json={
                    "name": "weather",
                    "url": "http://localhost:8001/mcp",
                },
            )

        assert response.status_code == 409
        assert "already exists" in response.json()["error"]

    async def test_get_backend(
        self, session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """Get backend by name."""
        async with session_maker() as session:
            repo = BackendRepository(session)
            await repo.create(BackendCreate(name="weather", url="http://localhost:8000/mcp"))
            await session.commit()

        app = Starlette(routes=get_admin_routes())
        app.state.session_maker = session_maker
        app.state.backend_manager = BackendManager(session_maker)

        with TestClient(app) as client:
            response = client.get("/admin/backends/weather")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "weather"
        assert data["url"] == "http://localhost:8000/mcp"

    async def test_get_backend_not_found(
        self, session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """Get backend returns 404 for non-existent backend."""
        app = Starlette(routes=get_admin_routes())
        app.state.session_maker = session_maker
        app.state.backend_manager = BackendManager(session_maker)

        with TestClient(app) as client:
            response = client.get("/admin/backends/nonexistent")

        assert response.status_code == 404

    async def test_update_backend(
        self, session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """Update backend modifies fields."""
        async with session_maker() as session:
            repo = BackendRepository(session)
            await repo.create(BackendCreate(name="weather", url="http://localhost:8000/mcp"))
            await session.commit()

        app = Starlette(routes=get_admin_routes())
        app.state.session_maker = session_maker
        app.state.backend_manager = BackendManager(session_maker)

        with TestClient(app) as client:
            response = client.put(
                "/admin/backends/weather",
                json={"timeout": 60.0},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["timeout"] == 60.0

    async def test_delete_backend(
        self, session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """Delete backend removes from database."""
        async with session_maker() as session:
            repo = BackendRepository(session)
            await repo.create(BackendCreate(name="weather", url="http://localhost:8000/mcp"))
            await session.commit()

        app = Starlette(routes=get_admin_routes())
        app.state.session_maker = session_maker
        app.state.backend_manager = BackendManager(session_maker)

        with TestClient(app) as client:
            response = client.delete("/admin/backends/weather")

        assert response.status_code == 200
        assert "deleted" in response.json()["message"]

        # Verify deleted
        async with session_maker() as session:
            repo = BackendRepository(session)
            backend = await repo.get_by_name("weather")
            assert backend is None

    async def test_delete_backend_not_found(
        self, session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """Delete backend returns 404 for non-existent backend."""
        app = Starlette(routes=get_admin_routes())
        app.state.session_maker = session_maker
        app.state.backend_manager = BackendManager(session_maker)

        with TestClient(app) as client:
            response = client.delete("/admin/backends/nonexistent")

        assert response.status_code == 404


class TestBackendActionRoutes:
    """Tests for backend action routes (refresh, enable, disable)."""

    async def test_refresh_backend(
        self, session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """Refresh backend updates tools."""
        async with session_maker() as session:
            repo = BackendRepository(session)
            await repo.create(BackendCreate(name="weather", url="http://localhost:8000/mcp"))
            await session.commit()

        app = Starlette(routes=get_admin_routes())
        app.state.session_maker = session_maker
        manager = BackendManager(session_maker)
        app.state.backend_manager = manager

        with (
            patch.object(manager, "add_backend", new_callable=AsyncMock) as mock_add,
            TestClient(app) as client,
        ):
            mock_add.return_value = [
                ToolInfo(name="get_forecast", input_schema={}),
                ToolInfo(name="get_current", input_schema={}),
            ]

            response = client.post("/admin/backends/weather/refresh")

        assert response.status_code == 200
        data = response.json()
        assert data["backend_name"] == "weather"
        assert data["tools_count"] == 2
        assert set(data["tools"]) == {"get_forecast", "get_current"}

    async def test_enable_backend(
        self, session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """Enable backend sets enabled=True and connects."""
        async with session_maker() as session:
            repo = BackendRepository(session)
            await repo.create(
                BackendCreate(name="weather", url="http://localhost:8000/mcp", enabled=False)
            )
            await session.commit()

        app = Starlette(routes=get_admin_routes())
        app.state.session_maker = session_maker
        manager = BackendManager(session_maker)
        app.state.backend_manager = manager

        with (
            patch.object(manager, "add_backend", new_callable=AsyncMock) as mock_add,
            TestClient(app) as client,
        ):
            mock_add.return_value = []

            response = client.post("/admin/backends/weather/enable")

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is True

    async def test_disable_backend(
        self, session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """Disable backend sets enabled=False and disconnects."""
        async with session_maker() as session:
            repo = BackendRepository(session)
            await repo.create(BackendCreate(name="weather", url="http://localhost:8000/mcp"))
            await session.commit()

        app = Starlette(routes=get_admin_routes())
        app.state.session_maker = session_maker
        manager = BackendManager(session_maker)
        app.state.backend_manager = manager

        with TestClient(app) as client:
            response = client.post("/admin/backends/weather/disable")

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is False


class TestToolRoutes:
    """Tests for tool routes."""

    async def test_list_tools_empty(
        self, session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """List tools returns empty list when no tools exist."""
        app = Starlette(routes=get_admin_routes())
        app.state.session_maker = session_maker
        app.state.backend_manager = BackendManager(session_maker)

        with TestClient(app) as client:
            response = client.get("/admin/tools")

        assert response.status_code == 200
        data = response.json()
        assert data["tools"] == []
        assert data["total"] == 0

    async def test_list_tools_with_data(
        self, session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """List tools returns all tools."""
        async with session_maker() as session:
            backend_repo = BackendRepository(session)
            backend = await backend_repo.create(
                BackendCreate(name="weather", url="http://localhost:8000/mcp")
            )
            tool_repo = ToolRepository(session)
            await tool_repo.refresh_backend_tools(
                backend,
                [
                    ToolInfo(name="get_forecast", description="Get forecast", input_schema={}),
                    ToolInfo(name="get_current", input_schema={}),
                ],
            )
            await session.commit()

        app = Starlette(routes=get_admin_routes())
        app.state.session_maker = session_maker
        app.state.backend_manager = BackendManager(session_maker)

        with TestClient(app) as client:
            response = client.get("/admin/tools")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        prefixed_names = {t["prefixed_name"] for t in data["tools"]}
        assert prefixed_names == {"weather__get_forecast", "weather__get_current"}


class TestMetricsRoutes:
    """Tests for metrics routes."""

    async def test_get_metrics_empty(
        self, session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """Get metrics returns zeros when no calls exist."""
        app = Starlette(routes=get_admin_routes())
        app.state.session_maker = session_maker
        app.state.backend_manager = BackendManager(session_maker)

        with TestClient(app) as client:
            response = client.get("/admin/metrics")

        assert response.status_code == 200
        data = response.json()
        assert data["total_calls"] == 0
        assert data["success_rate"] == 0.0

    async def test_get_metrics_with_data(
        self, session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """Get metrics returns aggregated stats."""
        async with session_maker() as session:
            repo = ToolCallRepository(session)
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
            # Create a failed call
            await repo.create(
                ToolCallCreate(
                    backend_name="weather",
                    tool_name="get_forecast",
                    arguments={},
                    success=False,
                    error_message="Error",
                    latency_ms=50,
                )
            )
            await session.commit()

        app = Starlette(routes=get_admin_routes())
        app.state.session_maker = session_maker
        app.state.backend_manager = BackendManager(session_maker)

        with TestClient(app) as client:
            response = client.get("/admin/metrics")

        assert response.status_code == 200
        data = response.json()
        assert data["total_calls"] == 4
        assert data["success_count"] == 3
        assert data["error_count"] == 1
        assert data["success_rate"] == 0.75

    async def test_get_metrics_filtered_by_backend(
        self, session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """Get metrics can filter by backend name."""
        async with session_maker() as session:
            repo = ToolCallRepository(session)
            # Weather backend calls
            await repo.create(
                ToolCallCreate(
                    backend_name="weather",
                    tool_name="get_forecast",
                    arguments={},
                    success=True,
                    latency_ms=100,
                )
            )
            # Search backend calls
            await repo.create(
                ToolCallCreate(
                    backend_name="search",
                    tool_name="search",
                    arguments={},
                    success=True,
                    latency_ms=200,
                )
            )
            await session.commit()

        app = Starlette(routes=get_admin_routes())
        app.state.session_maker = session_maker
        app.state.backend_manager = BackendManager(session_maker)

        with TestClient(app) as client:
            response = client.get("/admin/metrics?backend=weather")

        assert response.status_code == 200
        data = response.json()
        assert data["total_calls"] == 1
        assert data["avg_latency_ms"] == 100.0

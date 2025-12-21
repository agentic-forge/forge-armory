"""Integration tests for the forge-armory gateway.

These tests verify end-to-end functionality including:
- MCP protocol flow (initialize, tools/list, tools/call, ping)
- Discovery endpoint
- Tool routing across backends
- Mount endpoints for direct backend access
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Route
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
from forge_armory.gateway import BackendManager, ToolNotFoundError
from forge_armory.server import MCPGateway, mcp_handler, mount_handler, well_known_mcp


@pytest.fixture
async def integration_session_maker() -> async_sessionmaker[AsyncSession]:
    """Create a session maker with in-memory SQLite for integration tests."""
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
async def seeded_session_maker(
    integration_session_maker: async_sessionmaker[AsyncSession],
) -> async_sessionmaker[AsyncSession]:
    """Session maker with pre-seeded backend and tools."""
    async with integration_session_maker() as session:
        # Create a backend
        backend_repo = BackendRepository(session)
        backend = await backend_repo.create(
            BackendCreate(
                name="test-backend",
                url="http://localhost:9000/mcp",
                prefix="test",
                mount_enabled=True,
            )
        )

        # Create tools for the backend
        tool_repo = ToolRepository(session)
        await tool_repo.refresh_backend_tools(
            backend,
            [
                ToolInfo(
                    name="greet",
                    description="Greet someone",
                    input_schema={"type": "object", "properties": {"name": {"type": "string"}}},
                ),
                ToolInfo(
                    name="add",
                    description="Add two numbers",
                    input_schema={
                        "type": "object",
                        "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
                    },
                ),
            ],
        )

        # Create a second backend without mount
        backend2 = await backend_repo.create(
            BackendCreate(
                name="no-mount-backend",
                url="http://localhost:9001/mcp",
                prefix="nomount",
                mount_enabled=False,
            )
        )

        await tool_repo.refresh_backend_tools(
            backend2,
            [
                ToolInfo(
                    name="hidden_tool",
                    description="A tool without direct mount access",
                    input_schema={"type": "object"},
                ),
            ],
        )

        await session.commit()

    return integration_session_maker


def create_test_app(session_maker: async_sessionmaker[AsyncSession]) -> Any:
    """Create a test Starlette app with mocked backend connections."""
    # Create manager with mocked connections
    manager = BackendManager(session_maker)

    # Create MCP gateway
    mcp_gateway = MCPGateway(manager)

    middleware = [
        Middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        ),
    ]

    app = Starlette(
        middleware=middleware,
        routes=[
            Route("/.well-known/mcp.json", well_known_mcp, methods=["GET"]),
            Route("/mcp", mcp_handler, methods=["POST"]),
            Route("/mcp/{prefix}", mount_handler, methods=["POST"]),
            *get_admin_routes(),
        ],
    )

    app.state.session_maker = session_maker
    app.state.backend_manager = manager
    app.state.mcp_gateway = mcp_gateway

    return app


class TestMCPProtocol:
    """Tests for MCP protocol endpoints."""

    def test_mcp_initialize(
        self, seeded_session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """Test MCP initialize request."""
        app = create_test_app(seeded_session_maker)

        with TestClient(app) as client:
            response = client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "method": "initialize",
                    "params": {"clientInfo": {"name": "test-client", "version": "1.0"}},
                    "id": 1,
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["jsonrpc"] == "2.0"
        assert data["id"] == 1
        assert "result" in data
        assert data["result"]["protocolVersion"] == "2024-11-05"
        assert data["result"]["serverInfo"]["name"] == "forge-armory"
        assert "tools" in data["result"]["capabilities"]

    def test_mcp_ping(
        self, seeded_session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """Test MCP ping request."""
        app = create_test_app(seeded_session_maker)

        with TestClient(app) as client:
            response = client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "method": "ping", "params": {}, "id": 2},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["jsonrpc"] == "2.0"
        assert data["id"] == 2
        assert data["result"] == {}

    def test_mcp_list_tools(
        self, seeded_session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """Test MCP tools/list returns all tools with prefixes."""
        app = create_test_app(seeded_session_maker)

        with TestClient(app) as client:
            response = client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": 3},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["jsonrpc"] == "2.0"
        assert data["id"] == 3

        tools = data["result"]["tools"]
        tool_names = [t["name"] for t in tools]

        # Should have prefixed tool names
        assert "test__greet" in tool_names
        assert "test__add" in tool_names
        assert "nomount__hidden_tool" in tool_names

    def test_mcp_method_not_found(
        self, seeded_session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """Test MCP returns error for unknown method."""
        app = create_test_app(seeded_session_maker)

        with TestClient(app) as client:
            response = client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "method": "unknown/method", "params": {}, "id": 4},
            )

        assert response.status_code == 400
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == -32601
        assert "unknown/method" in data["error"]["message"]

    def test_mcp_parse_error(
        self, seeded_session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """Test MCP returns error for invalid JSON."""
        app = create_test_app(seeded_session_maker)

        with TestClient(app) as client:
            response = client.post(
                "/mcp",
                content="not valid json",
                headers={"Content-Type": "application/json"},
            )

        assert response.status_code == 400
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == -32700


class TestMCPToolCall:
    """Tests for MCP tools/call with mocked backend."""

    def test_call_tool_routes_correctly(
        self, seeded_session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """Test tools/call routes to correct backend and returns result."""
        app = create_test_app(seeded_session_maker)

        # Mock the backend connection's call_tool method
        mock_result = [{"type": "text", "text": "Hello, World!"}]

        with patch.object(
            app.state.backend_manager,
            "call_tool",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_call:
            with TestClient(app) as client:
                response = client.post(
                    "/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/call",
                        "params": {"name": "test__greet", "arguments": {"name": "World"}},
                        "id": 5,
                    },
                )

            assert response.status_code == 200
            data = response.json()
            assert data["id"] == 5
            assert "result" in data

            # Verify call_tool was called with correct arguments
            mock_call.assert_called_once_with("test__greet", {"name": "World"})

    def test_call_tool_not_found(
        self, seeded_session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """Test tools/call returns error for unknown tool."""
        app = create_test_app(seeded_session_maker)

        # Mock call_tool to raise ToolNotFoundError
        with patch.object(
            app.state.backend_manager,
            "call_tool",
            new_callable=AsyncMock,
            side_effect=ToolNotFoundError("Tool not found"),
        ):
            with TestClient(app) as client:
                response = client.post(
                    "/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/call",
                        "params": {"name": "unknown__tool", "arguments": {}},
                        "id": 6,
                    },
                )

            assert response.status_code == 500
            data = response.json()
            assert "error" in data


class TestMountEndpoints:
    """Tests for direct mount endpoints (/mcp/{prefix})."""

    def test_mount_list_tools(
        self, seeded_session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """Test mount endpoint lists tools without prefix."""
        app = create_test_app(seeded_session_maker)

        with TestClient(app) as client:
            response = client.post(
                "/mcp/test",
                json={"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": 1},
            )

        assert response.status_code == 200
        data = response.json()

        tools = data["result"]["tools"]
        tool_names = [t["name"] for t in tools]

        # Should have unprefixed tool names
        assert "greet" in tool_names
        assert "add" in tool_names
        # Should NOT have tools from other backends
        assert "hidden_tool" not in tool_names

    def test_mount_disabled_returns_empty(
        self, seeded_session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """Test mount endpoint returns empty for disabled mount."""
        app = create_test_app(seeded_session_maker)

        with TestClient(app) as client:
            response = client.post(
                "/mcp/nomount",
                json={"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": 1},
            )

        assert response.status_code == 200
        data = response.json()

        # Should return empty tools list because mount is disabled
        tools = data["result"]["tools"]
        assert tools == []

    def test_mount_call_tool(
        self, seeded_session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """Test mount endpoint routes tool call with prefix added."""
        app = create_test_app(seeded_session_maker)

        mock_result = [{"type": "text", "text": "Result"}]

        with patch.object(
            app.state.backend_manager,
            "call_tool",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_call:
            with TestClient(app) as client:
                response = client.post(
                    "/mcp/test",
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/call",
                        "params": {"name": "greet", "arguments": {"name": "Test"}},
                        "id": 2,
                    },
                )

            assert response.status_code == 200

            # Should have called with prefixed name
            mock_call.assert_called_once_with("test__greet", {"name": "Test"})

    def test_mount_initialize(
        self, seeded_session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """Test mount endpoint handles initialize."""
        app = create_test_app(seeded_session_maker)

        with TestClient(app) as client:
            response = client.post(
                "/mcp/test",
                json={"jsonrpc": "2.0", "method": "initialize", "params": {}, "id": 1},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["result"]["serverInfo"]["name"] == "forge-armory"


class TestDiscoveryEndpoint:
    """Tests for /.well-known/mcp.json discovery endpoint."""

    def test_discovery_returns_metadata(
        self, seeded_session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """Test discovery endpoint returns server metadata."""
        app = create_test_app(seeded_session_maker)

        with TestClient(app) as client:
            response = client.get("/.well-known/mcp.json")

        assert response.status_code == 200
        data = response.json()

        assert data["name"] == "forge-armory"
        assert data["version"] == "0.1.0"
        assert "endpoints" in data
        assert data["endpoints"]["aggregated"]["url"] == "/mcp"

    def test_discovery_lists_mounts(
        self, seeded_session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """Test discovery endpoint lists mount points for enabled backends."""
        app = create_test_app(seeded_session_maker)

        with TestClient(app) as client:
            response = client.get("/.well-known/mcp.json")

        assert response.status_code == 200
        data = response.json()

        mounts = data["endpoints"]["mounts"]

        # Should include test backend (mount_enabled=True)
        assert "test" in mounts
        assert mounts["test"]["url"] == "/mcp/test"

        # Should NOT include nomount backend (mount_enabled=False)
        assert "nomount" not in mounts


class TestEndToEndFlow:
    """End-to-end tests combining admin API and MCP protocol."""

    def test_create_backend_and_list_tools(
        self, integration_session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """Test creating a backend via admin API and listing tools via MCP."""
        app = create_test_app(integration_session_maker)

        with TestClient(app) as client:
            # 1. Create a backend via admin API
            create_response = client.post(
                "/admin/backends",
                json={
                    "name": "new-backend",
                    "url": "http://localhost:9999/mcp",
                    "prefix": "new",
                    "mount_enabled": True,
                },
            )

            assert create_response.status_code == 201
            backend_data = create_response.json()
            assert backend_data["name"] == "new-backend"
            assert backend_data["effective_prefix"] == "new"

            # 2. List tools via MCP (should be empty since no tools registered yet)
            mcp_response = client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": 1},
            )

            assert mcp_response.status_code == 200
            tools = mcp_response.json()["result"]["tools"]
            # No tools yet (backend not refreshed)
            assert len(tools) == 0

    def test_full_admin_workflow(
        self, integration_session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """Test complete admin workflow: create, list, update, delete."""
        app = create_test_app(integration_session_maker)

        with TestClient(app) as client:
            # Create
            create_resp = client.post(
                "/admin/backends",
                json={"name": "workflow-test", "url": "http://test.local/mcp"},
            )
            assert create_resp.status_code == 201

            # List
            list_resp = client.get("/admin/backends")
            assert list_resp.status_code == 200
            backends = list_resp.json()["backends"]
            assert len(backends) == 1
            assert backends[0]["name"] == "workflow-test"

            # Update
            update_resp = client.put(
                "/admin/backends/workflow-test",
                json={"timeout": 60.0},
            )
            assert update_resp.status_code == 200
            assert update_resp.json()["timeout"] == 60.0

            # Disable
            disable_resp = client.post("/admin/backends/workflow-test/disable")
            assert disable_resp.status_code == 200
            assert disable_resp.json()["enabled"] is False

            # Enable
            enable_resp = client.post("/admin/backends/workflow-test/enable")
            assert enable_resp.status_code == 200
            assert enable_resp.json()["enabled"] is True

            # Delete
            delete_resp = client.delete("/admin/backends/workflow-test")
            assert delete_resp.status_code == 200

            # Verify deleted
            list_resp2 = client.get("/admin/backends")
            assert list_resp2.json()["backends"] == []


class TestMetricsIntegration:
    """Tests for metrics across admin API."""

    def test_metrics_empty(
        self, integration_session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """Test metrics endpoint with no calls."""
        app = create_test_app(integration_session_maker)

        with TestClient(app) as client:
            response = client.get("/admin/metrics")

        assert response.status_code == 200
        data = response.json()
        assert data["total_calls"] == 0

    def test_metrics_after_tool_calls(
        self, seeded_session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """Test metrics are recorded after tool calls."""
        app = create_test_app(seeded_session_maker)

        # Manually record some tool calls
        async def record_calls() -> None:
            async with seeded_session_maker() as session:
                repo = ToolCallRepository(session)
                await repo.create(
                    ToolCallCreate(
                        backend_name="test-backend",
                        tool_name="greet",
                        arguments={"name": "World"},
                        success=True,
                        latency_ms=50,
                    )
                )
                await repo.create(
                    ToolCallCreate(
                        backend_name="test-backend",
                        tool_name="add",
                        arguments={"a": 1, "b": 2},
                        success=True,
                        latency_ms=30,
                    )
                )
                await repo.create(
                    ToolCallCreate(
                        backend_name="test-backend",
                        tool_name="greet",
                        arguments={"name": "Error"},
                        success=False,
                        error_message="Something went wrong",
                        latency_ms=100,
                    )
                )
                await session.commit()

        asyncio.get_event_loop().run_until_complete(record_calls())

        with TestClient(app) as client:
            response = client.get("/admin/metrics")

        assert response.status_code == 200
        data = response.json()
        assert data["total_calls"] == 3
        assert data["success_count"] == 2
        assert data["error_count"] == 1
        assert data["avg_latency_ms"] == 60.0  # (50 + 30 + 100) / 3

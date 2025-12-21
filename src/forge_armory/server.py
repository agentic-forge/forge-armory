"""Gateway server combining MCP endpoints and Admin API."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from forge_armory.admin import router as admin_router
from forge_armory.db import (
    BackendRepository,
    ToolRepository,
    async_session_maker,
    close_db,
    init_db,
)
from forge_armory.gateway import BackendManager

logger = logging.getLogger(__name__)


# ============================================================================
# MCP Protocol Handler
# ============================================================================


class MCPGateway:
    """MCP gateway that proxies tool calls to backend servers.

    Implements the MCP protocol by:
    - Aggregating tools from all backends at /mcp
    - Providing direct access to individual backends at /mcp/{prefix}
    """

    def __init__(self, manager: BackendManager) -> None:
        self.manager = manager

    async def handle_mcp_request(self, request: Request) -> JSONResponse:
        """Handle MCP JSON-RPC requests at /mcp endpoint.

        This is the aggregated endpoint where all tools are available
        with their prefixed names.
        """
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(
                {"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}, "id": None},
                status_code=400,
            )

        method = body.get("method", "")
        params = body.get("params", {})
        request_id = body.get("id")

        try:
            if method == "initialize":
                result = await self._handle_initialize(params)
            elif method == "tools/list":
                result = await self._handle_list_tools()
            elif method == "tools/call":
                result = await self._handle_call_tool(params)
            elif method == "ping":
                result = {}
            else:
                return JSONResponse(
                    {
                        "jsonrpc": "2.0",
                        "error": {"code": -32601, "message": f"Method not found: {method}"},
                        "id": request_id,
                    },
                    status_code=400,
                )

            return JSONResponse({"jsonrpc": "2.0", "result": result, "id": request_id})

        except Exception as e:
            logger.exception("Error handling MCP request")
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "error": {"code": -32603, "message": str(e)},
                    "id": request_id,
                },
                status_code=500,
            )

    async def handle_mount_request(self, request: Request, prefix: str) -> JSONResponse:
        """Handle MCP requests at /mcp/{prefix} endpoint.

        This provides direct access to a specific backend's tools
        without the prefix.
        """
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(
                {"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}, "id": None},
                status_code=400,
            )

        method = body.get("method", "")
        params = body.get("params", {})
        request_id = body.get("id")

        try:
            if method == "initialize":
                result = await self._handle_initialize(params)
            elif method == "tools/list":
                result = await self._handle_list_tools_for_mount(prefix)
            elif method == "tools/call":
                result = await self._handle_call_tool_for_mount(prefix, params)
            elif method == "ping":
                result = {}
            else:
                return JSONResponse(
                    {
                        "jsonrpc": "2.0",
                        "error": {"code": -32601, "message": f"Method not found: {method}"},
                        "id": request_id,
                    },
                    status_code=400,
                )

            return JSONResponse({"jsonrpc": "2.0", "result": result, "id": request_id})

        except Exception as e:
            logger.exception("Error handling MCP mount request")
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "error": {"code": -32603, "message": str(e)},
                    "id": request_id,
                },
                status_code=500,
            )

    async def _handle_initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle initialize request."""
        _ = params  # Reserved for future use (client info, capabilities)
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {"listChanged": True},
            },
            "serverInfo": {
                "name": "forge-armory",
                "version": "0.1.0",
            },
        }

    async def _handle_list_tools(self) -> dict[str, Any]:
        """List all tools from all backends (aggregated)."""
        tools = await self.manager.list_tools()

        return {
            "tools": [
                {
                    "name": tool.prefixed_name,
                    "description": tool.description or "",
                    "inputSchema": tool.input_schema,
                }
                for tool in tools
            ]
        }

    async def _handle_list_tools_for_mount(self, prefix: str) -> dict[str, Any]:
        """List tools for a specific mount point (unprefixed)."""
        async with self.manager._session_maker() as session:
            backend_repo = BackendRepository(session)
            tool_repo = ToolRepository(session)

            # Find backend by effective prefix
            backends = await backend_repo.list_all(enabled_only=True)
            backend = next(
                (b for b in backends if b.effective_prefix == prefix and b.mount_enabled),
                None,
            )

            if not backend:
                return {"tools": []}

            tools = await tool_repo.list_by_backend(backend.id)

            return {
                "tools": [
                    {
                        "name": tool.name,  # Original name without prefix
                        "description": tool.description or "",
                        "inputSchema": tool.input_schema,
                    }
                    for tool in tools
                ]
            }

    async def _handle_call_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        """Call a tool using its prefixed name."""
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        result = await self.manager.call_tool(tool_name, arguments)

        # Convert result to MCP format
        return self._format_tool_result(result)

    async def _handle_call_tool_for_mount(
        self, prefix: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Call a tool on a specific mount using unprefixed name."""
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        # Convert to prefixed name for routing
        prefixed_name = f"{prefix}__{tool_name}"
        result = await self.manager.call_tool(prefixed_name, arguments)

        return self._format_tool_result(result)

    def _format_tool_result(self, result: Any) -> dict[str, Any]:
        """Format tool result for MCP response."""
        # Handle different result types
        if isinstance(result, dict):
            return {"content": [{"type": "text", "text": str(result)}]}
        elif isinstance(result, list):
            # FastMCP often returns list of content items
            return {"content": result}
        elif isinstance(result, str):
            return {"content": [{"type": "text", "text": result}]}
        else:
            return {"content": [{"type": "text", "text": str(result)}]}


# ============================================================================
# Application Factory
# ============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("Starting Forge Armory gateway...")

    # Initialize database
    await init_db()
    logger.info("Database initialized")

    # Create session maker and store in app state
    app.state.session_maker = async_session_maker

    # Create and initialize backend manager
    manager = BackendManager(async_session_maker)
    await manager.initialize()
    app.state.backend_manager = manager
    logger.info("Backend manager initialized with %d backends", len(manager.connected_backends))

    # Create MCP gateway
    app.state.mcp_gateway = MCPGateway(manager)

    yield

    # Shutdown
    logger.info("Shutting down Forge Armory gateway...")
    await manager.shutdown()
    await close_db()
    logger.info("Gateway shutdown complete")


# Create the application
app = FastAPI(
    title="Forge Armory",
    description="MCP protocol gateway - aggregates tools from multiple MCP servers",
    version="0.1.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include admin API router
app.include_router(admin_router)


# ============================================================================
# MCP Endpoints
# ============================================================================


@app.get("/.well-known/mcp.json")
async def well_known_mcp(request: Request) -> dict[str, Any]:
    """Serve MCP discovery metadata."""
    session_maker = request.app.state.session_maker

    async with session_maker() as session:
        backend_repo = BackendRepository(session)
        backends = await backend_repo.list_all(enabled_only=True)

        # Build mount points for backends with mount_enabled
        mounts = {}
        for backend in backends:
            if backend.mount_enabled:
                mounts[backend.effective_prefix] = {
                    "url": f"/mcp/{backend.effective_prefix}",
                    "description": f"Direct access to {backend.name}",
                }

    return {
        "name": "forge-armory",
        "version": "0.1.0",
        "description": "MCP protocol gateway - aggregates tools from multiple MCP servers",
        "endpoints": {
            "aggregated": {
                "url": "/mcp",
                "description": "All tools from all backends with prefixed names",
            },
            "mounts": mounts,
        },
    }


@app.post("/mcp")
async def mcp_handler(request: Request) -> JSONResponse:
    """Handle MCP requests at /mcp endpoint."""
    gateway: MCPGateway = request.app.state.mcp_gateway
    return await gateway.handle_mcp_request(request)


@app.post("/mcp/{prefix}")
async def mount_handler(request: Request, prefix: str) -> JSONResponse:
    """Handle MCP requests at /mcp/{prefix} endpoint."""
    gateway: MCPGateway = request.app.state.mcp_gateway
    return await gateway.handle_mount_request(request, prefix)

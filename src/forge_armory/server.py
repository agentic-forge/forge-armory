"""Gateway server combining MCP endpoints and Admin API."""

from __future__ import annotations

import json
import logging
import uuid
from contextlib import asynccontextmanager
from enum import Enum
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from forge_armory.admin import router as admin_router
from forge_armory.db import (
    BackendRepository,
    ToolRepository,
    async_session_maker,
    close_db,
    init_db,
)
from forge_armory.gateway import BackendManager, RequestContext

logger = logging.getLogger(__name__)


# ============================================================================
# MCP Mode Support
# ============================================================================


class MCPMode(str, Enum):
    """MCP endpoint modes."""

    NORMAL = "normal"  # All tools visible to LLM
    RAG = "rag"  # Only search_tools meta-tool visible


def get_mcp_mode(request: Request) -> MCPMode:
    """Extract MCP mode from query parameters.

    Args:
        request: FastAPI request object

    Returns:
        MCPMode.RAG if ?mode=rag, otherwise MCPMode.NORMAL
    """
    mode = request.query_params.get("mode", "normal").lower()
    if mode == "rag":
        return MCPMode.RAG
    return MCPMode.NORMAL


def get_client_ip(request: Request) -> str | None:
    """Extract client IP from request, handling reverse proxy headers.

    Checks headers in order of preference:
    1. X-Forwarded-For (standard proxy header, takes first IP)
    2. X-Real-IP (Nginx/Traefik)
    3. CF-Connecting-IP (Cloudflare)
    4. Falls back to request.client.host
    """
    # X-Forwarded-For may contain multiple IPs: "client, proxy1, proxy2"
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        # Take the first IP (original client)
        return forwarded_for.split(",")[0].strip()

    # X-Real-IP is typically set by Nginx/Traefik
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()

    # Cloudflare specific header
    cf_ip = request.headers.get("cf-connecting-ip")
    if cf_ip:
        return cf_ip.strip()

    # Fall back to direct connection
    if request.client:
        return request.client.host

    return None


def get_request_context(request: Request) -> RequestContext:
    """Extract request context from FastAPI request.

    Extracts:
    - client_ip: From proxy headers or direct connection
    - request_id: From X-Request-ID header or generates a new one
    - session_id: From X-Session-ID header (optional)
    - caller: From X-Caller or Authorization header user info (optional)
    """
    # Get or generate request ID for tracing
    request_id = request.headers.get("x-request-id")
    if not request_id:
        request_id = str(uuid.uuid4())[:8]  # Short ID for convenience

    return RequestContext(
        client_ip=get_client_ip(request),
        request_id=request_id,
        session_id=request.headers.get("x-session-id"),
        caller=request.headers.get("x-caller"),
    )


# ============================================================================
# MCP Protocol Handler
# ============================================================================


class MCPGateway:
    """MCP gateway that proxies tool calls to backend servers.

    Implements the MCP protocol by:
    - Aggregating tools from all backends at /mcp
    - Providing direct access to individual backends at /mcp/{prefix}

    Supports two modes:
    - NORMAL: All tools visible to LLM (default)
    - RAG: Only search_tools meta-tool visible, tools discovered via search
    """

    # The search_tools meta-tool name
    SEARCH_TOOLS_NAME = "search_tools"

    def __init__(self, manager: BackendManager) -> None:
        self.manager = manager
        self._session_maker = manager._session_maker

    async def handle_mcp_request(self, request: Request) -> JSONResponse:
        """Handle MCP JSON-RPC requests at /mcp endpoint.

        This is the aggregated endpoint where all tools are available
        with their prefixed names.

        Supports two modes via query parameter:
        - /mcp (default): All tools visible
        - /mcp?mode=rag: Only search_tools meta-tool visible
        """
        # Extract request context and mode
        context = get_request_context(request)
        mcp_mode = get_mcp_mode(request)

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
                result = await self._handle_initialize(params, mcp_mode)
            elif method == "tools/list":
                if mcp_mode == MCPMode.RAG:
                    result = await self._handle_list_tools_rag()
                else:
                    result = await self._handle_list_tools()
            elif method == "tools/call":
                result = await self._handle_call_tool(params, context)
            elif method == "ping":
                result = {}
            else:
                # JSON-RPC spec: return 200 with error in body, not HTTP error status
                return JSONResponse(
                    {
                        "jsonrpc": "2.0",
                        "error": {"code": -32601, "message": f"Method not found: {method}"},
                        "id": request_id,
                    },
                )

            return JSONResponse(
                {"jsonrpc": "2.0", "result": result, "id": request_id},
            )

        except Exception as e:
            logger.exception("Error handling MCP request")
            # JSON-RPC spec: return 200 with error in body, not HTTP error status
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "error": {"code": -32603, "message": str(e)},
                    "id": request_id,
                },
            )

    async def handle_mount_request(self, request: Request, prefix: str) -> JSONResponse:
        """Handle MCP requests at /mcp/{prefix} endpoint.

        This provides direct access to a specific backend's tools
        without the prefix.
        """
        # Extract request context for tracking
        context = get_request_context(request)

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
                result = await self._handle_call_tool_for_mount(prefix, params, context)
            elif method == "ping":
                result = {}
            else:
                # JSON-RPC spec: return 200 with error in body, not HTTP error status
                return JSONResponse(
                    {
                        "jsonrpc": "2.0",
                        "error": {"code": -32601, "message": f"Method not found: {method}"},
                        "id": request_id,
                    },
                )

            return JSONResponse(
                {"jsonrpc": "2.0", "result": result, "id": request_id},
            )

        except Exception as e:
            logger.exception("Error handling MCP mount request")
            # JSON-RPC spec: return 200 with error in body, not HTTP error status
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "error": {"code": -32603, "message": str(e)},
                    "id": request_id,
                },
            )

    async def _handle_initialize(
        self,
        params: dict[str, Any],
        mode: MCPMode = MCPMode.NORMAL,
    ) -> dict[str, Any]:
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
                "mode": mode.value,
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

    async def _handle_list_tools_rag(self) -> dict[str, Any]:
        """List only the search_tools meta-tool (RAG mode).

        In RAG mode, the LLM sees only the search_tools meta-tool.
        When it calls search_tools with a query, relevant tools are
        returned and can be called directly.
        """
        from forge_armory.db.repository import ToolRAGConfigRepository
        from forge_armory.toolrag import render_manifest

        # Get capability manifest template and tools
        async with self._session_maker() as session:
            config_repo = ToolRAGConfigRepository(session)
            config = await config_repo.get_or_create()
            template = config.capability_manifest

            # Get all tools to render the manifest
            tool_repo = ToolRepository(session)
            tools = await tool_repo.list_all()

        # Render the manifest template with actual tool list
        rendered_manifest = render_manifest(template, tools)

        # Build the search_tools meta-tool description
        base_description = (
            "Search for available tools by describing what you need. "
            "Returns a list of matching tools that you can then call directly."
        )

        description = f"{base_description}\n\n{rendered_manifest}"

        return {
            "tools": [
                {
                    "name": self.SEARCH_TOOLS_NAME,
                    "description": description,
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": (
                                    "Natural language description of what tool you need. "
                                    "Be specific about the task you want to accomplish."
                                ),
                            },
                            "threshold": {
                                "type": "number",
                                "description": (
                                    "Minimum similarity score (0-1). "
                                    "Lower values return more results. Default: 0.5"
                                ),
                                "minimum": 0,
                                "maximum": 1,
                            },
                        },
                        "required": ["query"],
                    },
                }
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

    async def _handle_call_tool(
        self,
        params: dict[str, Any],
        context: RequestContext,
    ) -> dict[str, Any]:
        """Call a tool using its prefixed name.

        In RAG mode, the search_tools meta-tool is handled specially.
        All other tools (including discovered tools) are called normally.

        Args:
            params: MCP call params with name and arguments
            context: Request context for tracking

        Returns:
            MCP result dict
        """
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        # Handle search_tools meta-tool in RAG mode
        if tool_name == self.SEARCH_TOOLS_NAME:
            return await self._handle_search_tools(arguments)

        # Normal tool call - works in both modes
        result = await self.manager.call_tool(tool_name, arguments, context)

        # Convert result to MCP format (always JSON)
        return self._format_tool_result(result)

    async def _handle_search_tools(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle the search_tools meta-tool call.

        Searches for tools matching the query using semantic similarity.
        Returns all tools meeting the similarity threshold.

        Args:
            arguments: Tool arguments with query and optional threshold

        Returns:
            MCP result dict
        """
        from forge_armory.toolrag import (
            format_search_response,
            format_search_results,
            search_tools,
        )

        query = arguments.get("query", "")
        threshold = arguments.get("threshold")

        if not query:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps({
                            "error": "Query is required",
                            "tools": [],
                            "total_matches": 0,
                        }),
                    }
                ]
            }

        # Search for matching tools (returns all matching threshold)
        async with self._session_maker() as session:
            tools = await search_tools(
                session,
                query,
                threshold=threshold,
            )

        # Format results
        result = format_search_results(tools, query)
        response = format_search_response(result)

        return {"content": [{"type": "text", "text": json.dumps(response)}]}

    async def _handle_call_tool_for_mount(
        self,
        prefix: str,
        params: dict[str, Any],
        context: RequestContext,
    ) -> dict[str, Any]:
        """Call a tool on a specific mount using unprefixed name.

        Args:
            prefix: Backend prefix
            params: MCP call params with name and arguments
            context: Request context for tracking

        Returns:
            MCP result dict
        """
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        # Convert to prefixed name for routing
        prefixed_name = f"{prefix}__{tool_name}"
        result = await self.manager.call_tool(prefixed_name, arguments, context)

        return self._format_tool_result(result)

    def _format_tool_result(self, result: Any) -> dict[str, Any]:
        """Format tool result for MCP response.

        Always returns JSON format. TOON transformation is handled
        by the orchestrator, not armory.

        Args:
            result: Raw tool result from backend

        Returns:
            MCP result dict with JSON content
        """
        # Extract actual data from result
        data = self._extract_result_data(result)

        # Always return JSON
        text = data if isinstance(data, str) else json.dumps(data, default=str)

        return {"content": [{"type": "text", "text": text}]}

    def _extract_result_data(self, result: Any) -> Any:
        """Extract the actual data from a tool result.

        Handles various result formats from backends:
        - CallToolResult: Extract structured_content or text from content
        - dict: Return as-is
        - list of MCP content items: Extract text and parse as JSON
        - str: Try to parse as JSON, otherwise return as-is
        - other: Return as-is

        Args:
            result: Raw result from backend

        Returns:
            Extracted data suitable for formatting
        """
        # Handle FastMCP CallToolResult objects
        # Check for structured_content first (preferred - already parsed)
        if hasattr(result, 'structured_content') and result.structured_content is not None:
            return result.structured_content

        # Check for data field (FastMCP stores parsed result here)
        if hasattr(result, 'data') and result.data is not None:
            # Data might be a pydantic model, convert to dict if possible
            if hasattr(result.data, 'model_dump'):
                return result.data.model_dump()
            elif hasattr(result.data, '__dict__'):
                # Fallback for dataclass-like objects
                return result.data.__dict__
            return result.data

        # Check for content list with TextContent items
        if hasattr(result, 'content') and isinstance(result.content, list) and result.content:
            first = result.content[0]
            # TextContent has a 'text' attribute
            if hasattr(first, 'text'):
                return self._try_parse_json(first.text)
            # Or it might be a dict
            elif isinstance(first, dict) and first.get("type") == "text":
                return self._try_parse_json(first.get("text", ""))

        data = result

        # Handle dict that is already MCP-formatted (has "content" key with list)
        # This happens when backend returns raw JSON-RPC result
        if isinstance(result, dict) and "content" in result:
            content = result["content"]
            if isinstance(content, list) and content:
                first = content[0]
                if isinstance(first, dict) and first.get("type") == "text":
                    return self._try_parse_json(first.get("text", ""))

        # Handle list of MCP content items (dict format)
        if isinstance(result, list) and result:
            first = result[0]
            if isinstance(first, dict) and first.get("type") == "text":
                text = first.get("text", "")
                data = self._try_parse_json(text)
            else:
                data = result

        # Handle string results - try to parse as JSON
        elif isinstance(result, str):
            data = self._try_parse_json(result)

        # Handle dict - return as-is
        elif isinstance(result, dict):
            data = result

        return data

    def _try_parse_json(self, text: str) -> Any:
        """Try to parse text as JSON, return original text on failure."""
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return text


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
# Admin UI Static Files
# ============================================================================

# Path to the admin UI dist folder
ADMIN_UI_DIR = Path(__file__).parent.parent.parent / "admin-ui" / "dist"


@app.get("/ui/{path:path}")
async def serve_ui(path: str) -> FileResponse:
    """Serve admin UI static files.

    Falls back to index.html for client-side routing.
    """
    file_path = ADMIN_UI_DIR / path

    # If file exists, serve it
    if file_path.is_file():
        return FileResponse(file_path)

    # Otherwise serve index.html for client-side routing
    return FileResponse(ADMIN_UI_DIR / "index.html")


@app.get("/ui")
async def redirect_ui() -> FileResponse:
    """Redirect /ui to /ui/ for proper routing."""
    return FileResponse(ADMIN_UI_DIR / "index.html")


# Mount static assets (CSS, JS, etc.) - this handles the assets directory
if ADMIN_UI_DIR.exists():
    app.mount(
        "/ui/assets",
        StaticFiles(directory=ADMIN_UI_DIR / "assets"),
        name="ui-assets",
    )


# ============================================================================
# Health Check Endpoint
# ============================================================================


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint for Docker/k8s health probes."""
    return {"status": "healthy", "service": "forge-armory"}


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

"""Admin API routes for managing backends."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from starlette.responses import JSONResponse
from starlette.routing import Route

from forge_armory.admin.schemas import (
    BackendCreateRequest,
    BackendListResponse,
    BackendResponse,
    BackendUpdateRequest,
    ErrorResponse,
    MessageResponse,
    MetricsResponse,
    RefreshResponse,
    ToolListResponse,
    ToolResponse,
)
from forge_armory.db import (
    BackendCreate,
    BackendRepository,
    BackendUpdate,
    ToolCallRepository,
    ToolRepository,
)
from forge_armory.gateway import (
    BackendConnectionError,
    BackendNotFoundError,
)

if TYPE_CHECKING:
    from starlette.requests import Request

    from forge_armory.gateway import BackendManager

logger = logging.getLogger(__name__)


def _json_response(data: dict, status_code: int = 200) -> JSONResponse:
    """Create a JSON response."""
    return JSONResponse(data, status_code=status_code)


def _error_response(error: str, detail: str | None = None, status_code: int = 400) -> JSONResponse:
    """Create an error response."""
    return _json_response(
        ErrorResponse(error=error, detail=detail).model_dump(),
        status_code=status_code,
    )


# ============================================================================
# Backend Routes
# ============================================================================


async def list_backends(request: Request) -> JSONResponse:
    """List all backends.

    GET /admin/backends
    """
    session_maker = request.app.state.session_maker

    async with session_maker() as session:
        repo = BackendRepository(session)
        backends = await repo.list_all()

        tool_repo = ToolRepository(session)

        backend_responses = []
        for backend in backends:
            tools = await tool_repo.list_by_backend(backend.id)
            backend_responses.append(
                BackendResponse(
                    id=backend.id,
                    name=backend.name,
                    url=backend.url,
                    enabled=backend.enabled,
                    timeout=backend.timeout,
                    prefix=backend.prefix,
                    mount_enabled=backend.mount_enabled,
                    effective_prefix=backend.effective_prefix,
                    created_at=backend.created_at,
                    updated_at=backend.updated_at,
                    tool_count=len(tools),
                ).model_dump(mode="json")
            )

    return _json_response(
        BackendListResponse(
            backends=backend_responses,
            total=len(backend_responses),
        ).model_dump(mode="json")
    )


async def create_backend(request: Request) -> JSONResponse:
    """Create a new backend and connect to it.

    POST /admin/backends
    """
    try:
        body = await request.json()
        data = BackendCreateRequest.model_validate(body)
    except Exception as e:
        return _error_response("Invalid request body", str(e), 400)

    session_maker = request.app.state.session_maker
    manager: BackendManager = request.app.state.backend_manager

    async with session_maker() as session:
        repo = BackendRepository(session)

        # Check if backend already exists
        existing = await repo.get_by_name(data.name)
        if existing:
            return _error_response(f"Backend '{data.name}' already exists", status_code=409)

        # Create backend in DB
        backend = await repo.create(
            BackendCreate(
                name=data.name,
                url=data.url,
                enabled=data.enabled,
                timeout=data.timeout,
                prefix=data.prefix,
                mount_enabled=data.mount_enabled,
            )
        )
        await session.commit()

        # Try to connect if enabled
        tool_count = 0
        if backend.enabled:
            try:
                tools = await manager.add_backend(backend)
                tool_count = len(tools)
            except BackendConnectionError as e:
                logger.warning("Failed to connect to new backend %s: %s", backend.name, e)

        return _json_response(
            BackendResponse(
                id=backend.id,
                name=backend.name,
                url=backend.url,
                enabled=backend.enabled,
                timeout=backend.timeout,
                prefix=backend.prefix,
                mount_enabled=backend.mount_enabled,
                effective_prefix=backend.effective_prefix,
                created_at=backend.created_at,
                updated_at=backend.updated_at,
                tool_count=tool_count,
            ).model_dump(mode="json"),
            status_code=201,
        )


async def get_backend(request: Request) -> JSONResponse:
    """Get a backend by name.

    GET /admin/backends/{name}
    """
    name = request.path_params["name"]
    session_maker = request.app.state.session_maker

    async with session_maker() as session:
        repo = BackendRepository(session)
        backend = await repo.get_by_name(name)

        if not backend:
            return _error_response(f"Backend '{name}' not found", status_code=404)

        tool_repo = ToolRepository(session)
        tools = await tool_repo.list_by_backend(backend.id)

        return _json_response(
            BackendResponse(
                id=backend.id,
                name=backend.name,
                url=backend.url,
                enabled=backend.enabled,
                timeout=backend.timeout,
                prefix=backend.prefix,
                mount_enabled=backend.mount_enabled,
                effective_prefix=backend.effective_prefix,
                created_at=backend.created_at,
                updated_at=backend.updated_at,
                tool_count=len(tools),
            ).model_dump(mode="json")
        )


async def update_backend(request: Request) -> JSONResponse:
    """Update a backend.

    PUT /admin/backends/{name}
    """
    name = request.path_params["name"]

    try:
        body = await request.json()
        data = BackendUpdateRequest.model_validate(body)
    except Exception as e:
        return _error_response("Invalid request body", str(e), 400)

    session_maker = request.app.state.session_maker

    async with session_maker() as session:
        repo = BackendRepository(session)
        # Only pass fields that were explicitly set in the request
        update_data = data.model_dump(exclude_unset=True)
        backend = await repo.update(name, BackendUpdate(**update_data))

        if not backend:
            return _error_response(f"Backend '{name}' not found", status_code=404)

        await session.commit()

        tool_repo = ToolRepository(session)
        tools = await tool_repo.list_by_backend(backend.id)

        return _json_response(
            BackendResponse(
                id=backend.id,
                name=backend.name,
                url=backend.url,
                enabled=backend.enabled,
                timeout=backend.timeout,
                prefix=backend.prefix,
                mount_enabled=backend.mount_enabled,
                effective_prefix=backend.effective_prefix,
                created_at=backend.created_at,
                updated_at=backend.updated_at,
                tool_count=len(tools),
            ).model_dump(mode="json")
        )


async def delete_backend(request: Request) -> JSONResponse:
    """Delete a backend.

    DELETE /admin/backends/{name}
    """
    name = request.path_params["name"]
    session_maker = request.app.state.session_maker
    manager: BackendManager = request.app.state.backend_manager

    # Disconnect if connected
    await manager.remove_backend(name)

    async with session_maker() as session:
        repo = BackendRepository(session)
        deleted = await repo.delete(name)

        if not deleted:
            return _error_response(f"Backend '{name}' not found", status_code=404)

        await session.commit()

    return _json_response(
        MessageResponse(message=f"Backend '{name}' deleted").model_dump()
    )


async def refresh_backend(request: Request) -> JSONResponse:
    """Refresh a backend's tools.

    POST /admin/backends/{name}/refresh
    """
    name = request.path_params["name"]
    session_maker = request.app.state.session_maker
    manager: BackendManager = request.app.state.backend_manager

    # Check backend exists
    async with session_maker() as session:
        repo = BackendRepository(session)
        backend = await repo.get_by_name(name)

        if not backend:
            return _error_response(f"Backend '{name}' not found", status_code=404)

    # If not connected, try to connect first
    if name not in manager.connected_backends:
        try:
            tools = await manager.add_backend(backend)
        except BackendConnectionError as e:
            return _error_response(f"Failed to connect to backend: {e}", status_code=503)
    else:
        try:
            tools = await manager.refresh_backend(name)
        except BackendNotFoundError as e:
            return _error_response(str(e), status_code=404)
        except BackendConnectionError as e:
            return _error_response(f"Failed to refresh backend: {e}", status_code=503)

    return _json_response(
        RefreshResponse(
            backend_name=name,
            tools_count=len(tools),
            tools=[t.name for t in tools],
        ).model_dump()
    )


async def enable_backend(request: Request) -> JSONResponse:
    """Enable a backend and connect to it.

    POST /admin/backends/{name}/enable
    """
    name = request.path_params["name"]
    session_maker = request.app.state.session_maker
    manager: BackendManager = request.app.state.backend_manager

    async with session_maker() as session:
        repo = BackendRepository(session)
        backend = await repo.set_enabled(name, enabled=True)

        if not backend:
            return _error_response(f"Backend '{name}' not found", status_code=404)

        await session.commit()

        # Try to connect
        if name not in manager.connected_backends:
            try:
                await manager.add_backend(backend)
            except BackendConnectionError as e:
                logger.warning("Failed to connect to enabled backend %s: %s", name, e)

        tool_repo = ToolRepository(session)
        tools = await tool_repo.list_by_backend(backend.id)

        return _json_response(
            BackendResponse(
                id=backend.id,
                name=backend.name,
                url=backend.url,
                enabled=backend.enabled,
                timeout=backend.timeout,
                prefix=backend.prefix,
                mount_enabled=backend.mount_enabled,
                effective_prefix=backend.effective_prefix,
                created_at=backend.created_at,
                updated_at=backend.updated_at,
                tool_count=len(tools),
            ).model_dump(mode="json")
        )


async def disable_backend(request: Request) -> JSONResponse:
    """Disable a backend and disconnect from it.

    POST /admin/backends/{name}/disable
    """
    name = request.path_params["name"]
    session_maker = request.app.state.session_maker
    manager: BackendManager = request.app.state.backend_manager

    # Disconnect if connected
    await manager.remove_backend(name)

    async with session_maker() as session:
        repo = BackendRepository(session)
        backend = await repo.set_enabled(name, enabled=False)

        if not backend:
            return _error_response(f"Backend '{name}' not found", status_code=404)

        await session.commit()

        tool_repo = ToolRepository(session)
        tools = await tool_repo.list_by_backend(backend.id)

        return _json_response(
            BackendResponse(
                id=backend.id,
                name=backend.name,
                url=backend.url,
                enabled=backend.enabled,
                timeout=backend.timeout,
                prefix=backend.prefix,
                mount_enabled=backend.mount_enabled,
                effective_prefix=backend.effective_prefix,
                created_at=backend.created_at,
                updated_at=backend.updated_at,
                tool_count=len(tools),
            ).model_dump(mode="json")
        )


# ============================================================================
# Tool Routes
# ============================================================================


async def list_tools(request: Request) -> JSONResponse:
    """List all tools from all backends.

    GET /admin/tools
    """
    session_maker = request.app.state.session_maker

    async with session_maker() as session:
        tool_repo = ToolRepository(session)
        tools = await tool_repo.list_all()

        backend_repo = BackendRepository(session)

        tool_responses = []
        for tool in tools:
            backend = await backend_repo.get_by_id(tool.backend_id)
            backend_name = backend.name if backend else "unknown"
            tool_responses.append(
                ToolResponse(
                    id=tool.id,
                    backend_name=backend_name,
                    name=tool.name,
                    prefixed_name=tool.prefixed_name,
                    description=tool.description,
                    input_schema=tool.input_schema,
                    refreshed_at=tool.refreshed_at,
                ).model_dump(mode="json")
            )

    return _json_response(
        ToolListResponse(
            tools=tool_responses,
            total=len(tool_responses),
        ).model_dump(mode="json")
    )


# ============================================================================
# Metrics Routes
# ============================================================================


async def get_metrics(request: Request) -> JSONResponse:
    """Get aggregated metrics for all tool calls.

    GET /admin/metrics
    Query params:
        - backend: Filter by backend name (optional)
    """
    backend_name = request.query_params.get("backend")
    session_maker = request.app.state.session_maker

    async with session_maker() as session:
        repo = ToolCallRepository(session)
        stats = await repo.get_stats(backend_name=backend_name)

    return _json_response(
        MetricsResponse(
            total_calls=stats["total_calls"],
            success_count=stats["success_count"],
            error_count=stats["error_count"],
            success_rate=stats["success_rate"],
            avg_latency_ms=stats["avg_latency_ms"],
            min_latency_ms=stats["min_latency_ms"],
            max_latency_ms=stats["max_latency_ms"],
        ).model_dump()
    )


# ============================================================================
# Route definitions
# ============================================================================


def get_admin_routes() -> list[Route]:
    """Get all admin API routes."""
    return [
        # Backend routes
        Route("/admin/backends", list_backends, methods=["GET"]),
        Route("/admin/backends", create_backend, methods=["POST"]),
        Route("/admin/backends/{name}", get_backend, methods=["GET"]),
        Route("/admin/backends/{name}", update_backend, methods=["PUT"]),
        Route("/admin/backends/{name}", delete_backend, methods=["DELETE"]),
        Route("/admin/backends/{name}/refresh", refresh_backend, methods=["POST"]),
        Route("/admin/backends/{name}/enable", enable_backend, methods=["POST"]),
        Route("/admin/backends/{name}/disable", disable_backend, methods=["POST"]),
        # Tool routes
        Route("/admin/tools", list_tools, methods=["GET"]),
        # Metrics routes
        Route("/admin/metrics", get_metrics, methods=["GET"]),
    ]

"""Admin API routes for managing backends."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from forge_armory.admin.schemas import (
    BackendCreateRequest,
    BackendListResponse,
    BackendResponse,
    BackendUpdateRequest,
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
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from forge_armory.gateway import BackendManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


# ============================================================================
# Dependencies
# ============================================================================


async def get_session_maker(request: Request) -> async_sessionmaker[AsyncSession]:
    """Get session maker from app state."""
    return request.app.state.session_maker


async def get_manager(request: Request) -> BackendManager:
    """Get backend manager from app state."""
    return request.app.state.backend_manager


SessionMakerDep = Annotated["async_sessionmaker[AsyncSession]", Depends(get_session_maker)]
ManagerDep = Annotated["BackendManager", Depends(get_manager)]


# ============================================================================
# Backend Routes
# ============================================================================


@router.get("/backends", response_model=BackendListResponse)
async def list_backends(session_maker: SessionMakerDep) -> BackendListResponse:
    """List all backends."""
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
                )
            )

    return BackendListResponse(
        backends=backend_responses,
        total=len(backend_responses),
    )


@router.post("/backends", response_model=BackendResponse, status_code=201)
async def create_backend(
    data: BackendCreateRequest,
    session_maker: SessionMakerDep,
    manager: ManagerDep,
) -> BackendResponse:
    """Create a new backend and connect to it."""
    async with session_maker() as session:
        repo = BackendRepository(session)

        # Check if backend already exists
        existing = await repo.get_by_name(data.name)
        if existing:
            raise HTTPException(status_code=409, detail=f"Backend '{data.name}' already exists")

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

        return BackendResponse(
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
        )


@router.get("/backends/{name}", response_model=BackendResponse)
async def get_backend(name: str, session_maker: SessionMakerDep) -> BackendResponse:
    """Get a backend by name."""
    async with session_maker() as session:
        repo = BackendRepository(session)
        backend = await repo.get_by_name(name)

        if not backend:
            raise HTTPException(status_code=404, detail=f"Backend '{name}' not found")

        tool_repo = ToolRepository(session)
        tools = await tool_repo.list_by_backend(backend.id)

        return BackendResponse(
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
        )


@router.put("/backends/{name}", response_model=BackendResponse)
async def update_backend(
    name: str,
    data: BackendUpdateRequest,
    session_maker: SessionMakerDep,
) -> BackendResponse:
    """Update a backend."""
    async with session_maker() as session:
        repo = BackendRepository(session)
        # Only pass fields that were explicitly set in the request
        update_data = data.model_dump(exclude_unset=True)
        backend = await repo.update(name, BackendUpdate(**update_data))

        if not backend:
            raise HTTPException(status_code=404, detail=f"Backend '{name}' not found")

        await session.commit()

        tool_repo = ToolRepository(session)
        tools = await tool_repo.list_by_backend(backend.id)

        return BackendResponse(
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
        )


@router.delete("/backends/{name}", response_model=MessageResponse)
async def delete_backend(
    name: str,
    session_maker: SessionMakerDep,
    manager: ManagerDep,
) -> MessageResponse:
    """Delete a backend."""
    # Disconnect if connected
    await manager.remove_backend(name)

    async with session_maker() as session:
        repo = BackendRepository(session)
        deleted = await repo.delete(name)

        if not deleted:
            raise HTTPException(status_code=404, detail=f"Backend '{name}' not found")

        await session.commit()

    return MessageResponse(message=f"Backend '{name}' deleted")


@router.post("/backends/{name}/refresh", response_model=RefreshResponse)
async def refresh_backend(
    name: str,
    session_maker: SessionMakerDep,
    manager: ManagerDep,
) -> RefreshResponse:
    """Refresh a backend's tools."""
    # Check backend exists
    async with session_maker() as session:
        repo = BackendRepository(session)
        backend = await repo.get_by_name(name)

        if not backend:
            raise HTTPException(status_code=404, detail=f"Backend '{name}' not found")

    # If not connected, try to connect first
    if name not in manager.connected_backends:
        try:
            tools = await manager.add_backend(backend)
        except BackendConnectionError as e:
            raise HTTPException(
                status_code=503, detail=f"Failed to connect to backend: {e}"
            ) from e
    else:
        try:
            tools = await manager.refresh_backend(name)
        except BackendNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except BackendConnectionError as e:
            raise HTTPException(
                status_code=503, detail=f"Failed to refresh backend: {e}"
            ) from e

    return RefreshResponse(
        backend_name=name,
        tools_count=len(tools),
        tools=[t.name for t in tools],
    )


@router.post("/backends/{name}/enable", response_model=BackendResponse)
async def enable_backend(
    name: str,
    session_maker: SessionMakerDep,
    manager: ManagerDep,
) -> BackendResponse:
    """Enable a backend and connect to it."""
    async with session_maker() as session:
        repo = BackendRepository(session)
        backend = await repo.set_enabled(name, enabled=True)

        if not backend:
            raise HTTPException(status_code=404, detail=f"Backend '{name}' not found")

        await session.commit()

        # Try to connect
        if name not in manager.connected_backends:
            try:
                await manager.add_backend(backend)
            except BackendConnectionError as e:
                logger.warning("Failed to connect to enabled backend %s: %s", name, e)

        tool_repo = ToolRepository(session)
        tools = await tool_repo.list_by_backend(backend.id)

        return BackendResponse(
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
        )


@router.post("/backends/{name}/disable", response_model=BackendResponse)
async def disable_backend(
    name: str,
    session_maker: SessionMakerDep,
    manager: ManagerDep,
) -> BackendResponse:
    """Disable a backend and disconnect from it."""
    # Disconnect if connected
    await manager.remove_backend(name)

    async with session_maker() as session:
        repo = BackendRepository(session)
        backend = await repo.set_enabled(name, enabled=False)

        if not backend:
            raise HTTPException(status_code=404, detail=f"Backend '{name}' not found")

        await session.commit()

        tool_repo = ToolRepository(session)
        tools = await tool_repo.list_by_backend(backend.id)

        return BackendResponse(
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
        )


# ============================================================================
# Tool Routes
# ============================================================================


@router.get("/tools", response_model=ToolListResponse)
async def list_tools(session_maker: SessionMakerDep) -> ToolListResponse:
    """List all tools from all backends."""
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
                )
            )

    return ToolListResponse(
        tools=tool_responses,
        total=len(tool_responses),
    )


# ============================================================================
# Metrics Routes
# ============================================================================


@router.get("/metrics", response_model=MetricsResponse)
async def get_metrics(
    session_maker: SessionMakerDep,
    backend: Annotated[str | None, Query(description="Filter by backend name")] = None,
) -> MetricsResponse:
    """Get aggregated metrics for all tool calls."""
    async with session_maker() as session:
        repo = ToolCallRepository(session)
        stats = await repo.get_stats(backend_name=backend)

    return MetricsResponse(
        total_calls=stats["total_calls"],
        success_count=stats["success_count"],
        error_count=stats["error_count"],
        success_rate=stats["success_rate"],
        avg_latency_ms=stats["avg_latency_ms"],
        min_latency_ms=stats["min_latency_ms"],
        max_latency_ms=stats["max_latency_ms"],
    )

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
    EnhancedMetricsResponse,
    MessageResponse,
    MetricsResponse,
    RefreshResponse,
    TimeSeriesPoint,
    TimeSeriesResponse,
    ToolCallListResponse,
    ToolCallResponse,
    ToolListResponse,
    ToolMetricsListResponse,
    ToolMetricsResponse,
    ToolRagConfigResponse,
    ToolRagConfigUpdateRequest,
    ToolRagPreviewResponse,
    ToolRagRegenerateResponse,
    ToolRagStatusResponse,
    ToolResponse,
)
from forge_armory.db import (
    BackendCreate,
    BackendRepository,
    BackendUpdate,
    ToolCallRepository,
    ToolRepository,
)
from forge_armory.db.repository import ToolRAGConfigRepository, parse_time_period
from forge_armory.gateway import (
    BackendConnectionError,
    BackendNotFoundError,
)
from forge_armory.settings import settings
from forge_armory.toolrag import render_manifest

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


@router.get("/metrics/enhanced", response_model=EnhancedMetricsResponse)
async def get_enhanced_metrics(
    session_maker: SessionMakerDep,
    backend: Annotated[str | None, Query(description="Filter by backend name")] = None,
    tool: Annotated[str | None, Query(description="Filter by tool name")] = None,
    period: Annotated[str | None, Query(description="Time period (1h, 24h, 7d, 30d, all)")] = None,
) -> EnhancedMetricsResponse:
    """Get enhanced metrics with percentile latencies."""
    since = parse_time_period(period) if period else None

    async with session_maker() as session:
        repo = ToolCallRepository(session)
        stats = await repo.get_stats_with_percentiles(
            backend_name=backend,
            tool_name=tool,
            since=since,
        )

    return EnhancedMetricsResponse(
        total_calls=stats["total_calls"],
        success_count=stats["success_count"],
        error_count=stats["error_count"],
        success_rate=stats["success_rate"],
        avg_latency_ms=stats["avg_latency_ms"],
        min_latency_ms=stats["min_latency_ms"],
        max_latency_ms=stats["max_latency_ms"],
        p50_latency_ms=stats["p50_latency_ms"],
        p95_latency_ms=stats["p95_latency_ms"],
        p99_latency_ms=stats["p99_latency_ms"],
    )


@router.get("/metrics/calls", response_model=ToolCallListResponse)
async def list_tool_calls(
    session_maker: SessionMakerDep,
    backend: Annotated[str | None, Query(description="Filter by backend name")] = None,
    tool: Annotated[str | None, Query(description="Filter by tool name")] = None,
    success: Annotated[bool | None, Query(description="Filter by success status")] = None,
    period: Annotated[str | None, Query(description="Time period (1h, 24h, 7d, 30d, all)")] = None,
    limit: Annotated[int, Query(ge=1, le=1000, description="Max results")] = 100,
    offset: Annotated[int, Query(ge=0, description="Pagination offset")] = 0,
) -> ToolCallListResponse:
    """List tool calls with pagination and filtering."""
    since = parse_time_period(period) if period else None

    async with session_maker() as session:
        repo = ToolCallRepository(session)

        # Get paginated calls
        calls = await repo.list_paginated(
            backend_name=backend,
            tool_name=tool,
            success=success,
            since=since,
            limit=limit,
            offset=offset,
        )

        # Get total count for pagination
        total = await repo.count(
            backend_name=backend,
            tool_name=tool,
            success=success,
            since=since,
        )

    return ToolCallListResponse(
        calls=[
            ToolCallResponse(
                id=call.id,
                tool_id=call.tool_id,
                backend_name=call.backend_name,
                tool_name=call.tool_name,
                arguments=call.arguments,
                success=call.success,
                error_message=call.error_message,
                latency_ms=call.latency_ms,
                called_at=call.called_at,
            )
            for call in calls
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/metrics/by-tool", response_model=ToolMetricsListResponse)
async def get_tool_metrics(
    session_maker: SessionMakerDep,
    backend: Annotated[str | None, Query(description="Filter by backend name")] = None,
    period: Annotated[str | None, Query(description="Time period (1h, 24h, 7d, 30d, all)")] = None,
    order_by: Annotated[
        str, Query(description="Sort field (total_calls, error_count, avg_latency_ms, p95_latency_ms)")
    ] = "total_calls",
    order: Annotated[str, Query(description="Sort order (asc, desc)")] = "desc",
    limit: Annotated[int, Query(ge=1, le=200, description="Max results")] = 50,
) -> ToolMetricsListResponse:
    """Get per-tool aggregated metrics."""
    since = parse_time_period(period) if period else None

    async with session_maker() as session:
        repo = ToolCallRepository(session)
        metrics = await repo.get_tool_metrics(
            backend_name=backend,
            since=since,
            order_by=order_by,
            order=order,
            limit=limit,
        )

    return ToolMetricsListResponse(
        tools=[
            ToolMetricsResponse(
                tool_name=m["tool_name"],
                backend_name=m["backend_name"],
                total_calls=m["total_calls"],
                success_count=m["success_count"],
                error_count=m["error_count"],
                success_rate=m["success_rate"],
                avg_latency_ms=m["avg_latency_ms"],
                min_latency_ms=m["min_latency_ms"],
                max_latency_ms=m["max_latency_ms"],
                p95_latency_ms=m["p95_latency_ms"],
                last_called_at=m["last_called_at"],
            )
            for m in metrics
        ],
        total=len(metrics),
    )


@router.get("/metrics/timeseries", response_model=TimeSeriesResponse)
async def get_timeseries(
    session_maker: SessionMakerDep,
    period: Annotated[str, Query(description="Time period (1h, 24h, 7d, 30d)")] = "24h",
    backend: Annotated[str | None, Query(description="Filter by backend name")] = None,
    tool: Annotated[str | None, Query(description="Filter by tool name")] = None,
    granularity: Annotated[str | None, Query(description="Granularity (minute, hour, day)")] = None,
) -> TimeSeriesResponse:
    """Get time-bucketed metrics for charts."""
    since = parse_time_period(period)

    # Auto-select granularity based on period if not specified
    if not granularity:
        if period in ("1h", "2h"):
            granularity = "minute"
        elif period in ("24h", "7d"):
            granularity = "hour"
        else:
            granularity = "day"

    async with session_maker() as session:
        repo = ToolCallRepository(session)
        data = await repo.get_timeseries(
            backend_name=backend,
            tool_name=tool,
            since=since,
            granularity=granularity,
        )

    return TimeSeriesResponse(
        period=period,
        granularity=granularity,
        data=[
            TimeSeriesPoint(
                timestamp=d["timestamp"],
                total_calls=d["total_calls"],
                success_count=d["success_count"],
                error_count=d["error_count"],
                avg_latency_ms=d["avg_latency_ms"],
            )
            for d in data
        ],
    )


# ============================================================================
# Tool RAG Routes
# ============================================================================


@router.get("/tool-rag/config", response_model=ToolRagConfigResponse)
async def get_tool_rag_config(session_maker: SessionMakerDep) -> ToolRagConfigResponse:
    """Get Tool RAG configuration."""
    async with session_maker() as session:
        repo = ToolRAGConfigRepository(session)
        config = await repo.get_or_create()
        await session.commit()

        return ToolRagConfigResponse(
            id=config.id,
            capability_manifest=config.capability_manifest,
            tools_hash=config.tools_hash,
            default_threshold=config.default_threshold,
            default_max_results=config.default_max_results,
            updated_at=config.updated_at,
        )


@router.put("/tool-rag/config", response_model=ToolRagConfigResponse)
async def update_tool_rag_config(
    data: ToolRagConfigUpdateRequest,
    session_maker: SessionMakerDep,
) -> ToolRagConfigResponse:
    """Update Tool RAG configuration."""
    async with session_maker() as session:
        repo = ToolRAGConfigRepository(session)
        config = await repo.get_or_create()

        # Update fields if provided
        if data.capability_manifest is not None:
            config.capability_manifest = data.capability_manifest
        if data.default_threshold is not None:
            config.default_threshold = data.default_threshold
        if data.default_max_results is not None:
            config.default_max_results = data.default_max_results

        await session.commit()

        return ToolRagConfigResponse(
            id=config.id,
            capability_manifest=config.capability_manifest,
            tools_hash=config.tools_hash,
            default_threshold=config.default_threshold,
            default_max_results=config.default_max_results,
            updated_at=config.updated_at,
        )


@router.get("/tool-rag/status", response_model=ToolRagStatusResponse)
async def get_tool_rag_status(session_maker: SessionMakerDep) -> ToolRagStatusResponse:
    """Get Tool RAG embedding status."""
    async with session_maker() as session:
        tool_repo = ToolRepository(session)
        total_tools, indexed_tools = await tool_repo.count_with_embeddings()

    indexing_percentage = (indexed_tools / total_tools * 100) if total_tools > 0 else 0.0

    return ToolRagStatusResponse(
        enabled=settings.toolrag_enabled,
        embedding_model=settings.toolrag_embedding_model,
        total_tools=total_tools,
        indexed_tools=indexed_tools,
        indexing_percentage=round(indexing_percentage, 1),
    )


@router.post("/tool-rag/regenerate", response_model=ToolRagRegenerateResponse)
async def regenerate_embeddings(session_maker: SessionMakerDep) -> ToolRagRegenerateResponse:
    """Regenerate embeddings for all tools."""
    if not settings.toolrag_enabled:
        raise HTTPException(
            status_code=400,
            detail="Tool RAG is not enabled. Set ARMORY_TOOLRAG_ENABLED=true to enable.",
        )

    async with session_maker() as session:
        tool_repo = ToolRepository(session)
        tools_processed = await tool_repo.regenerate_all_embeddings()
        await session.commit()

        # Get updated counts
        _total_tools, indexed_tools = await tool_repo.count_with_embeddings()

    return ToolRagRegenerateResponse(
        message=f"Successfully regenerated embeddings for {tools_processed} tools",
        tools_processed=tools_processed,
        tools_indexed=indexed_tools,
    )


@router.get("/tool-rag/preview", response_model=ToolRagPreviewResponse)
async def preview_manifest(session_maker: SessionMakerDep) -> ToolRagPreviewResponse:
    """Preview the rendered capability manifest.

    Shows both the template and the rendered result with {{TOOL_LIST}} replaced.
    """
    async with session_maker() as session:
        config_repo = ToolRAGConfigRepository(session)
        config = await config_repo.get_or_create()
        template = config.capability_manifest

        tool_repo = ToolRepository(session)
        tools = await tool_repo.list_all()

    rendered = render_manifest(template, tools)

    return ToolRagPreviewResponse(
        template=template,
        rendered=rendered,
        tool_count=len(tools),
    )

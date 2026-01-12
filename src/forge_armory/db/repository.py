"""Repository layer for database operations."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import selectinload

from forge_armory.db.models import Backend, Tool, ToolCall

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

# ============================================================================
# Pydantic schemas for CRUD operations
# ============================================================================


class BackendCreate(BaseModel):
    """Schema for creating a backend."""

    name: str = Field(min_length=1, max_length=100)
    url: str | None = None
    command: list[str] | None = None
    enabled: bool = True
    timeout: float = Field(default=30.0, ge=1.0, le=300.0)
    prefix: str | None = Field(default=None, max_length=100)
    mount_enabled: bool = True


class BackendUpdate(BaseModel):
    """Schema for updating a backend."""

    url: str | None = None
    command: list[str] | None = None
    enabled: bool | None = None
    timeout: float | None = Field(default=None, ge=1.0, le=300.0)
    prefix: str | None = None
    mount_enabled: bool | None = None


class ToolInfo(BaseModel):
    """Tool information from an MCP server."""

    name: str
    description: str | None = None
    input_schema: dict


class ToolCallCreate(BaseModel):
    """Schema for creating a tool call record."""

    backend_name: str
    tool_name: str
    arguments: dict
    success: bool
    error_message: str | None = None
    latency_ms: int
    # Request context fields
    client_ip: str | None = None
    request_id: str | None = None
    session_id: str | None = None
    caller: str | None = None


# ============================================================================
# Backend Repository
# ============================================================================


class BackendRepository:
    """Repository for backend CRUD operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_all(self, enabled_only: bool = False) -> list[Backend]:
        """List all backends, optionally filtering by enabled status."""
        stmt = select(Backend).order_by(Backend.name)
        if enabled_only:
            stmt = stmt.where(Backend.enabled == True)  # noqa: E712
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, backend_id: uuid.UUID) -> Backend | None:
        """Get a backend by ID."""
        stmt = select(Backend).where(Backend.id == backend_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Backend | None:
        """Get a backend by name."""
        stmt = select(Backend).where(Backend.name == name)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_name_with_tools(self, name: str) -> Backend | None:
        """Get a backend by name with tools eagerly loaded."""
        stmt = (
            select(Backend)
            .where(Backend.name == name)
            .options(selectinload(Backend.tools))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, data: BackendCreate) -> Backend:
        """Create a new backend."""
        backend = Backend(
            name=data.name,
            url=data.url,
            command=data.command,
            enabled=data.enabled,
            timeout=data.timeout,
            prefix=data.prefix,
            mount_enabled=data.mount_enabled,
        )
        self.session.add(backend)
        await self.session.flush()
        return backend

    async def update(self, name: str, data: BackendUpdate) -> Backend | None:
        """Update an existing backend."""
        backend = await self.get_by_name(name)
        if not backend:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(backend, key, value)

        await self.session.flush()
        return backend

    async def delete(self, name: str) -> bool:
        """Delete a backend by name."""
        backend = await self.get_by_name(name)
        if not backend:
            return False

        await self.session.delete(backend)
        await self.session.flush()
        return True

    async def set_enabled(self, name: str, enabled: bool) -> Backend | None:
        """Enable or disable a backend."""
        backend = await self.get_by_name(name)
        if not backend:
            return None

        backend.enabled = enabled
        await self.session.flush()
        return backend


# ============================================================================
# Tool Repository
# ============================================================================


class ToolRepository:
    """Repository for tool CRUD operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_all(self) -> list[Tool]:
        """List all tools."""
        stmt = select(Tool).order_by(Tool.prefixed_name)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_backend(self, backend_id: uuid.UUID) -> list[Tool]:
        """List all tools for a backend."""
        stmt = (
            select(Tool)
            .where(Tool.backend_id == backend_id)
            .order_by(Tool.name)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_prefixed_name(self, prefixed_name: str) -> Tool | None:
        """Get a tool by its prefixed name."""
        stmt = select(Tool).where(Tool.prefixed_name == prefixed_name)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def refresh_backend_tools(
        self,
        backend: Backend,
        tools: list[ToolInfo],
    ) -> list[Tool]:
        """Replace all tools for a backend with new tools."""
        # Delete existing tools
        stmt = delete(Tool).where(Tool.backend_id == backend.id)
        await self.session.execute(stmt)

        # Create new tools
        prefix = backend.effective_prefix
        new_tools = []
        now = datetime.now(UTC).replace(tzinfo=None)

        for tool_info in tools:
            prefixed_name = f"{prefix}__{tool_info.name}"
            tool = Tool(
                backend_id=backend.id,
                name=tool_info.name,
                prefixed_name=prefixed_name,
                description=tool_info.description,
                input_schema=tool_info.input_schema,
                refreshed_at=now,
            )
            self.session.add(tool)
            new_tools.append(tool)

        await self.session.flush()
        return new_tools


# ============================================================================
# Tool Call Repository
# ============================================================================


class ToolCallRepository:
    """Repository for tool call metrics."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, data: ToolCallCreate, tool_id: uuid.UUID | None = None) -> ToolCall:
        """Record a tool call."""
        tool_call = ToolCall(
            tool_id=tool_id,
            backend_name=data.backend_name,
            tool_name=data.tool_name,
            arguments=data.arguments,
            success=data.success,
            error_message=data.error_message,
            latency_ms=data.latency_ms,
            client_ip=data.client_ip,
            request_id=data.request_id,
            session_id=data.session_id,
            caller=data.caller,
        )
        self.session.add(tool_call)
        await self.session.flush()
        return tool_call

    async def list_recent(
        self,
        backend_name: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[ToolCall]:
        """List recent tool calls."""
        stmt = select(ToolCall).order_by(ToolCall.called_at.desc()).limit(limit)

        if backend_name:
            stmt = stmt.where(ToolCall.backend_name == backend_name)
        if since:
            stmt = stmt.where(ToolCall.called_at >= since)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_stats(
        self,
        backend_name: str | None = None,
        since: datetime | None = None,
    ) -> dict:
        """Get aggregated statistics for tool calls."""
        stmt = select(ToolCall)

        if backend_name:
            stmt = stmt.where(ToolCall.backend_name == backend_name)
        if since:
            stmt = stmt.where(ToolCall.called_at >= since)

        result = await self.session.execute(stmt)
        calls = list(result.scalars().all())

        if not calls:
            return {
                "total_calls": 0,
                "success_count": 0,
                "error_count": 0,
                "success_rate": 0.0,
                "avg_latency_ms": 0.0,
                "min_latency_ms": 0,
                "max_latency_ms": 0,
            }

        success_count = sum(1 for c in calls if c.success)
        error_count = len(calls) - success_count
        latencies = [c.latency_ms for c in calls]

        return {
            "total_calls": len(calls),
            "success_count": success_count,
            "error_count": error_count,
            "success_rate": success_count / len(calls) if calls else 0.0,
            "avg_latency_ms": sum(latencies) / len(latencies) if latencies else 0.0,
            "min_latency_ms": min(latencies) if latencies else 0,
            "max_latency_ms": max(latencies) if latencies else 0,
        }

    async def get_stats_with_percentiles(
        self,
        backend_name: str | None = None,
        tool_name: str | None = None,
        since: datetime | None = None,
    ) -> dict:
        """Get aggregated statistics including percentile latencies."""
        stmt = select(ToolCall)

        if backend_name:
            stmt = stmt.where(ToolCall.backend_name == backend_name)
        if tool_name:
            stmt = stmt.where(ToolCall.tool_name == tool_name)
        if since:
            stmt = stmt.where(ToolCall.called_at >= since)

        result = await self.session.execute(stmt)
        calls = list(result.scalars().all())

        if not calls:
            return {
                "total_calls": 0,
                "success_count": 0,
                "error_count": 0,
                "success_rate": 0.0,
                "avg_latency_ms": 0.0,
                "min_latency_ms": 0,
                "max_latency_ms": 0,
                "p50_latency_ms": None,
                "p95_latency_ms": None,
                "p99_latency_ms": None,
            }

        success_count = sum(1 for c in calls if c.success)
        error_count = len(calls) - success_count
        latencies = sorted([c.latency_ms for c in calls])

        return {
            "total_calls": len(calls),
            "success_count": success_count,
            "error_count": error_count,
            "success_rate": success_count / len(calls) if calls else 0.0,
            "avg_latency_ms": sum(latencies) / len(latencies) if latencies else 0.0,
            "min_latency_ms": min(latencies) if latencies else 0,
            "max_latency_ms": max(latencies) if latencies else 0,
            "p50_latency_ms": _percentile(latencies, 50),
            "p95_latency_ms": _percentile(latencies, 95),
            "p99_latency_ms": _percentile(latencies, 99),
        }

    async def list_paginated(
        self,
        backend_name: str | None = None,
        tool_name: str | None = None,
        success: bool | None = None,
        since: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ToolCall]:
        """List tool calls with pagination and filtering."""
        stmt = (
            select(ToolCall)
            .order_by(ToolCall.called_at.desc())
            .limit(limit)
            .offset(offset)
        )

        if backend_name:
            stmt = stmt.where(ToolCall.backend_name == backend_name)
        if tool_name:
            stmt = stmt.where(ToolCall.tool_name == tool_name)
        if success is not None:
            stmt = stmt.where(ToolCall.success == success)
        if since:
            stmt = stmt.where(ToolCall.called_at >= since)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count(
        self,
        backend_name: str | None = None,
        tool_name: str | None = None,
        success: bool | None = None,
        since: datetime | None = None,
    ) -> int:
        """Count tool calls matching the filters."""
        stmt = select(func.count(ToolCall.id))

        if backend_name:
            stmt = stmt.where(ToolCall.backend_name == backend_name)
        if tool_name:
            stmt = stmt.where(ToolCall.tool_name == tool_name)
        if success is not None:
            stmt = stmt.where(ToolCall.success == success)
        if since:
            stmt = stmt.where(ToolCall.called_at >= since)

        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def get_tool_metrics(
        self,
        backend_name: str | None = None,
        since: datetime | None = None,
        order_by: str = "total_calls",
        order: str = "desc",
        limit: int = 50,
    ) -> list[dict]:
        """Get per-tool aggregated metrics."""
        stmt = select(ToolCall)

        if backend_name:
            stmt = stmt.where(ToolCall.backend_name == backend_name)
        if since:
            stmt = stmt.where(ToolCall.called_at >= since)

        result = await self.session.execute(stmt)
        calls = list(result.scalars().all())

        # Group by (backend_name, tool_name)
        tool_data: dict[tuple[str, str], list[ToolCall]] = defaultdict(list)
        for call in calls:
            key = (call.backend_name, call.tool_name)
            tool_data[key].append(call)

        # Calculate metrics per tool
        metrics = []
        for (backend, tool), tool_calls in tool_data.items():
            success_count = sum(1 for c in tool_calls if c.success)
            error_count = len(tool_calls) - success_count
            latencies = sorted([c.latency_ms for c in tool_calls])
            last_called = max(c.called_at for c in tool_calls) if tool_calls else None

            metrics.append({
                "tool_name": tool,
                "backend_name": backend,
                "total_calls": len(tool_calls),
                "success_count": success_count,
                "error_count": error_count,
                "success_rate": success_count / len(tool_calls) if tool_calls else 0.0,
                "avg_latency_ms": sum(latencies) / len(latencies) if latencies else 0.0,
                "min_latency_ms": min(latencies) if latencies else 0,
                "max_latency_ms": max(latencies) if latencies else 0,
                "p95_latency_ms": _percentile(latencies, 95),
                "last_called_at": last_called,
            })

        # Sort
        reverse = order == "desc"
        if order_by in ("total_calls", "error_count", "avg_latency_ms", "p95_latency_ms"):
            metrics.sort(key=lambda x: x.get(order_by, 0) or 0, reverse=reverse)
        elif order_by == "last_called_at":
            metrics.sort(
                key=lambda x: x.get("last_called_at") or datetime.min.replace(tzinfo=None),
                reverse=reverse,
            )
        else:
            metrics.sort(key=lambda x: x.get("total_calls", 0), reverse=reverse)

        return metrics[:limit]

    async def get_timeseries(
        self,
        backend_name: str | None = None,
        tool_name: str | None = None,
        since: datetime | None = None,
        granularity: str = "hour",
    ) -> list[dict]:
        """Get time-bucketed metrics for charts."""
        stmt = select(ToolCall).order_by(ToolCall.called_at.asc())

        if backend_name:
            stmt = stmt.where(ToolCall.backend_name == backend_name)
        if tool_name:
            stmt = stmt.where(ToolCall.tool_name == tool_name)
        if since:
            stmt = stmt.where(ToolCall.called_at >= since)

        result = await self.session.execute(stmt)
        calls = list(result.scalars().all())

        if not calls:
            return []

        # Bucket calls by time
        buckets: dict[datetime, list[ToolCall]] = defaultdict(list)
        for call in calls:
            bucket_time = _truncate_to_granularity(call.called_at, granularity)
            buckets[bucket_time].append(call)

        # Calculate metrics per bucket
        timeseries = []
        for timestamp in sorted(buckets.keys()):
            bucket_calls = buckets[timestamp]
            success_count = sum(1 for c in bucket_calls if c.success)
            error_count = len(bucket_calls) - success_count
            latencies = [c.latency_ms for c in bucket_calls]

            timeseries.append({
                "timestamp": timestamp,
                "total_calls": len(bucket_calls),
                "success_count": success_count,
                "error_count": error_count,
                "avg_latency_ms": sum(latencies) / len(latencies) if latencies else 0.0,
            })

        return timeseries


# ============================================================================
# Helper Functions
# ============================================================================


def _percentile(sorted_values: list[int], percentile: int) -> int | None:
    """Calculate percentile from a sorted list of values."""
    if not sorted_values:
        return None
    index = int(len(sorted_values) * percentile / 100)
    return sorted_values[min(index, len(sorted_values) - 1)]


def _truncate_to_granularity(dt: datetime, granularity: str) -> datetime:
    """Truncate datetime to the specified granularity."""
    if granularity == "minute":
        return dt.replace(second=0, microsecond=0)
    elif granularity == "hour":
        return dt.replace(minute=0, second=0, microsecond=0)
    elif granularity == "day":
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        # Default to hour
        return dt.replace(minute=0, second=0, microsecond=0)


def parse_time_period(period: str) -> datetime | None:
    """Parse a time period string into a datetime for 'since' filtering.

    Supported formats: "1h", "24h", "7d", "30d", "all"
    """
    if period == "all" or not period:
        return None

    now = datetime.now(UTC).replace(tzinfo=None)

    if period.endswith("h"):
        hours = int(period[:-1])
        return now - timedelta(hours=hours)
    elif period.endswith("d"):
        days = int(period[:-1])
        return now - timedelta(days=days)
    elif period.endswith("m"):
        minutes = int(period[:-1])
        return now - timedelta(minutes=minutes)

    return None

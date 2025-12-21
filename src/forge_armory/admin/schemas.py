"""Pydantic schemas for Admin API request/response models."""

from __future__ import annotations

# Pydantic requires these at runtime for model validation - cannot be in TYPE_CHECKING
from datetime import datetime  # noqa: TC003
from uuid import UUID  # noqa: TC003

from pydantic import BaseModel, Field

# ============================================================================
# Backend Schemas
# ============================================================================


class BackendCreateRequest(BaseModel):
    """Request body for creating a backend."""

    name: str = Field(min_length=1, max_length=100)
    url: str = Field(min_length=1)
    enabled: bool = True
    timeout: float = Field(default=30.0, ge=1.0, le=300.0)
    prefix: str | None = Field(default=None, max_length=100)
    mount_enabled: bool = True


class BackendUpdateRequest(BaseModel):
    """Request body for updating a backend."""

    url: str | None = None
    enabled: bool | None = None
    timeout: float | None = Field(default=None, ge=1.0, le=300.0)
    prefix: str | None = None
    mount_enabled: bool | None = None


class BackendResponse(BaseModel):
    """Response model for a backend."""

    id: UUID
    name: str
    url: str | None
    enabled: bool
    timeout: float
    prefix: str | None
    mount_enabled: bool
    effective_prefix: str
    created_at: datetime
    updated_at: datetime
    tool_count: int = 0

    model_config = {"from_attributes": True}


class BackendListResponse(BaseModel):
    """Response model for listing backends."""

    backends: list[BackendResponse]
    total: int


# ============================================================================
# Tool Schemas
# ============================================================================


class ToolResponse(BaseModel):
    """Response model for a tool."""

    id: UUID
    backend_name: str
    name: str
    prefixed_name: str
    description: str | None
    input_schema: dict
    refreshed_at: datetime

    model_config = {"from_attributes": True}


class ToolListResponse(BaseModel):
    """Response model for listing tools."""

    tools: list[ToolResponse]
    total: int


# ============================================================================
# Metrics Schemas
# ============================================================================


class MetricsResponse(BaseModel):
    """Response model for metrics."""

    total_calls: int
    success_count: int
    error_count: int
    success_rate: float
    avg_latency_ms: float
    min_latency_ms: int
    max_latency_ms: int


class BackendMetricsResponse(BaseModel):
    """Response model for per-backend metrics."""

    backend_name: str
    metrics: MetricsResponse


# ============================================================================
# Action Response Schemas
# ============================================================================


class RefreshResponse(BaseModel):
    """Response model for refresh action."""

    backend_name: str
    tools_count: int
    tools: list[str]


class MessageResponse(BaseModel):
    """Generic message response."""

    message: str


class ErrorResponse(BaseModel):
    """Error response model."""

    error: str
    detail: str | None = None

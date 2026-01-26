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
    api_key: str | None = Field(default=None, max_length=500)


class BackendUpdateRequest(BaseModel):
    """Request body for updating a backend."""

    url: str | None = None
    enabled: bool | None = None
    timeout: float | None = Field(default=None, ge=1.0, le=300.0)
    prefix: str | None = None
    mount_enabled: bool | None = None
    api_key: str | None = None


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
    # MCP session fields
    session_initialized: bool = False
    requires_session: bool = False
    has_api_key: bool = False  # Don't expose actual key
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


class EnhancedMetricsResponse(BaseModel):
    """Response model for enhanced metrics with percentiles."""

    total_calls: int
    success_count: int
    error_count: int
    success_rate: float
    avg_latency_ms: float
    min_latency_ms: int
    max_latency_ms: int
    p50_latency_ms: int | None = None
    p95_latency_ms: int | None = None
    p99_latency_ms: int | None = None


class BackendMetricsResponse(BaseModel):
    """Response model for per-backend metrics."""

    backend_name: str
    metrics: MetricsResponse


# ============================================================================
# Tool Call Schemas
# ============================================================================


class ToolCallResponse(BaseModel):
    """Response model for a single tool call."""

    id: UUID
    tool_id: UUID | None
    backend_name: str
    tool_name: str
    arguments: dict
    success: bool
    error_message: str | None
    latency_ms: int
    called_at: datetime
    # Request context fields
    client_ip: str | None = None
    request_id: str | None = None
    session_id: str | None = None
    caller: str | None = None

    model_config = {"from_attributes": True}


class ToolCallListResponse(BaseModel):
    """Response model for paginated tool call list."""

    calls: list[ToolCallResponse]
    total: int
    limit: int
    offset: int


# ============================================================================
# Tool Metrics Schemas
# ============================================================================


class ToolMetricsResponse(BaseModel):
    """Response model for per-tool metrics."""

    tool_name: str
    backend_name: str
    total_calls: int
    success_count: int
    error_count: int
    success_rate: float
    avg_latency_ms: float
    min_latency_ms: int
    max_latency_ms: int
    p95_latency_ms: int | None = None
    last_called_at: datetime | None = None


class ToolMetricsListResponse(BaseModel):
    """Response model for tool metrics list."""

    tools: list[ToolMetricsResponse]
    total: int


# ============================================================================
# Time Series Schemas
# ============================================================================


class TimeSeriesPoint(BaseModel):
    """Single data point in a time series."""

    timestamp: datetime
    total_calls: int
    success_count: int
    error_count: int
    avg_latency_ms: float


class TimeSeriesResponse(BaseModel):
    """Response model for time series metrics."""

    period: str
    granularity: str
    data: list[TimeSeriesPoint]


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


# ============================================================================
# Tool RAG Schemas
# ============================================================================


class ToolRagConfigResponse(BaseModel):
    """Response model for Tool RAG configuration."""

    id: int
    capability_manifest: str
    tools_hash: str
    default_threshold: float
    updated_at: datetime

    model_config = {"from_attributes": True}


class ToolRagConfigUpdateRequest(BaseModel):
    """Request body for updating Tool RAG configuration."""

    capability_manifest: str | None = None
    default_threshold: float | None = Field(default=None, ge=0.0, le=1.0)


class ToolRagStatusResponse(BaseModel):
    """Response model for Tool RAG status."""

    enabled: bool
    embedding_model: str
    total_tools: int
    indexed_tools: int
    indexing_percentage: float


class ToolRagRegenerateResponse(BaseModel):
    """Response model for embedding regeneration."""

    message: str
    tools_processed: int
    tools_indexed: int


class ToolRagPreviewResponse(BaseModel):
    """Response model for manifest preview."""

    template: str
    rendered: str
    tool_count: int

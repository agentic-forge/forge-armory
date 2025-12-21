"""Admin API for managing backends."""

from forge_armory.admin.routes import router
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

__all__ = [
    "router",
    "BackendCreateRequest",
    "BackendUpdateRequest",
    "BackendResponse",
    "BackendListResponse",
    "ToolResponse",
    "ToolListResponse",
    "MetricsResponse",
    "RefreshResponse",
    "MessageResponse",
    "ErrorResponse",
]

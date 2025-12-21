"""Admin API for managing backends."""

from forge_armory.admin.routes import get_admin_routes
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
    "get_admin_routes",
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

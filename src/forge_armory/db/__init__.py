"""Database layer for Forge Armory."""

from forge_armory.db.engine import (
    async_session_maker,
    close_db,
    engine,
    get_session,
    init_db,
)
from forge_armory.db.models import Backend, Base, Tool, ToolCall
from forge_armory.db.repository import (
    BackendCreate,
    BackendRepository,
    BackendUpdate,
    ToolCallCreate,
    ToolCallRepository,
    ToolInfo,
    ToolRepository,
)

__all__ = [
    # Engine
    "engine",
    "async_session_maker",
    "get_session",
    "init_db",
    "close_db",
    # Models
    "Base",
    "Backend",
    "Tool",
    "ToolCall",
    # Repository
    "BackendRepository",
    "BackendCreate",
    "BackendUpdate",
    "ToolRepository",
    "ToolInfo",
    "ToolCallRepository",
    "ToolCallCreate",
]

"""SQLAlchemy ORM models for Forge Armory."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class Backend(Base):
    """MCP backend server configuration."""

    __tablename__ = "backends"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=False,
    )
    url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    command: Mapped[list | None] = mapped_column(
        JSON,
        nullable=True,
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    timeout: Mapped[float] = mapped_column(
        Float,
        default=30.0,
        nullable=False,
    )
    prefix: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    mount_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        default=utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )

    # Relationships
    tools: Mapped[list[Tool]] = relationship(
        "Tool",
        back_populates="backend",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Backend(name={self.name!r}, enabled={self.enabled})>"

    @property
    def effective_prefix(self) -> str:
        """Get the effective prefix for tool namespacing."""
        return self.prefix if self.prefix else self.name


class Tool(Base):
    """Cached tool definition from a backend."""

    __tablename__ = "tools"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    backend_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("backends.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )
    prefixed_name: Mapped[str] = mapped_column(
        String(300),
        unique=True,
        index=True,
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    input_schema: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
    )
    refreshed_at: Mapped[datetime] = mapped_column(
        default=utcnow,
        nullable=False,
    )

    # Relationships
    backend: Mapped[Backend] = relationship(
        "Backend",
        back_populates="tools",
    )
    tool_calls: Mapped[list[ToolCall]] = relationship(
        "ToolCall",
        back_populates="tool",
    )

    def __repr__(self) -> str:
        return f"<Tool(prefixed_name={self.prefixed_name!r})>"


class ToolCall(Base):
    """Record of a tool call for metrics tracking."""

    __tablename__ = "tool_calls"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    tool_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tools.id", ondelete="SET NULL"),
        nullable=True,
    )
    backend_name: Mapped[str] = mapped_column(
        String(100),
        index=True,
        nullable=False,
    )
    tool_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )
    arguments: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
    )
    success: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    latency_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    called_at: Mapped[datetime] = mapped_column(
        default=utcnow,
        index=True,
        nullable=False,
    )

    # Relationships
    tool: Mapped[Tool | None] = relationship(
        "Tool",
        back_populates="tool_calls",
    )

    # Composite index for common queries
    __table_args__ = (
        Index("ix_tool_calls_backend_called_at", "backend_name", "called_at"),
    )

    def __repr__(self) -> str:
        return f"<ToolCall(tool_name={self.tool_name!r}, success={self.success})>"

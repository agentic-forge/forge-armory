"""Initial database schema.

Revision ID: 000_initial
Revises:
Create Date: 2024-12-01 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "000_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create backends table
    op.create_table(
        "backends",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("url", sa.String(500), nullable=True),
        sa.Column("command", postgresql.JSON(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, default=True),
        sa.Column("timeout", sa.Float(), nullable=False, default=30.0),
        sa.Column("prefix", sa.String(100), nullable=True),
        sa.Column("mount_enabled", sa.Boolean(), nullable=False, default=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_backends_name", "backends", ["name"], unique=True)

    # Create tools table
    op.create_table(
        "tools",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("backend_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("prefixed_name", sa.String(300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("input_schema", postgresql.JSON(), nullable=False),
        sa.Column("refreshed_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["backend_id"], ["backends.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tools_prefixed_name", "tools", ["prefixed_name"], unique=True)

    # Create tool_calls table (with all fields including request context)
    op.create_table(
        "tool_calls",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tool_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("backend_name", sa.String(100), nullable=False),
        sa.Column("tool_name", sa.String(200), nullable=False),
        sa.Column("arguments", postgresql.JSON(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("called_at", sa.DateTime(), nullable=False),
        # Request context fields
        sa.Column("client_ip", sa.String(45), nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("session_id", sa.String(64), nullable=True),
        sa.Column("caller", sa.String(200), nullable=True),
        sa.ForeignKeyConstraint(["tool_id"], ["tools.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tool_calls_backend_name", "tool_calls", ["backend_name"])
    op.create_index("ix_tool_calls_called_at", "tool_calls", ["called_at"])
    op.create_index("ix_tool_calls_backend_called_at", "tool_calls", ["backend_name", "called_at"])
    op.create_index("ix_tool_calls_client_ip", "tool_calls", ["client_ip"])
    op.create_index("ix_tool_calls_request_id", "tool_calls", ["request_id"])
    op.create_index("ix_tool_calls_caller", "tool_calls", ["caller"])


def downgrade() -> None:
    op.drop_table("tool_calls")
    op.drop_table("tools")
    op.drop_table("backends")

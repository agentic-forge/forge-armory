"""Add MCP session support fields to backends table.

Revision ID: 004
Revises: 003
Create Date: 2026-01-26 10:00:00.000000+00:00

Adds fields to store MCP session state per backend:
- session_id: The Mcp-Session-Id from upstream server
- session_initialized: Whether session handshake completed
- requires_session: Whether backend requires session management
- api_key: Optional API key for authenticated backends (e.g., HuggingFace)
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "backends",
        sa.Column("session_id", sa.String(200), nullable=True),
    )
    op.add_column(
        "backends",
        sa.Column("session_initialized", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "backends",
        sa.Column("requires_session", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "backends",
        sa.Column("api_key", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("backends", "api_key")
    op.drop_column("backends", "requires_session")
    op.drop_column("backends", "session_initialized")
    op.drop_column("backends", "session_id")

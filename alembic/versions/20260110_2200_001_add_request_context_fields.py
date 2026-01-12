"""Add request context fields to tool_calls table.

Revision ID: 001
Revises: 000_initial
Create Date: 2026-01-10 22:00:00.000000+00:00

Note: This migration is now a no-op because the columns were included
in the initial schema (000_initial). Kept for migration history.
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: str | None = "000_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """No-op: columns already exist in initial schema."""
    pass


def downgrade() -> None:
    """No-op: columns are part of initial schema."""
    pass

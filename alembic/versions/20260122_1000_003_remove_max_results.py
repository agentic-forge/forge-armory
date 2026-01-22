"""Remove default_max_results from tool_rag_config.

Revision ID: 003
Revises: 002
Create Date: 2026-01-22 10:00:00.000000+00:00

Tool RAG now returns all tools matching the similarity threshold,
rather than limiting to a maximum number of results.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("tool_rag_config", "default_max_results")


def downgrade() -> None:
    op.add_column(
        "tool_rag_config",
        sa.Column(
            "default_max_results",
            sa.Integer(),
            nullable=False,
            server_default="5",
        ),
    )

"""Add Tool RAG support.

Revision ID: 002
Revises: 001
Create Date: 2026-01-20 10:00:00.000000+00:00

Adds pgvector extension and embedding column to tools table for semantic search.
Creates tool_rag_config table for storing capability manifest.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Embedding dimensions for sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_DIMENSIONS = 384


def upgrade() -> None:
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Add embedding column to tools table
    op.add_column(
        "tools",
        sa.Column("embedding", Vector(EMBEDDING_DIMENSIONS), nullable=True),
    )

    # Create index for vector similarity search using cosine distance
    # Using ivfflat for approximate nearest neighbor (good balance of speed/accuracy)
    # Note: ivfflat requires data to be present for optimal index, but we create it
    # here anyway - it will work correctly, just not optimally until reindexed
    op.execute(
        "CREATE INDEX ix_tools_embedding ON tools "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )

    # Create tool_rag_config table (singleton for configuration)
    op.create_table(
        "tool_rag_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "capability_manifest",
            sa.Text(),
            nullable=False,
            server_default="",
            comment="Brief description of available tool categories for search_tools meta-tool",
        ),
        sa.Column(
            "tools_hash",
            sa.String(64),
            nullable=False,
            server_default="",
            comment="SHA-256 hash of tool descriptions, used to detect when manifest needs update",
        ),
        sa.Column(
            "default_threshold",
            sa.Float(),
            nullable=False,
            server_default="0.5",
            comment="Default similarity threshold for tool search (0.0-1.0)",
        ),
        sa.Column(
            "default_max_results",
            sa.Integer(),
            nullable=False,
            server_default="5",
            comment="Default maximum number of tools to return from search",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )

    # Insert singleton row with defaults
    op.execute(
        "INSERT INTO tool_rag_config (capability_manifest, tools_hash) VALUES ('', '')"
    )


def downgrade() -> None:
    op.drop_table("tool_rag_config")
    op.drop_index("ix_tools_embedding", table_name="tools")
    op.drop_column("tools", "embedding")
    op.execute("DROP EXTENSION IF EXISTS vector")

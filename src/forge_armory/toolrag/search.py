"""Search service for Tool RAG.

Provides semantic search for tools using pgvector cosine similarity.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select, text

from forge_armory.db.models import Tool
from forge_armory.settings import settings
from forge_armory.toolrag.embedding import embedding_service

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Result from a tool search."""

    tools: list[dict]  # Full tool definitions in MCP format
    query: str
    total_matches: int


async def search_tools(
    session: AsyncSession,
    query: str,
    threshold: float | None = None,
) -> list[Tool]:
    """Search for tools matching a query using semantic similarity.

    Uses pgvector cosine distance to find tools with descriptions
    semantically similar to the query. Returns ALL tools that meet
    the similarity threshold.

    Args:
        session: Database session
        query: Natural language query describing what tool is needed
        threshold: Minimum similarity score (0-1). Default from settings.

    Returns:
        List of matching Tool objects, ordered by relevance (most similar first)
    """
    if not query or not query.strip():
        return []

    # Use default threshold from settings if not provided
    if threshold is None:
        threshold = settings.toolrag_default_threshold

    # Compute query embedding
    query_embedding = embedding_service.embed(query)

    # pgvector uses cosine distance (1 - similarity)
    # We want tools where similarity >= threshold
    # So distance <= (1 - threshold)
    max_distance = 1 - threshold

    # Query using pgvector cosine distance operator (<=>)
    # The operator returns distance, not similarity
    # Returns ALL tools meeting the threshold, ordered by relevance
    stmt = (
        select(Tool)
        .where(Tool.embedding.isnot(None))
        .where(
            text("tools.embedding <=> :query_embedding <= :max_distance")
        )
        .order_by(text("tools.embedding <=> :query_embedding"))
    )

    result = await session.execute(
        stmt,
        {
            "query_embedding": str(query_embedding),
            "max_distance": max_distance,
        },
    )

    tools = list(result.scalars().all())
    logger.debug(
        "Tool search: query=%r threshold=%.2f found=%d",
        query[:50],
        threshold,
        len(tools),
    )

    return tools


def format_tool_for_mcp(tool: Tool) -> dict:
    """Format a Tool object for MCP protocol response.

    Args:
        tool: Tool object from database

    Returns:
        Dict in MCP tool format
    """
    return {
        "name": tool.prefixed_name,
        "description": tool.description or "",
        "inputSchema": tool.input_schema,
    }


def format_search_results(
    tools: list[Tool],
    query: str,
) -> SearchResult:
    """Format search results for response.

    Args:
        tools: List of Tool objects from search
        query: Original search query

    Returns:
        SearchResult with formatted tool definitions
    """
    return SearchResult(
        tools=[format_tool_for_mcp(tool) for tool in tools],
        query=query,
        total_matches=len(tools),
    )


def format_search_response(result: SearchResult) -> dict:
    """Format SearchResult for JSON response.

    This is what gets returned from the search_tools meta-tool.

    Args:
        result: SearchResult from format_search_results

    Returns:
        Dict suitable for JSON serialization
    """
    return {
        "tools": result.tools,
        "query": result.query,
        "total_matches": result.total_matches,
        "instruction": (
            "You can now call any of these tools directly using their name. "
            "If none of these tools match your needs, try a different search query."
        ),
    }


async def get_embedding_stats(session: AsyncSession) -> dict:
    """Get statistics about tool embeddings.

    Args:
        session: Database session

    Returns:
        Dict with embedding statistics
    """
    from sqlalchemy import func

    # Count total tools
    total_stmt = select(func.count(Tool.id))
    total_result = await session.execute(total_stmt)
    total = total_result.scalar() or 0

    # Count tools with embeddings
    embedded_stmt = select(func.count(Tool.id)).where(Tool.embedding.isnot(None))
    embedded_result = await session.execute(embedded_stmt)
    embedded = embedded_result.scalar() or 0

    return {
        "total_tools": total,
        "tools_with_embeddings": embedded,
        "tools_without_embeddings": total - embedded,
        "embedding_coverage": embedded / total if total > 0 else 0.0,
    }

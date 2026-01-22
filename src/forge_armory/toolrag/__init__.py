"""Tool RAG module for semantic tool search."""

from forge_armory.toolrag.embedding import (
    EmbeddingService,
    create_embedding_text,
    embedding_service,
)
from forge_armory.toolrag.manifest import (
    DEFAULT_TEMPLATE,
    TOOL_LIST_PLACEHOLDER,
    generate_tool_list,
    get_default_template,
    render_manifest,
)
from forge_armory.toolrag.search import (
    SearchResult,
    format_search_response,
    format_search_results,
    format_tool_for_mcp,
    get_embedding_stats,
    search_tools,
)

__all__ = [
    # Embedding
    "EmbeddingService",
    "create_embedding_text",
    "embedding_service",
    # Manifest
    "DEFAULT_TEMPLATE",
    "TOOL_LIST_PLACEHOLDER",
    "generate_tool_list",
    "get_default_template",
    "render_manifest",
    # Search
    "SearchResult",
    "format_search_response",
    "format_search_results",
    "format_tool_for_mcp",
    "get_embedding_stats",
    "search_tools",
]

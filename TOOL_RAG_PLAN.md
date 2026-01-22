# Tool RAG Implementation Plan

> **Status:** Phases 1-5 Complete (Armory + Orchestrator done), Phase 6 Pending (Testing & Docs)
> **Last Updated:** 2026-01-22
> **Related:** [blueprint/docs/TOOL_RAG.md](../blueprint/docs/TOOL_RAG.md)
>
> **Note:** Tool RAG returns ALL tools matching the similarity threshold. There is no max_results limit.

## Overview

### Goal

Implement Tool RAG (Retrieval-Augmented Generation for tools) in Armory to reduce context usage when many tools are available. Instead of sending all tool definitions to the LLM, we expose a single `search_tools` meta-tool that retrieves relevant tools on demand.

### Approach: Search and Load

We implement the "Search and Load" pattern:

1. In RAG mode, `tools/list` returns only `search_tools` (with capability manifest in description)
2. LLM calls `search_tools(query)` to find relevant tools
3. `search_tools` returns full tool definitions for matching tools
4. LLM can then call those tools directly (Armory accepts any registered tool)

### Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Embedding model | Local (sentence-transformers) | Avoid API latency during tool calls |
| Vector store | pgvector | Already using PostgreSQL, minimal new infrastructure |
| Query strategy | Raw user message | Avoid LLM calls in retrieval path |
| Filtering | Threshold-based | Return only relevant tools, not fixed top-k |
| Mode switching | Query parameter (`?mode=rag`) | Avoids path conflicts with `/mcp/{prefix}` |
| Manifest generation | Manual via Admin UI | No LLM integration needed in Armory |
| What to embed | Description only | Sufficient for retrieval; full definition returned after match |

---

## Architecture

### Component Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                              Armory                                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐     │
│  │                     MCP Endpoints                           │     │
│  │                                                             │     │
│  │  POST /mcp              → Normal mode (all tools)          │     │
│  │  POST /mcp?mode=rag     → RAG mode (search_tools only)     │     │
│  │  POST /mcp/{prefix}     → Direct backend (unchanged)       │     │
│  │                                                             │     │
│  └──────────────────────────┬─────────────────────────────────┘     │
│                              │                                       │
│            ┌─────────────────┴─────────────────┐                    │
│            │                                   │                    │
│            ▼                                   ▼                    │
│  ┌──────────────────────┐         ┌──────────────────────┐         │
│  │   Backend Manager    │         │   Tool RAG Service   │         │
│  │   (existing)         │         │   (new)              │         │
│  │                      │         │                      │         │
│  │  - Route tool calls  │         │  - search_tools      │         │
│  │  - Backend connections│        │  - Embedding service │         │
│  │  - Metrics recording │         │  - Semantic search   │         │
│  └──────────────────────┘         └──────────┬───────────┘         │
│                                               │                     │
│  ┌────────────────────────────────────────────┴──────────────────┐ │
│  │                      PostgreSQL + pgvector                     │ │
│  │                                                                │ │
│  │  Tool table                    ToolRAGConfig table             │ │
│  │  ┌─────────────────────┐      ┌─────────────────────┐         │ │
│  │  │ - name              │      │ - capability_manifest│         │ │
│  │  │ - description       │      │ - tools_hash         │         │ │
│  │  │ - input_schema      │      │ - updated_at         │         │ │
│  │  │ - embedding (vector)│      └─────────────────────┘         │ │
│  │  └─────────────────────┘                                       │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                     Embedding Service                          │ │
│  │                                                                │ │
│  │  - sentence-transformers/all-MiniLM-L6-v2                     │ │
│  │  - Loaded on-demand (first search request)                    │ │
│  │  - Embeddings computed on tool registration/refresh           │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Data Flow: RAG Mode

```
Client                          Armory                         Database
  │                               │                               │
  │ POST /mcp?mode=rag            │                               │
  │ {"method": "tools/list"}      │                               │
  │──────────────────────────────►│                               │
  │                               │  Get capability manifest      │
  │                               │──────────────────────────────►│
  │                               │◄──────────────────────────────│
  │ [search_tools with manifest]  │                               │
  │◄──────────────────────────────│                               │
  │                               │                               │
  │ POST /mcp?mode=rag            │                               │
  │ {"method": "tools/call",      │                               │
  │  "params": {                  │                               │
  │    "name": "search_tools",    │                               │
  │    "arguments": {             │                               │
  │      "query": "weather"       │                               │
  │    }}}                        │                               │
  │──────────────────────────────►│                               │
  │                               │  1. Embed query               │
  │                               │  2. Vector similarity search  │
  │                               │──────────────────────────────►│
  │                               │◄──────────────────────────────│
  │                               │  3. Filter by threshold       │
  │ [matching tool definitions]   │                               │
  │◄──────────────────────────────│                               │
  │                               │                               │
  │ POST /mcp?mode=rag            │                               │
  │ {"method": "tools/call",      │                               │
  │  "params": {                  │                               │
  │    "name": "weather__forecast"│                               │
  │    ...}}                      │                               │
  │──────────────────────────────►│                               │
  │                               │  Route to backend (normal)    │
  │                               │──────────────────────────────►│
  │ [tool result]                 │                               │
  │◄──────────────────────────────│                               │
```

---

## Database Changes

### 1. Enable pgvector Extension

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### 2. Add Embedding Column to Tool Table

```sql
ALTER TABLE tools ADD COLUMN embedding vector(384);
CREATE INDEX tools_embedding_idx ON tools USING ivfflat (embedding vector_cosine_ops);
```

**Notes:**
- 384 dimensions matches `all-MiniLM-L6-v2` output
- `ivfflat` index for approximate nearest neighbor search
- `vector_cosine_ops` for cosine similarity

### 3. New ToolRAGConfig Table

```sql
CREATE TABLE tool_rag_config (
    id SERIAL PRIMARY KEY,
    capability_manifest TEXT,
    tools_hash VARCHAR(64),  -- SHA-256 of tool descriptions
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Single row table (config singleton)
INSERT INTO tool_rag_config (capability_manifest, tools_hash)
VALUES ('', '');
```

### 4. SQLAlchemy Models

```python
# In db/models.py

from pgvector.sqlalchemy import Vector

class Tool(Base):
    __tablename__ = "tools"

    # ... existing columns ...

    # New column for Tool RAG
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(384), nullable=True
    )


class ToolRAGConfig(Base):
    """Singleton table for Tool RAG configuration."""
    __tablename__ = "tool_rag_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    capability_manifest: Mapped[str] = mapped_column(Text, default="")
    tools_hash: Mapped[str] = mapped_column(String(64), default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now()
    )
```

### 5. Alembic Migration

Create migration file: `alembic/versions/xxx_add_tool_rag.py`

```python
"""Add Tool RAG support

Revision ID: xxx
"""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

def upgrade():
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Add embedding column to tools
    op.add_column(
        "tools",
        sa.Column("embedding", Vector(384), nullable=True)
    )

    # Create index for vector similarity search
    op.execute(
        "CREATE INDEX tools_embedding_idx ON tools "
        "USING ivfflat (embedding vector_cosine_ops)"
    )

    # Create tool_rag_config table
    op.create_table(
        "tool_rag_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("capability_manifest", sa.Text(), default=""),
        sa.Column("tools_hash", sa.String(64), default=""),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )

    # Insert singleton row
    op.execute(
        "INSERT INTO tool_rag_config (capability_manifest, tools_hash) "
        "VALUES ('', '')"
    )


def downgrade():
    op.drop_table("tool_rag_config")
    op.drop_index("tools_embedding_idx")
    op.drop_column("tools", "embedding")
    op.execute("DROP EXTENSION IF EXISTS vector")
```

---

## Embedding Service

### Model Choice

**Model:** `sentence-transformers/all-MiniLM-L6-v2`

| Property | Value |
|----------|-------|
| Dimensions | 384 |
| Size | ~80MB |
| Speed | ~14,000 sentences/sec on CPU |
| Quality | Good for semantic similarity |
| License | Apache 2.0 |

### Implementation

```python
# src/forge_armory/toolrag/embedding.py

from __future__ import annotations

import logging
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Service for computing text embeddings.

    Loads the model on-demand to avoid startup cost when Tool RAG
    is not being used.
    """

    MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
    DIMENSIONS = 384

    def __init__(self) -> None:
        self._model: SentenceTransformer | None = None

    @property
    def model(self) -> SentenceTransformer:
        """Lazy-load the embedding model."""
        if self._model is None:
            logger.info("Loading embedding model: %s", self.MODEL_NAME)
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.MODEL_NAME)
            logger.info("Embedding model loaded")
        return self._model

    def embed(self, text: str) -> list[float]:
        """Compute embedding for a single text."""
        embedding = self.model.encode(text, convert_to_numpy=True)
        return embedding.tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Compute embeddings for multiple texts efficiently."""
        embeddings = self.model.encode(texts, convert_to_numpy=True)
        return embeddings.tolist()

    def is_loaded(self) -> bool:
        """Check if the model is loaded."""
        return self._model is not None


# Singleton instance
embedding_service = EmbeddingService()
```

### When to Compute Embeddings

Embeddings are computed when:
1. A backend's tools are refreshed (`POST /api/backends/{name}/refresh`)
2. Admin triggers "Regenerate Embeddings" in UI
3. New backend is added and connected

```python
# In repository.py or a new toolrag/service.py

async def update_tool_embeddings(
    session: AsyncSession,
    backend_id: int | None = None
) -> int:
    """Compute and store embeddings for tools.

    Args:
        session: Database session
        backend_id: If provided, only update tools for this backend

    Returns:
        Number of tools updated
    """
    tool_repo = ToolRepository(session)

    if backend_id:
        tools = await tool_repo.list_by_backend(backend_id)
    else:
        tools = await tool_repo.list_all()

    # Prepare texts for batch embedding
    texts = [tool.description or tool.name for tool in tools]

    # Compute embeddings in batch
    embeddings = embedding_service.embed_batch(texts)

    # Update tools with embeddings
    for tool, embedding in zip(tools, embeddings):
        tool.embedding = embedding

    await session.commit()

    return len(tools)
```

---

## Search Implementation

### Semantic Search Query

```python
# src/forge_armory/toolrag/search.py

from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from forge_armory.db.models import Tool
from forge_armory.toolrag.embedding import embedding_service


async def search_tools(
    session: AsyncSession,
    query: str,
    threshold: float = 0.5,
) -> list[Tool]:
    """Search for tools matching a query using semantic similarity.

    Returns ALL tools meeting the threshold, ordered by relevance.

    Args:
        session: Database session
        query: Natural language query
        threshold: Minimum cosine similarity (0-1). Default 0.5

    Returns:
        List of matching Tool objects, ordered by relevance
    """
    # Compute query embedding
    query_embedding = embedding_service.embed(query)

    # pgvector cosine distance: 1 - cosine_similarity
    # So we want distance < (1 - threshold)
    max_distance = 1 - threshold

    # Query with vector similarity
    # Using raw SQL for pgvector operators
    # Returns ALL tools meeting threshold
    stmt = (
        select(Tool)
        .where(Tool.embedding.isnot(None))
        .where(
            text("embedding <=> :query_embedding < :max_distance")
        )
        .order_by(text("embedding <=> :query_embedding"))
    )

    result = await session.execute(
        stmt,
        {
            "query_embedding": str(query_embedding),
            "max_distance": max_distance,
        }
    )

    return list(result.scalars().all())
```

### Alternative: Using pgvector SQLAlchemy Integration

```python
from pgvector.sqlalchemy import Vector

async def search_tools_v2(
    session: AsyncSession,
    query: str,
    threshold: float = 0.5,
) -> list[Tool]:
    """Search using pgvector's SQLAlchemy operators.

    Returns ALL tools meeting the threshold.
    """
    query_embedding = embedding_service.embed(query)

    # pgvector provides cosine_distance method
    stmt = (
        select(Tool)
        .where(Tool.embedding.isnot(None))
        .where(Tool.embedding.cosine_distance(query_embedding) < (1 - threshold))
        .order_by(Tool.embedding.cosine_distance(query_embedding))
    )

    result = await session.execute(stmt)
    return list(result.scalars().all())
```

### Search Results Format

```python
@dataclass
class SearchResult:
    """Result from tool search."""
    tools: list[dict]  # Full tool definitions
    query: str
    total_matches: int


def format_search_results(
    tools: list[Tool],
    query: str,
) -> dict:
    """Format search results for MCP response."""
    return {
        "tools": [
            {
                "name": tool.prefixed_name,
                "description": tool.description or "",
                "inputSchema": tool.input_schema,
            }
            for tool in tools
        ],
        "query": query,
        "total_matches": len(tools),
        "instruction": "You can now call any of these tools directly using their name.",
    }
```

---

## MCP Protocol Changes

### Mode Detection

```python
# In server.py

from urllib.parse import parse_qs

def get_mcp_mode(request: Request) -> str:
    """Extract MCP mode from query parameters.

    Returns:
        'rag' for Tool RAG mode, 'normal' otherwise
    """
    mode = request.query_params.get("mode", "normal")
    return mode if mode in ("rag", "normal") else "normal"
```

### Modified tools/list Handler

```python
async def _handle_list_tools(self, mode: str) -> dict[str, Any]:
    """List tools based on mode."""
    if mode == "rag":
        return await self._handle_list_tools_rag()
    else:
        return await self._handle_list_tools_normal()


async def _handle_list_tools_normal(self) -> dict[str, Any]:
    """List all tools (existing behavior)."""
    tools = await self.manager.list_tools()
    return {
        "tools": [
            {
                "name": tool.prefixed_name,
                "description": tool.description or "",
                "inputSchema": tool.input_schema,
            }
            for tool in tools
        ]
    }


async def _handle_list_tools_rag(self) -> dict[str, Any]:
    """List only search_tools meta-tool."""
    # Get capability manifest from config
    async with self.manager._session_maker() as session:
        config = await get_tool_rag_config(session)
        manifest = config.capability_manifest if config else ""

    search_tool = {
        "name": "search_tools",
        "description": self._build_search_tool_description(manifest),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language description of what you need"
                },
                "threshold": {
                    "type": "number",
                    "description": "Minimum relevance score (0-1). Default: 0.5. All tools meeting threshold are returned.",
                    "default": 0.5
                }
            },
            "required": ["query"]
        }
    }

    return {"tools": [search_tool]}


def _build_search_tool_description(self, manifest: str) -> str:
    """Build search_tools description with capability manifest."""
    base = "Search for tools that can help with a specific task."

    if manifest:
        base += f"\n\nAvailable capabilities:\n{manifest}"

    base += (
        "\n\nCall this tool with a natural language description of what you need. "
        "Returns matching tool definitions that you can then call directly. "
        "Only use this if the task requires external tools."
    )

    return base
```

### Modified tools/call Handler

```python
async def _handle_call_tool(
    self, params: dict[str, Any], context: RequestContext, mode: str
) -> dict[str, Any]:
    """Call a tool, handling search_tools specially in RAG mode."""
    tool_name = params.get("name", "")
    arguments = params.get("arguments", {})

    # Handle search_tools meta-tool
    if tool_name == "search_tools":
        return await self._handle_search_tools(arguments)

    # Normal tool call (works in both modes)
    result = await self.manager.call_tool(tool_name, arguments, context)
    return self._format_tool_result(result)


async def _handle_search_tools(self, arguments: dict[str, Any]) -> dict[str, Any]:
    """Handle the search_tools meta-tool.

    Returns all tools meeting the similarity threshold.
    """
    query = arguments.get("query", "")
    threshold = arguments.get("threshold", 0.5)

    if not query:
        return {
            "content": [{
                "type": "text",
                "text": "Error: 'query' parameter is required"
            }]
        }

    async with self.manager._session_maker() as session:
        tools = await search_tools(session, query, threshold)

    result = format_search_results(tools, query)

    return {
        "content": [{
            "type": "text",
            "text": json.dumps(result, indent=2)
        }]
    }
```

---

## Admin UI Changes

### New Settings Page: Tool RAG

**Route:** `/ui/settings/tool-rag`

#### Components

1. **Capability Manifest Section**
   - Text area showing current manifest
   - "Generate Prompt" button → copies prompt to clipboard
   - "Save Manifest" button → saves edited manifest
   - Last updated timestamp

2. **Embeddings Section**
   - Status: "X tools have embeddings" / "Y tools missing embeddings"
   - "Regenerate All Embeddings" button
   - Progress indicator during regeneration

3. **Configuration Section**
   - Default threshold slider (0.0 - 1.0)
   - All tools matching threshold are returned

#### Generate Prompt Function

```typescript
function generateManifestPrompt(tools: Tool[]): string {
  const toolList = tools
    .map(t => `- ${t.prefixed_name}: ${t.description}`)
    .join('\n');

  return `Summarize these tools into a brief capability manifest for an AI assistant.
Group by category. Keep it under 100 words. Format as a brief list.

Tools:
${toolList}

Output format:
- Category: Brief description of what tools in this category can do`;
}
```

### Admin API Endpoints

```python
# In admin/routes.py

@router.get("/tool-rag/config", response_model=ToolRAGConfigResponse)
async def get_tool_rag_config():
    """Get Tool RAG configuration."""
    ...

@router.put("/tool-rag/config", response_model=ToolRAGConfigResponse)
async def update_tool_rag_config(config: ToolRAGConfigUpdate):
    """Update Tool RAG configuration (manifest, etc.)."""
    ...

@router.post("/tool-rag/embeddings/regenerate")
async def regenerate_embeddings(backend_name: str | None = None):
    """Regenerate embeddings for all tools or specific backend."""
    ...

@router.get("/tool-rag/status", response_model=ToolRAGStatusResponse)
async def get_tool_rag_status():
    """Get Tool RAG status (embedding counts, etc.)."""
    ...

@router.get("/tool-rag/prompt")
async def get_manifest_prompt():
    """Get the prompt text for generating capability manifest."""
    ...
```

---

## Testing Strategy

### Unit Tests

```python
# tests/test_toolrag.py

class TestEmbeddingService:
    """Tests for embedding service."""

    def test_embed_single_text(self):
        """Embedding returns correct dimensions."""
        embedding = embedding_service.embed("test query")
        assert len(embedding) == 384

    def test_embed_batch(self):
        """Batch embedding is efficient."""
        texts = ["query 1", "query 2", "query 3"]
        embeddings = embedding_service.embed_batch(texts)
        assert len(embeddings) == 3
        assert all(len(e) == 384 for e in embeddings)

    def test_lazy_loading(self):
        """Model loads on first use."""
        service = EmbeddingService()
        assert not service.is_loaded()
        service.embed("test")
        assert service.is_loaded()


class TestToolSearch:
    """Tests for semantic search."""

    async def test_search_returns_relevant_tools(self, session):
        """Search returns tools matching query."""
        # Setup: Create tools with embeddings
        ...

        results = await search_tools(session, "weather forecast")
        assert len(results) > 0
        assert any("weather" in t.name for t in results)

    async def test_threshold_filtering(self, session):
        """Low similarity tools are filtered out."""
        results = await search_tools(session, "weather", threshold=0.9)
        # High threshold should return fewer results
        ...

    async def test_empty_query(self, session):
        """Empty query returns no results."""
        results = await search_tools(session, "")
        assert len(results) == 0


class TestMCPRagMode:
    """Tests for MCP RAG mode."""

    async def test_tools_list_rag_mode(self, client):
        """RAG mode returns only search_tools."""
        response = await client.post(
            "/mcp?mode=rag",
            json={"jsonrpc": "2.0", "method": "tools/list", "id": 1}
        )
        data = response.json()
        tools = data["result"]["tools"]
        assert len(tools) == 1
        assert tools[0]["name"] == "search_tools"

    async def test_tools_list_normal_mode(self, client):
        """Normal mode returns all tools."""
        response = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "method": "tools/list", "id": 1}
        )
        data = response.json()
        tools = data["result"]["tools"]
        assert len(tools) > 1  # All registered tools

    async def test_search_tools_call(self, client):
        """search_tools returns matching tools."""
        response = await client.post(
            "/mcp?mode=rag",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "search_tools",
                    "arguments": {"query": "weather"}
                },
                "id": 1
            }
        )
        data = response.json()
        # Parse result content
        ...
```

### Integration Tests

```python
class TestToolRAGIntegration:
    """End-to-end Tool RAG tests."""

    async def test_full_rag_flow(self, client):
        """Test complete RAG flow: list → search → call."""
        # 1. Get tools in RAG mode
        response = await client.post("/mcp?mode=rag", ...)
        assert "search_tools" in [t["name"] for t in response["tools"]]

        # 2. Search for weather tools
        response = await client.post("/mcp?mode=rag",
            json={...search_tools("weather")...})
        tools = parse_search_results(response)
        assert any("weather" in t["name"] for t in tools)

        # 3. Call a discovered tool
        weather_tool = next(t for t in tools if "weather" in t["name"])
        response = await client.post("/mcp?mode=rag",
            json={...call_tool(weather_tool["name"], {...})...})
        assert response["result"] is not None
```

### Accuracy Benchmarks

Create a benchmark suite to measure retrieval quality:

```python
# tests/benchmarks/test_retrieval_accuracy.py

BENCHMARK_QUERIES = [
    {
        "query": "What's the weather like?",
        "expected_tools": ["weather__get_forecast", "weather__get_current"],
    },
    {
        "query": "Search the internet for news",
        "expected_tools": ["search__web_search"],
    },
    # ... more test cases
]

async def test_retrieval_recall():
    """Measure recall - how often expected tools appear in results."""
    hits = 0
    total = 0

    for case in BENCHMARK_QUERIES:
        # Returns all tools meeting threshold
        results = await search_tools(session, case["query"])
        result_names = [t.prefixed_name for t in results]

        for expected in case["expected_tools"]:
            total += 1
            if expected in result_names:
                hits += 1

    recall = hits / total
    print(f"Recall: {recall:.2%}")
    assert recall >= 0.7  # Minimum acceptable recall
```

---

## Implementation Phases

### Phase 1: Database + Embeddings (Foundation) - COMPLETE

**Goal:** Add vector storage capability and embedding computation

**Completed:**
- [x] Added `pgvector` and `sentence-transformers` to dependencies
- [x] Created Alembic migration (`20260120_1000_002_add_tool_rag.py`):
  - pgvector extension
  - embedding column on tools table (vector(384))
  - tool_rag_config table with default_threshold
- [x] Implemented `EmbeddingService` class with lazy loading
- [x] Added embedding computation to tool refresh flow in repository
- [x] Unit tests for embedding service (21 tests)

**Files:**
- `alembic/versions/20260120_1000_002_add_tool_rag.py`
- `src/forge_armory/toolrag/embedding.py`
- `src/forge_armory/db/models.py` (Tool.embedding, ToolRAGConfig)
- `src/forge_armory/db/repository.py` (_compute_embeddings)
- `tests/test_toolrag.py`

### Phase 2: Search Service - COMPLETE

**Goal:** Implement semantic search functionality

**Completed:**
- [x] Implemented `search_tools()` function with pgvector cosine similarity
- [x] Threshold-based filtering (configurable, default 0.5)
- [x] Search result formatting for MCP responses
- [x] Repository methods for ToolRAGConfig CRUD
- [x] Unit tests for search formatting

**Files:**
- `src/forge_armory/toolrag/search.py`
- `src/forge_armory/db/repository.py` (ToolRAGConfigRepository)

### Phase 3: MCP Integration - COMPLETE

**Goal:** Expose Tool RAG via MCP protocol

**Completed:**
- [x] Added `MCPMode` enum and `get_mcp_mode()` function
- [x] Implemented RAG mode `tools/list` handler (returns only search_tools)
- [x] Implemented `search_tools` meta-tool handler
- [x] Normal tool calls work in RAG mode
- [x] Integration tests (6 tests for RAG mode)

**Files:**
- `src/forge_armory/server.py` (MCPMode, _handle_list_tools_rag, _handle_search_tools)
- `tests/test_integration.py` (TestToolRAGMode)

### Phase 4: Admin UI - COMPLETE

**Goal:** Management interface for Tool RAG

**Completed:**
- [x] Tool RAG settings page at `/ui/settings/tool-rag`
- [x] Capability manifest **template** editor with `{{TOOL_LIST}}` placeholder
- [x] Preview section showing rendered manifest (what LLMs see)
- [x] Embedding status display (model, indexed/total, percentage)
- [x] Regenerate embeddings action with confirmation
- [x] Configurable threshold default (all tools meeting threshold are returned)
- [x] Admin API endpoints:
  - GET/PUT `/admin/tool-rag/config`
  - GET `/admin/tool-rag/status`
  - GET `/admin/tool-rag/preview`
  - POST `/admin/tool-rag/regenerate`

**Files:**
- `admin-ui/src/views/ToolRagSettingsView.vue`
- `admin-ui/src/api/client.ts` (Tool RAG methods)
- `admin-ui/src/types/index.ts` (ToolRag* types)
- `admin-ui/src/router/index.ts`, `Sidebar.vue`, `Header.vue`
- `src/forge_armory/admin/routes.py` (Tool RAG routes)
- `src/forge_armory/admin/schemas.py` (ToolRag* schemas)
- `src/forge_armory/toolrag/manifest.py` (template rendering)

### Phase 5: Orchestrator Integration - COMPLETE

**Goal:** Integrate Tool RAG with forge-orchestrator

**Design:** Stateless per-request approach - no server-side configuration. Each request specifies whether to use RAG mode.

**Completed:**
- [x] Added `_get_armory_url()` helper to construct URL with `?mode=rag` parameter
- [x] Modified `run_stream()` to use RAG mode URL when `use_tool_rag_mode=true`
- [x] Added `TOOL_RAG_INSTRUCTIONS` system prompt for RAG mode behavior
- [x] Added `use_tool_rag_mode` parameter to `/chat/stream` API endpoint
- [x] Updated forge-ui with Tool RAG toggle in ChatInput component (Advanced view)

**Files modified:**
- `forge-orchestrator/src/forge_orchestrator/orchestrator.py` - `_get_armory_url()`, RAG instructions, request handling
- `forge-orchestrator/src/forge_orchestrator/server.py` - API parameter `use_tool_rag_mode: bool | None`
- `forge-ui/src/types/conversation.ts` - Added `useToolRag` to AdvancedViewSettings
- `forge-ui/src/composables/useConversation.ts` - Default value, API request body
- `forge-ui/src/components/ChatInput.vue` - RAG toggle button with blue accent

### Phase 6: Testing & Documentation - PENDING

**Goal:** Production readiness

**Planned Tasks:**
1. Add accuracy benchmarks
2. Performance testing (search latency)
3. Update API documentation
4. Update README with Tool RAG usage
5. Add example configurations

**Deliverables:**
- Benchmark suite
- Documentation complete
- Ready for production use

---

## Dependencies

### New Python Packages

```toml
# In pyproject.toml

[project.dependencies]
# ... existing ...
pgvector = ">=0.3.0"
sentence-transformers = ">=3.0.0"
```

### System Requirements

- PostgreSQL 15+ with pgvector extension
- ~100MB additional memory for embedding model (when loaded)

---

## Configuration

### Environment Variables

```bash
# Tool RAG settings (all optional, have defaults)
ARMORY_TOOLRAG_ENABLED=true              # Enable Tool RAG mode support
ARMORY_TOOLRAG_DEFAULT_THRESHOLD=0.5     # Default similarity threshold
ARMORY_TOOLRAG_DEFAULT_MAX_RESULTS=5     # Default max results
ARMORY_TOOLRAG_EMBEDDING_MODEL=all-MiniLM-L6-v2  # Embedding model name
```

### Settings Class

```python
# In settings.py

class Settings(BaseSettings):
    # ... existing ...

    # Tool RAG settings
    toolrag_enabled: bool = True
    toolrag_default_threshold: float = 0.5
    toolrag_embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
```

---

## Open Questions / Future Work

### For Later Consideration

1. **Hybrid search**: Combine semantic + keyword (BM25) search
   - Research shows mixed results; semantic alone may be sufficient

2. **Query expansion**: Use synonyms or LLM to expand query
   - Adds latency; evaluate if accuracy gains justify it

3. **Tool categories**: Pre-filter by category before semantic search
   - Useful for very large tool registries (1000+)

4. **Embedding versioning**: Handle embedding model upgrades
   - Store model version with embeddings
   - Trigger re-embedding on model change

5. **Caching**: Cache query embeddings for repeated searches
   - Low priority; embedding is fast (~5ms)

6. **Analytics**: Track search quality metrics
   - Which queries return no results?
   - Which tools are never found?

7. **Automated manifest generation**:
   - Integrate LLM API for one-click manifest generation
   - Currently manual to keep Armory LLM-free

---

## References

- [blueprint/docs/TOOL_RAG.md](../blueprint/docs/TOOL_RAG.md) - Original design document
- [arxiv.org/html/2509.20386](https://arxiv.org/html/2509.20386) - Dynamic ReAct paper
- [pgvector documentation](https://github.com/pgvector/pgvector)
- [sentence-transformers](https://www.sbert.net/)

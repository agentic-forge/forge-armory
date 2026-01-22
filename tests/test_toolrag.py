"""Tests for Tool RAG embedding and search services."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from forge_armory.toolrag.embedding import (
    EmbeddingService,
    create_embedding_text,
)
from forge_armory.toolrag.search import (
    SearchResult,
    format_search_response,
    format_search_results,
    format_tool_for_mcp,
)


class TestEmbeddingService:
    """Tests for EmbeddingService."""

    @pytest.fixture
    def service(self) -> EmbeddingService:
        """Create a fresh embedding service for each test."""
        return EmbeddingService()

    def test_dimensions_matches_model(self, service: EmbeddingService) -> None:
        """Service reports correct dimensions for the model."""
        # Default model is all-MiniLM-L6-v2 with 384 dimensions
        assert service.dimensions == 384

    def test_is_not_loaded_initially(self, service: EmbeddingService) -> None:
        """Model is not loaded until first use."""
        assert service.is_loaded() is False

    def test_embed_single_text(self, service: EmbeddingService) -> None:
        """Embedding a single text returns correct dimensions."""
        embedding = service.embed("weather forecast")

        assert isinstance(embedding, list)
        assert len(embedding) == 384
        assert all(isinstance(x, float) for x in embedding)

    def test_embed_loads_model(self, service: EmbeddingService) -> None:
        """Embedding a text loads the model."""
        assert service.is_loaded() is False
        service.embed("test")
        assert service.is_loaded() is True

    def test_embed_empty_string(self, service: EmbeddingService) -> None:
        """Embedding empty string returns zero vector."""
        embedding = service.embed("")

        assert len(embedding) == 384
        assert all(x == 0.0 for x in embedding)

    def test_embed_batch(self, service: EmbeddingService) -> None:
        """Batch embedding returns correct number of embeddings."""
        texts = ["weather forecast", "hotel booking", "flight search"]
        embeddings = service.embed_batch(texts)

        assert len(embeddings) == 3
        assert all(len(e) == 384 for e in embeddings)

    def test_embed_batch_empty_list(self, service: EmbeddingService) -> None:
        """Batch embedding empty list returns empty list."""
        embeddings = service.embed_batch([])
        assert embeddings == []

    def test_embed_batch_with_empty_strings(self, service: EmbeddingService) -> None:
        """Batch embedding handles empty strings in the batch."""
        texts = ["weather", "", "hotel"]
        embeddings = service.embed_batch(texts)

        assert len(embeddings) == 3
        # First and third should have non-zero embeddings
        assert any(x != 0.0 for x in embeddings[0])
        assert any(x != 0.0 for x in embeddings[2])
        # Second (empty string) should be zero vector
        assert all(x == 0.0 for x in embeddings[1])

    def test_similar_texts_have_similar_embeddings(self, service: EmbeddingService) -> None:
        """Semantically similar texts produce similar embeddings."""
        emb1 = service.embed("get weather forecast")
        emb2 = service.embed("check weather conditions")
        emb3 = service.embed("book a hotel room")

        # Calculate cosine similarity (dot product of normalized vectors)
        def cosine_similarity(a: list[float], b: list[float]) -> float:
            dot = sum(x * y for x, y in zip(a, b, strict=True))
            norm_a = sum(x * x for x in a) ** 0.5
            norm_b = sum(x * x for x in b) ** 0.5
            return dot / (norm_a * norm_b)

        # Weather texts should be more similar to each other
        weather_sim = cosine_similarity(emb1, emb2)
        cross_sim = cosine_similarity(emb1, emb3)

        assert weather_sim > cross_sim

    def test_unload_frees_model(self, service: EmbeddingService) -> None:
        """Unloading the model frees memory."""
        service.embed("test")
        assert service.is_loaded() is True

        service.unload()
        assert service.is_loaded() is False


class TestCreateEmbeddingText:
    """Tests for create_embedding_text helper."""

    def test_name_only(self) -> None:
        """Creates text with just the name."""
        text = create_embedding_text("get_weather", None)
        assert text == "get_weather"

    def test_name_and_description(self) -> None:
        """Creates text with name and description."""
        text = create_embedding_text(
            "get_weather",
            "Get current weather for a location",
        )
        assert "get_weather" in text
        assert "Get current weather for a location" in text

    def test_with_input_schema(self) -> None:
        """Creates text including parameter names from schema."""
        text = create_embedding_text(
            "get_weather",
            "Get weather",
            input_schema={
                "type": "object",
                "properties": {
                    "location": {"type": "string"},
                    "units": {"type": "string"},
                },
            },
        )
        assert "get_weather" in text
        assert "Get weather" in text
        assert "location" in text
        assert "units" in text

    def test_with_empty_schema(self) -> None:
        """Handles empty input schema."""
        text = create_embedding_text(
            "simple_tool",
            "A simple tool",
            input_schema={"type": "object"},
        )
        assert "simple_tool" in text
        assert "A simple tool" in text

    def test_prefixed_name(self) -> None:
        """Works with prefixed tool names."""
        text = create_embedding_text(
            "weather__get_forecast",
            "Get 5-day weather forecast",
        )
        assert "weather__get_forecast" in text
        assert "Get 5-day weather forecast" in text


class TestFormatToolForMcp:
    """Tests for format_tool_for_mcp helper."""

    def test_formats_complete_tool(self) -> None:
        """Formats a tool with all fields."""

        tool = MagicMock()
        tool.prefixed_name = "weather__get_forecast"
        tool.description = "Get weather forecast"
        tool.input_schema = {
            "type": "object",
            "properties": {"location": {"type": "string"}},
        }

        result = format_tool_for_mcp(tool)

        assert result["name"] == "weather__get_forecast"
        assert result["description"] == "Get weather forecast"
        assert result["inputSchema"] == tool.input_schema

    def test_handles_none_description(self) -> None:
        """Handles tool with no description."""

        tool = MagicMock()
        tool.prefixed_name = "simple_tool"
        tool.description = None
        tool.input_schema = {"type": "object"}

        result = format_tool_for_mcp(tool)

        assert result["name"] == "simple_tool"
        assert result["description"] == ""  # Empty string, not None


class TestFormatSearchResults:
    """Tests for format_search_results helper."""

    def test_formats_multiple_tools(self) -> None:
        """Formats a list of tools into SearchResult."""

        tools = []
        for i in range(3):
            tool = MagicMock()
            tool.prefixed_name = f"tool_{i}"
            tool.description = f"Description {i}"
            tool.input_schema = {"type": "object"}
            tools.append(tool)

        result = format_search_results(tools, "test query")

        assert isinstance(result, SearchResult)
        assert result.query == "test query"
        assert result.total_matches == 3
        assert len(result.tools) == 3
        assert result.tools[0]["name"] == "tool_0"

    def test_formats_empty_list(self) -> None:
        """Handles empty tool list."""
        result = format_search_results([], "no results query")

        assert result.query == "no results query"
        assert result.total_matches == 0
        assert result.tools == []


class TestFormatSearchResponse:
    """Tests for format_search_response helper."""

    def test_formats_for_json(self) -> None:
        """Formats SearchResult for JSON response."""
        search_result = SearchResult(
            tools=[
                {"name": "tool_1", "description": "Desc 1", "inputSchema": {}},
                {"name": "tool_2", "description": "Desc 2", "inputSchema": {}},
            ],
            query="find tools",
            total_matches=2,
        )

        response = format_search_response(search_result)

        assert response["query"] == "find tools"
        assert response["total_matches"] == 2
        assert len(response["tools"]) == 2
        assert "instruction" in response
        assert "call any of these tools" in response["instruction"]

    def test_empty_results_response(self) -> None:
        """Formats empty search results."""
        search_result = SearchResult(
            tools=[],
            query="nothing found",
            total_matches=0,
        )

        response = format_search_response(search_result)

        assert response["total_matches"] == 0
        assert response["tools"] == []
        assert "different search query" in response["instruction"]

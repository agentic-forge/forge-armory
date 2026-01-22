"""Embedding service for Tool RAG.

Provides semantic embeddings for tool descriptions using sentence-transformers.
The model is loaded on-demand to avoid startup cost when Tool RAG is not used.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from forge_armory.settings import settings

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# Embedding dimensions for supported models
MODEL_DIMENSIONS = {
    "sentence-transformers/all-MiniLM-L6-v2": 384,
    "sentence-transformers/all-mpnet-base-v2": 768,
    "BAAI/bge-small-en-v1.5": 384,
    "BAAI/bge-large-en-v1.5": 1024,
}

# Default model and dimensions
DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_DIMENSIONS = 384


class EmbeddingService:
    """Service for computing text embeddings.

    The model is loaded lazily on first use to avoid startup overhead.
    This is important because:
    1. Not all requests use Tool RAG
    2. The model can take 1-2 seconds to load
    3. Model uses ~100MB memory

    Usage:
        # Single text
        embedding = embedding_service.embed("weather forecast")

        # Batch (more efficient for multiple texts)
        embeddings = embedding_service.embed_batch(["weather", "hotel booking"])
    """

    def __init__(self, model_name: str | None = None) -> None:
        """Initialize the embedding service.

        Args:
            model_name: Model to use. Defaults to settings.toolrag_embedding_model
        """
        self._model_name = model_name or settings.toolrag_embedding_model
        self._model: SentenceTransformer | None = None
        self._dimensions = MODEL_DIMENSIONS.get(self._model_name, DEFAULT_DIMENSIONS)

    @property
    def model_name(self) -> str:
        """Get the model name."""
        return self._model_name

    @property
    def dimensions(self) -> int:
        """Get the embedding dimensions for the current model."""
        return self._dimensions

    @property
    def model(self) -> SentenceTransformer:
        """Get the model, loading it if necessary."""
        if self._model is None:
            self._load_model()
        return self._model  # type: ignore[return-value]

    def _load_model(self) -> None:
        """Load the embedding model."""
        logger.info("Loading embedding model: %s", self._model_name)

        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(self._model_name)
        logger.info("Embedding model loaded (dimensions: %d)", self._dimensions)

    def is_loaded(self) -> bool:
        """Check if the model is loaded."""
        return self._model is not None

    def embed(self, text: str) -> list[float]:
        """Compute embedding for a single text.

        Args:
            text: Text to embed

        Returns:
            Embedding vector as list of floats
        """
        if not text:
            # Return zero vector for empty text
            return [0.0] * self._dimensions

        embedding = self.model.encode(text, convert_to_numpy=True)
        return embedding.tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Compute embeddings for multiple texts efficiently.

        This is more efficient than calling embed() multiple times
        because the model can process batches in parallel.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        # Handle empty strings in the batch
        non_empty_indices = [i for i, t in enumerate(texts) if t]
        non_empty_texts = [texts[i] for i in non_empty_indices]

        if not non_empty_texts:
            # All texts were empty
            return [[0.0] * self._dimensions for _ in texts]

        # Compute embeddings for non-empty texts
        embeddings = self.model.encode(non_empty_texts, convert_to_numpy=True)

        # Build result with zero vectors for empty texts
        result: list[list[float]] = [[0.0] * self._dimensions for _ in texts]
        for idx, embedding in zip(non_empty_indices, embeddings, strict=True):
            result[idx] = embedding.tolist()

        return result

    def unload(self) -> None:
        """Unload the model to free memory."""
        if self._model is not None:
            logger.info("Unloading embedding model")
            self._model = None


def create_embedding_text(
    name: str,
    description: str | None,
    input_schema: dict | None = None,
) -> str:
    """Create the text to embed for a tool.

    Combines tool name, description, and optionally parameter names
    to create a rich text representation for embedding.

    Args:
        name: Tool name (e.g., "weather__get_forecast")
        description: Tool description
        input_schema: Tool input schema (JSON Schema)

    Returns:
        Combined text for embedding
    """
    parts = [name]

    if description:
        parts.append(description)

    # Optionally include parameter names for richer context
    if input_schema and "properties" in input_schema:
        param_names = list(input_schema["properties"].keys())
        if param_names:
            parts.append(" ".join(param_names))

    return " ".join(parts)


# Singleton instance
# Use this for most cases; create new instances only for testing
embedding_service = EmbeddingService()

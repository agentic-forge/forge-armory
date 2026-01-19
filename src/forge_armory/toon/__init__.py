"""TOON (Token-Oriented Object Notation) format support.

This module provides conversion between JSON and TOON format for
token-efficient responses to LLM clients.
"""

from forge_armory.toon.transformer import (
    get_size_comparison,
    is_toon_available,
    should_use_toon,
    to_json,
    to_toon,
    transform_result,
)

__all__ = [
    "get_size_comparison",
    "is_toon_available",
    "should_use_toon",
    "to_json",
    "to_toon",
    "transform_result",
]

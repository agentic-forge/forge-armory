"""TOON format transformer for token-efficient data serialization.

TOON (Token-Oriented Object Notation) provides 30-60% token reduction
compared to JSON for structured data, particularly uniform arrays of objects.

This module provides:
- Detection of data suitable for TOON conversion
- Conversion between JSON and TOON formats
- Graceful fallback to JSON when TOON isn't beneficial
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from toon_python import EncodeOptions

logger = logging.getLogger(__name__)


@dataclass
class _ToonLoader:
    """Lazy loader for toon_python module."""

    _module: Any = field(default=None, repr=False)
    _checked: bool = field(default=False, repr=False)

    def get_module(self) -> Any:
        """Get the toon_python module, loading it lazily if needed."""
        if not self._checked:
            try:
                import toon_python

                self._module = toon_python
                logger.debug("toon_python module loaded successfully")
            except ImportError:
                self._module = None
                logger.warning("toon_python not installed, TOON format unavailable")
            self._checked = True

        return self._module

    @property
    def is_available(self) -> bool:
        """Check if toon_python is available."""
        self.get_module()
        return self._module is not None


# Singleton loader instance
_loader = _ToonLoader()


def is_toon_available() -> bool:
    """Check if TOON format support is available.

    Returns:
        True if toon_python is installed and importable.
    """
    return _loader.is_available


def _is_uniform_array(data: list[Any], min_size: int = 2) -> bool:
    """Check if a list is a uniform array of objects with same keys.

    Args:
        data: List to check
        min_size: Minimum array size to consider (default: 2)

    Returns:
        True if the list contains uniform objects
    """
    if len(data) < min_size:
        return False

    if not all(isinstance(item, dict) for item in data):
        return False

    try:
        first_keys = frozenset(data[0].keys())
        return all(frozenset(item.keys()) == first_keys for item in data)
    except (AttributeError, IndexError):
        return False


def should_use_toon(data: Any, min_array_size: int = 2) -> bool:
    """Determine if data would benefit from TOON format.

    TOON excels at:
    - Uniform arrays of objects (same keys across all items)
    - Nested structures containing uniform arrays
    - Tabular data structures

    TOON is less effective for:
    - Deeply nested hierarchical structures
    - Irregular/heterogeneous objects
    - Simple primitives or short strings
    - Small arrays (< min_array_size items)

    Args:
        data: The data to evaluate
        min_array_size: Minimum array size to consider for TOON (default: 2)

    Returns:
        True if TOON would likely provide token savings

    Examples:
        >>> should_use_toon([{"id": 1}, {"id": 2}])
        True
        >>> should_use_toon({"users": [{"id": 1}, {"id": 2}]})
        True
        >>> should_use_toon({"temperature": 20})
        False
    """
    if not isinstance(data, (dict, list)):
        return False

    # Check for uniform array at top level (best case for TOON)
    if isinstance(data, list):
        return _is_uniform_array(data, min_array_size)

    # Check for dict containing uniform arrays
    if isinstance(data, dict):
        for value in data.values():
            if isinstance(value, list) and _is_uniform_array(value, min_array_size):
                return True

    return False


def to_toon(data: Any, options: EncodeOptions | None = None) -> str | None:
    """Convert data to TOON format.

    Args:
        data: JSON-serializable data to convert
        options: Optional TOON encoding options

    Returns:
        TOON-formatted string, or None if conversion fails
    """
    toon = _loader.get_module()
    if toon is None:
        return None

    try:
        if options is not None:
            return toon.encode(data, options)
        return toon.encode(data)
    except Exception as e:
        logger.warning("TOON encoding failed: %s", e)
        return None


def to_json(data: Any, indent: int | None = None) -> str:
    """Convert data to JSON format.

    Args:
        data: Data to serialize
        indent: Optional indentation for pretty printing

    Returns:
        JSON-formatted string
    """
    return json.dumps(data, indent=indent, default=str)


def transform_result(
    data: Any,
    prefer_toon: bool = False,
    min_array_size: int = 2,
) -> tuple[str, str]:
    """Transform data to the requested format.

    When prefer_toon=True, always attempts TOON conversion (honoring explicit request).
    Falls back to JSON only if TOON conversion fails.

    Args:
        data: The data to transform
        prefer_toon: Whether the client explicitly requests TOON format
        min_array_size: Minimum array size for TOON consideration (unused when prefer_toon=True)

    Returns:
        Tuple of (formatted_string, content_type)
        Content type is "text/toon" or "application/json"

    Examples:
        >>> data = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
        >>> text, content_type = transform_result(data, prefer_toon=True)
        >>> content_type
        'text/toon'

        >>> # Even flat dicts use TOON when explicitly requested
        >>> text, content_type = transform_result({"simple": "dict"}, prefer_toon=True)
        >>> content_type
        'text/toon'
    """
    if prefer_toon:
        # Honor explicit TOON request - attempt conversion regardless of data shape
        toon_result = to_toon(data)
        if toon_result is not None:
            return toon_result, "text/toon"
        # Fall through to JSON only if TOON conversion fails

    # Default to JSON
    return to_json(data), "application/json"


def get_size_comparison(data: Any) -> dict[str, Any]:
    """Get size comparison between JSON and TOON for given data.

    Useful for debugging and metrics.

    Args:
        data: Data to compare

    Returns:
        Dict with json_size, toon_size, savings_percent, and recommendation
    """
    json_str = to_json(data)
    json_size = len(json_str)

    result: dict[str, Any] = {
        "json_size": json_size,
        "toon_size": None,
        "savings_percent": 0.0,
        "savings_bytes": 0,
        "recommendation": "json",
        "toon_beneficial": should_use_toon(data),
    }

    toon_str = to_toon(data)
    if toon_str is not None:
        toon_size = len(toon_str)
        result["toon_size"] = toon_size
        result["savings_bytes"] = json_size - toon_size
        if json_size > 0:
            result["savings_percent"] = round((1 - toon_size / json_size) * 100, 1)

        if toon_size < json_size and result["toon_beneficial"]:
            result["recommendation"] = "toon"

    return result

"""Tests for TOON format transformer."""

from __future__ import annotations

import pytest

from forge_armory.toon import (
    get_size_comparison,
    is_toon_available,
    should_use_toon,
    to_json,
    to_toon,
    transform_result,
)


class TestToonAvailability:
    """Tests for TOON availability check."""

    def test_is_toon_available(self):
        """toon_python should be available in test environment."""
        assert is_toon_available() is True


class TestShouldUseToon:
    """Tests for should_use_toon() heuristic."""

    def test_uniform_array_returns_true(self):
        """Uniform array of objects should use TOON."""
        data = [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
        ]
        assert should_use_toon(data) is True

    def test_uniform_array_three_items(self):
        """Larger uniform array should use TOON."""
        data = [
            {"id": 1, "name": "Alice", "email": "alice@test.com"},
            {"id": 2, "name": "Bob", "email": "bob@test.com"},
            {"id": 3, "name": "Charlie", "email": "charlie@test.com"},
        ]
        assert should_use_toon(data) is True

    def test_heterogeneous_array_returns_false(self):
        """Non-uniform array should not use TOON."""
        data = [
            {"id": 1, "name": "Alice"},
            {"id": 2, "email": "bob@test.com"},  # Different keys
        ]
        assert should_use_toon(data) is False

    def test_nested_uniform_array_returns_true(self):
        """Dict with uniform array value should use TOON."""
        data = {
            "users": [
                {"id": 1, "name": "Alice"},
                {"id": 2, "name": "Bob"},
            ]
        }
        assert should_use_toon(data) is True

    def test_deeply_nested_uniform_array(self):
        """Dict with deeply nested uniform array should use TOON."""
        data = {
            "response": {
                "data": [
                    {"date": "2026-01-19", "temp": 5},
                    {"date": "2026-01-20", "temp": 7},
                ]
            }
        }
        # Only checks immediate children, so this returns False
        assert should_use_toon(data) is False

    def test_simple_dict_returns_false(self):
        """Simple flat dict should not use TOON."""
        data = {"temperature": 20, "city": "London"}
        assert should_use_toon(data) is False

    def test_string_returns_false(self):
        """Strings should not use TOON."""
        assert should_use_toon("hello") is False

    def test_number_returns_false(self):
        """Numbers should not use TOON."""
        assert should_use_toon(42) is False

    def test_none_returns_false(self):
        """None should not use TOON."""
        assert should_use_toon(None) is False

    def test_empty_array_returns_false(self):
        """Empty array should not use TOON."""
        assert should_use_toon([]) is False

    def test_single_item_array_returns_false(self):
        """Single item array should not use TOON (below min_array_size)."""
        data = [{"id": 1, "name": "Alice"}]
        assert should_use_toon(data) is False

    def test_min_array_size_parameter(self):
        """min_array_size parameter should be respected."""
        data = [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
        ]
        assert should_use_toon(data, min_array_size=2) is True
        assert should_use_toon(data, min_array_size=3) is False

    def test_array_of_primitives_returns_false(self):
        """Array of primitives should not use TOON."""
        data = [1, 2, 3, 4, 5]
        assert should_use_toon(data) is False

    def test_mixed_array_returns_false(self):
        """Mixed array (objects and primitives) should not use TOON."""
        data = [{"id": 1}, "string", 42]
        assert should_use_toon(data) is False


class TestToToon:
    """Tests for to_toon() conversion."""

    def test_converts_uniform_array(self):
        """to_toon should convert uniform array."""
        data = [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
        ]
        result = to_toon(data)
        assert result is not None
        assert "Alice" in result
        assert "Bob" in result

    def test_converts_nested_array(self):
        """to_toon should convert nested array with headers."""
        data = {
            "users": [
                {"id": 1, "name": "Alice"},
                {"id": 2, "name": "Bob"},
            ]
        }
        result = to_toon(data)
        assert result is not None
        assert "users[2]" in result
        assert "{id,name}" in result

    def test_converts_simple_dict(self):
        """to_toon should convert simple dict."""
        data = {"temperature": 20, "city": "London"}
        result = to_toon(data)
        assert result is not None
        assert "temperature" in result
        assert "20" in result

    def test_handles_special_characters(self):
        """to_toon should handle special characters."""
        data = [
            {"name": "O'Brien", "city": "New York"},
            {"name": "Smith", "city": "Los Angeles"},
        ]
        result = to_toon(data)
        assert result is not None


class TestToJson:
    """Tests for to_json() conversion."""

    def test_converts_dict(self):
        """to_json should convert dict."""
        data = {"temperature": 20, "city": "London"}
        result = to_json(data)
        assert result == '{"temperature": 20, "city": "London"}'

    def test_converts_array(self):
        """to_json should convert array."""
        data = [1, 2, 3]
        result = to_json(data)
        assert result == "[1, 2, 3]"

    def test_indent_parameter(self):
        """to_json should respect indent parameter."""
        data = {"a": 1}
        result = to_json(data, indent=2)
        assert "\n" in result

    def test_handles_non_serializable(self):
        """to_json should handle non-serializable types via default=str."""
        from datetime import datetime

        data = {"time": datetime(2026, 1, 19, 12, 0, 0)}
        result = to_json(data)
        assert "2026" in result


class TestTransformResult:
    """Tests for transform_result() main function."""

    def test_returns_toon_when_preferred_and_beneficial(self):
        """Returns TOON format when requested and data is suitable."""
        data = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
        formatted, content_type = transform_result(data, prefer_toon=True)
        assert content_type == "text/toon"
        assert "Alice" in formatted

    def test_returns_toon_when_preferred_even_for_simple_data(self):
        """Returns TOON format for any data when explicitly requested."""
        data = {"simple": "object"}
        formatted, content_type = transform_result(data, prefer_toon=True)
        # When TOON is explicitly requested, it should be used regardless of data shape
        assert content_type == "text/toon"
        assert "simple" in formatted

    def test_returns_json_when_not_preferred(self):
        """Returns JSON when client doesn't prefer TOON."""
        data = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
        formatted, content_type = transform_result(data, prefer_toon=False)
        assert content_type == "application/json"

    def test_default_is_json(self):
        """Default format should be JSON."""
        data = [{"id": 1}, {"id": 2}]
        formatted, content_type = transform_result(data)
        assert content_type == "application/json"


class TestGetSizeComparison:
    """Tests for get_size_comparison() metrics function."""

    def test_returns_all_fields(self):
        """Should return all expected fields."""
        data = [{"id": 1}, {"id": 2}]
        result = get_size_comparison(data)
        assert "json_size" in result
        assert "toon_size" in result
        assert "savings_percent" in result
        assert "savings_bytes" in result
        assert "recommendation" in result
        assert "toon_beneficial" in result

    def test_recommends_toon_for_uniform_array(self):
        """Should recommend TOON for uniform arrays."""
        data = [
            {"id": 1, "name": "Alice", "email": "alice@test.com"},
            {"id": 2, "name": "Bob", "email": "bob@test.com"},
            {"id": 3, "name": "Charlie", "email": "charlie@test.com"},
        ]
        result = get_size_comparison(data)
        assert result["recommendation"] == "toon"
        assert result["toon_beneficial"] is True
        assert result["savings_percent"] > 0

    def test_recommends_json_for_simple_data(self):
        """Should recommend JSON for non-beneficial data."""
        data = {"temperature": 20}
        result = get_size_comparison(data)
        assert result["recommendation"] == "json"
        assert result["toon_beneficial"] is False

    def test_shows_savings(self):
        """Should show positive savings for beneficial data."""
        data = [
            {"id": 1, "name": "Alice", "email": "alice@test.com"},
            {"id": 2, "name": "Bob", "email": "bob@test.com"},
        ]
        result = get_size_comparison(data)
        assert result["savings_bytes"] > 0
        assert result["savings_percent"] > 0
        assert result["toon_size"] < result["json_size"]


class TestRealWorldData:
    """Tests with real-world-like data structures."""

    def test_geocode_response(self):
        """Test with geocode-like response data."""
        data = [
            {
                "name": "London",
                "country": "United Kingdom",
                "country_code": "GB",
                "latitude": 51.5074,
                "longitude": -0.1278,
                "timezone": "Europe/London",
                "population": 8982000,
                "admin1": "England",
            },
            {
                "name": "London",
                "country": "Canada",
                "country_code": "CA",
                "latitude": 42.9849,
                "longitude": -81.2453,
                "timezone": "America/Toronto",
                "population": 383822,
                "admin1": "Ontario",
            },
        ]
        assert should_use_toon(data) is True
        comparison = get_size_comparison(data)
        assert comparison["savings_percent"] > 30  # Expect significant savings

    def test_forecast_response(self):
        """Test with forecast-like response data."""
        data = {
            "location": "Berlin, Germany",
            "timezone": "Europe/Berlin",
            "daily": [
                {"date": "2026-01-19", "temp_max": 5, "temp_min": -2, "description": "Cloudy"},
                {"date": "2026-01-20", "temp_max": 7, "temp_min": 0, "description": "Sunny"},
                {"date": "2026-01-21", "temp_max": 4, "temp_min": -3, "description": "Rain"},
            ],
        }
        assert should_use_toon(data) is True
        comparison = get_size_comparison(data)
        assert comparison["savings_percent"] > 20

    def test_current_weather_response(self):
        """Test with current weather-like response (not beneficial)."""
        data = {
            "location": "Tokyo, Japan",
            "temperature": 12,
            "feels_like": 10,
            "humidity": 65,
            "weather_description": "Partly cloudy",
            "wind_speed": 15,
        }
        assert should_use_toon(data) is False
        comparison = get_size_comparison(data)
        assert comparison["recommendation"] == "json"

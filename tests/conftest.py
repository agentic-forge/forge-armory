"""Pytest configuration and fixtures for Armory tests."""

from __future__ import annotations

import pytest


@pytest.fixture
def mock_gateway_url() -> str:
    """Default mock gateway URL for testing."""
    return "http://localhost:8080/mcp"


@pytest.fixture
def mock_backend_url() -> str:
    """Default mock backend URL for testing."""
    return "http://localhost:8000/mcp"

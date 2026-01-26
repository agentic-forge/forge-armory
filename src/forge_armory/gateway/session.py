"""MCP session management for backend connections.

Implements the MCP Streamable HTTP protocol session handshake:
1. Client sends `initialize` method
2. Server returns `Mcp-Session-Id` header
3. Client sends `notifications/initialized`
4. Subsequent requests include `Mcp-Session-Id` header
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from forge_armory.db import Backend

logger = logging.getLogger(__name__)


def _parse_response(response: httpx.Response) -> dict[str, Any]:
    """Parse response body, handling both JSON and SSE formats.

    MCP Streamable HTTP servers may return responses as:
    - Direct JSON (content-type: application/json)
    - SSE format (content-type: text/event-stream):
      event: message
      data: {"jsonrpc":"2.0",...}

    Args:
        response: HTTP response to parse

    Returns:
        Parsed JSON-RPC response

    Raises:
        ValueError: If response cannot be parsed
    """
    content_type = response.headers.get("content-type", "")

    # Direct JSON response
    if "application/json" in content_type:
        return response.json()

    # SSE format - extract JSON from data: line
    if "text/event-stream" in content_type:
        text = response.text
        for line in text.split("\n"):
            line = line.strip()
            if line.startswith("data:"):
                json_str = line[5:].strip()  # Remove "data:" prefix
                if json_str:
                    return json.loads(json_str)

        raise ValueError(f"No data line found in SSE response: {text[:200]}")

    # Fallback: try to parse as JSON
    try:
        return response.json()
    except json.JSONDecodeError as e:
        raise ValueError(f"Cannot parse response (content-type: {content_type}): {e}")

# MCP protocol version
MCP_PROTOCOL_VERSION = "2024-11-05"

# Client info sent during initialization
CLIENT_INFO = {
    "name": "forge-armory",
    "version": "0.1.0",
}


@dataclass
class SessionState:
    """Tracks MCP session state for a backend."""

    session_id: str | None = None
    initialized: bool = False
    requires_session: bool = False


class MCPSessionError(Exception):
    """Error during MCP session management."""

    pass


def _build_headers(
    backend: Backend,
    session_id: str | None = None,
) -> dict[str, str]:
    """Build HTTP headers for MCP requests."""
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }

    if backend.api_key:
        headers["Authorization"] = f"Bearer {backend.api_key}"

    if session_id:
        headers["Mcp-Session-Id"] = session_id

    return headers


async def initialize_session(
    backend: Backend,
    client: httpx.AsyncClient,
) -> SessionState:
    """Initialize an MCP session with a backend server.

    Performs the full MCP initialization handshake:
    1. Send `initialize` request
    2. Extract session ID from response headers (if any)
    3. Send `notifications/initialized` (if session was created)

    Args:
        backend: Backend configuration
        client: HTTP client to use for requests

    Returns:
        SessionState with session details

    Raises:
        MCPSessionError: If initialization fails or backend has no URL
    """
    if not backend.url:
        raise MCPSessionError(f"Backend {backend.name} has no URL configured")

    headers = _build_headers(backend)
    url = backend.url  # Capture for type narrowing

    # Build initialize request
    init_request = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "initialize",
        "params": {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": CLIENT_INFO,
        },
    }

    try:
        response = await client.post(
            url,
            json=init_request,
            headers=headers,
            timeout=backend.timeout,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise MCPSessionError(
            f"Initialize request failed with status {e.response.status_code}: {e.response.text}"
        ) from e
    except httpx.RequestError as e:
        raise MCPSessionError(f"Initialize request failed: {e}") from e

    # Check for session ID in response header
    # Header names are case-insensitive in HTTP
    session_id = response.headers.get("mcp-session-id")

    state = SessionState(
        session_id=session_id,
        initialized=True,
        requires_session=session_id is not None,
    )

    if session_id:
        logger.info(
            "Session initialized for %s: %s...",
            backend.name,
            session_id[:8] if len(session_id) > 8 else session_id,
        )

        # Send initialized notification
        headers["Mcp-Session-Id"] = session_id
        await client.post(
            url,
            json={
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
            },
            headers=headers,
            timeout=backend.timeout,
        )
    else:
        logger.debug("Backend %s does not require sessions", backend.name)

    return state


async def refresh_session(
    backend: Backend,
    client: httpx.AsyncClient,
) -> SessionState:
    """Refresh/re-initialize a session.

    Use this when a session expires or becomes invalid.

    Args:
        backend: Backend configuration
        client: HTTP client to use for requests

    Returns:
        New SessionState
    """
    logger.info("Refreshing session for %s", backend.name)
    return await initialize_session(backend, client)


async def call_tool_with_session(
    backend: Backend,
    tool_name: str,
    arguments: dict[str, Any],
    session_id: str | None,
    client: httpx.AsyncClient,
) -> dict[str, Any]:
    """Call a tool on a backend with session support.

    Args:
        backend: Backend configuration
        tool_name: Name of the tool to call
        arguments: Tool arguments
        session_id: Session ID to include (if any)
        client: HTTP client to use

    Returns:
        JSON-RPC response from the backend

    Raises:
        MCPSessionError: If the call fails or backend has no URL
    """
    if not backend.url:
        raise MCPSessionError(f"Backend {backend.name} has no URL configured")

    headers = _build_headers(backend, session_id)
    url = backend.url  # Capture for type narrowing

    request = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments,
        },
    }

    try:
        response = await client.post(
            url,
            json=request,
            headers=headers,
            timeout=backend.timeout,
        )
        response.raise_for_status()
        return _parse_response(response)
    except ValueError as e:
        raise MCPSessionError(f"Failed to parse tool call response: {e}") from e
    except httpx.HTTPStatusError as e:
        # Check if this is a session error
        if e.response.status_code == 400:
            try:
                error_data = _parse_response(e.response)
                error_str = str(error_data).lower()
                if "session" in error_str or "invalid" in error_str:
                    raise MCPSessionError(
                        f"Session error (may need refresh): {error_data}"
                    ) from e
            except (ValueError, KeyError):
                pass
        raise MCPSessionError(
            f"Tool call failed with status {e.response.status_code}: {e.response.text}"
        ) from e
    except httpx.RequestError as e:
        raise MCPSessionError(f"Tool call request failed: {e}") from e


async def list_tools_with_session(
    backend: Backend,
    session_id: str | None,
    client: httpx.AsyncClient,
) -> dict[str, Any]:
    """List tools from a backend with session support.

    Args:
        backend: Backend configuration
        session_id: Session ID to include (if any)
        client: HTTP client to use

    Returns:
        JSON-RPC response containing tools list

    Raises:
        MCPSessionError: If the request fails or backend has no URL
    """
    if not backend.url:
        raise MCPSessionError(f"Backend {backend.name} has no URL configured")

    headers = _build_headers(backend, session_id)
    url = backend.url  # Capture for type narrowing

    request = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "tools/list",
    }

    try:
        response = await client.post(
            url,
            json=request,
            headers=headers,
            timeout=backend.timeout,
        )
        response.raise_for_status()
        return _parse_response(response)
    except ValueError as e:
        raise MCPSessionError(f"Failed to parse tools/list response: {e}") from e
    except httpx.HTTPStatusError as e:
        raise MCPSessionError(
            f"tools/list failed with status {e.response.status_code}: {e.response.text}"
        ) from e
    except httpx.RequestError as e:
        raise MCPSessionError(f"tools/list request failed: {e}") from e

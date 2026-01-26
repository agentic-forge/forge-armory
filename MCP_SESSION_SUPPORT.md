# MCP Session Support for Armory

## Overview

Some MCP servers (like HuggingFace) require session management via the MCP Streamable HTTP protocol. Currently, Armory doesn't support sessions, which prevents it from proxying to these servers.

This document outlines how to add session support to Armory.

## Background

### MCP Streamable HTTP Protocol

The MCP Streamable HTTP transport requires:

1. **Initialize Request**: Client sends `initialize` method
2. **Session ID**: Server returns `Mcp-Session-Id` header
3. **Initialized Notification**: Client sends `notifications/initialized`
4. **Subsequent Requests**: Client includes `Mcp-Session-Id` header

### Current Armory Behavior

Armory currently:
- Handles `initialize` requests but doesn't manage per-backend sessions
- Doesn't store or forward session IDs
- Treats each request as stateless

### Required Changes

Armory needs to:
1. Initialize sessions with upstream MCP servers that require them
2. Store session IDs per backend
3. Include session IDs when calling upstream servers

## Implementation Plan

### Phase 1: Backend Session Management

#### 1.1 Update MCPBackend Model

```python
# In forge_armory/gateway/models.py or similar

@dataclass
class MCPBackend:
    name: str
    url: str
    api_key: str | None = None
    enabled: bool = True

    # New session fields
    session_id: str | None = None
    session_initialized: bool = False
    requires_session: bool = False  # Discovered during first connect
```

#### 1.2 Add Session Initialization Logic

```python
# In forge_armory/gateway/connection.py or manager.py

async def initialize_backend_session(
    backend: MCPBackend,
    client: httpx.AsyncClient,
) -> str | None:
    """Initialize MCP session with a backend server.

    Returns session ID if server requires sessions, None otherwise.
    """
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if backend.api_key:
        headers["Authorization"] = f"Bearer {backend.api_key}"

    # Send initialize request
    init_request = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "forge-armory",
                "version": "0.1.0",
            },
        },
    }

    response = await client.post(
        backend.url,
        json=init_request,
        headers=headers,
        timeout=30.0,
    )
    response.raise_for_status()

    # Check for session ID in response header
    session_id = response.headers.get("mcp-session-id")

    if session_id:
        # Send initialized notification
        headers["Mcp-Session-Id"] = session_id
        await client.post(
            backend.url,
            json={
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
            },
            headers=headers,
            timeout=30.0,
        )

        backend.session_id = session_id
        backend.session_initialized = True
        backend.requires_session = True

    return session_id
```

#### 1.3 Update Backend Manager

```python
# In forge_armory/gateway/manager.py

class BackendManager:
    async def initialize(self) -> None:
        """Initialize all backends, including session setup."""
        for backend in self.backends:
            try:
                async with httpx.AsyncClient(follow_redirects=True) as client:
                    await initialize_backend_session(backend, client)

                    # Also fetch tools
                    tools = await self._fetch_backend_tools(backend, client)
                    self._register_tools(backend, tools)

            except Exception as e:
                logger.warning(
                    "Failed to initialize backend",
                    backend=backend.name,
                    error=str(e),
                )

    async def call_backend_tool(
        self,
        backend: MCPBackend,
        tool_name: str,
        arguments: dict,
    ) -> Any:
        """Call a tool on a backend, handling sessions."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }

        if backend.api_key:
            headers["Authorization"] = f"Bearer {backend.api_key}"

        # Include session ID if backend requires it
        if backend.session_id:
            headers["Mcp-Session-Id"] = backend.session_id

        # Make tool call...
```

### Phase 2: Session Lifecycle Management

#### 2.1 Session Expiry Handling

Sessions may expire. Handle this gracefully:

```python
async def call_with_session_retry(
    backend: MCPBackend,
    request_fn: Callable,
) -> Any:
    """Call backend with automatic session re-initialization on expiry."""
    try:
        return await request_fn()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 400:
            # Check if it's a session error
            try:
                error = e.response.json()
                if "session" in str(error).lower():
                    # Re-initialize session and retry
                    await initialize_backend_session(backend, client)
                    return await request_fn()
            except:
                pass
        raise
```

#### 2.2 Periodic Session Refresh

Optionally refresh sessions before they expire:

```python
async def refresh_sessions_periodically(self):
    """Background task to refresh sessions."""
    while True:
        await asyncio.sleep(300)  # Every 5 minutes

        for backend in self.backends:
            if backend.requires_session:
                try:
                    await initialize_backend_session(backend, client)
                except Exception as e:
                    logger.warning(
                        "Failed to refresh session",
                        backend=backend.name,
                        error=str(e),
                    )
```

### Phase 3: Configuration

#### 3.1 Backend Configuration Schema

Update the backend configuration to support session-related options:

```yaml
# In config or database
backends:
  - name: huggingface
    url: https://huggingface.co/mcp
    api_key: ${HF_TOKEN}  # Optional
    requires_session: auto  # auto, yes, no
```

#### 3.2 Admin UI Updates

Add session status to the Armory admin UI:

- Show session ID (truncated) for each backend
- Show session status: "Active", "Expired", "Not Required"
- Add "Refresh Session" button

## Testing

### Test with HuggingFace MCP Server

1. Add HuggingFace as a backend:
   ```
   name: huggingface
   url: https://huggingface.co/mcp
   api_key: (optional)
   ```

2. Verify session initialization in logs:
   ```
   INFO: Session initialized for huggingface: abc123...
   ```

3. Verify tools are fetched:
   ```
   INFO: Fetched 9 tools from huggingface
   ```

4. Test tool calls through Armory:
   ```bash
   curl -X POST http://localhost:4042/mcp \
     -H "Content-Type: application/json" \
     -d '{
       "jsonrpc": "2.0",
       "id": "1",
       "method": "tools/call",
       "params": {
         "name": "huggingface__model_search",
         "arguments": {"query": "llama"}
       }
     }'
   ```

### Test Session Expiry

1. Manually expire session (if possible) or wait
2. Make a tool call
3. Verify session is re-initialized automatically
4. Verify tool call succeeds

## Files to Modify

| File | Changes |
|------|---------|
| `forge_armory/gateway/models.py` | Add session fields to MCPBackend |
| `forge_armory/gateway/connection.py` | Add session initialization logic |
| `forge_armory/gateway/manager.py` | Update to manage sessions |
| `forge_armory/server.py` | Pass session ID in tool calls |
| `forge_armory/config.py` | Add session configuration options |

## References

- [MCP Streamable HTTP Transport Spec](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports)
- [HuggingFace MCP Server](https://huggingface.co/docs/hub/en/hf-mcp-server)

## Implementation in forge-orchestrator (Reference)

The custom MCP server support in forge-orchestrator already implements this pattern:

```python
# forge-orchestrator/src/forge_orchestrator/orchestrator.py

async def _mcp_initialize_session(client, server_url, headers, timeout):
    """Initialize an MCP session and return the session ID."""
    # Send initialize request
    # Get session ID from response header
    # Send initialized notification
    # Return session ID

async def fetch_custom_server_tools(server_url, server_name, api_key, timeout):
    """Fetch tools with session support."""
    session_id = await _mcp_initialize_session(...)
    # Include session ID in tools/list request
    # Store session ID in tool definitions for later calls

async def call_custom_server_tool(server_url, original_tool_name, api_key, session_id, **kwargs):
    """Call tool with session ID."""
    # Initialize new session if needed
    # Include Mcp-Session-Id header
```

This same pattern should be adapted for Armory's backend management.

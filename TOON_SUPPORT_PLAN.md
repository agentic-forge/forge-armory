# TOON Format Support Implementation Plan

> **Status:** Phase 4 Complete (All Phases Done)
> **Last Updated:** 2026-01-19
> **Related:** [blueprint/docs/VISION.md](../blueprint/docs/VISION.md)

## Overview

### Goal

Add TOON (Token-Oriented Object Notation) format support to Armory via HTTP content negotiation. Clients can request tool results in TOON format using the `Accept: text/toon` header, reducing token usage by 30-60% for structured data sent to LLMs.

### Approach: Content Negotiation

Standard HTTP content negotiation pattern:

1. Client sends `Accept: text/toon` header with MCP request
2. Armory converts tool results to TOON format
3. Response includes `Content-Type: text/toon`
4. Default remains JSON for backward compatibility

### Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Trigger mechanism | `Accept` header | Standard HTTP, client-driven |
| Default format | JSON | Backward compatibility |
| TOON library | `toon-python` (PyPI) | Existing, maintained library |
| Scope | Tool results only | Where structured data appears |
| Fallback | JSON if TOON fails | Graceful degradation |

---

## Architecture

### Request/Response Flow

```
MCP Client                          Armory                         Backend
    │                                  │                              │
    │ POST /mcp                        │                              │
    │ Accept: text/toon                │                              │
    │ {"method": "tools/call", ...}    │                              │
    │─────────────────────────────────►│                              │
    │                                  │  Call backend tool           │
    │                                  │─────────────────────────────►│
    │                                  │◄─────────────────────────────│
    │                                  │  JSON result                 │
    │                                  │                              │
    │                                  │  Convert to TOON             │
    │                                  │  (if beneficial)             │
    │                                  │                              │
    │ Content-Type: text/toon          │                              │
    │ {"result": {"content": [...]}}   │                              │
    │◄─────────────────────────────────│                              │
```

### Component Changes

```
┌─────────────────────────────────────────────────────────────────────┐
│                              Armory                                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐     │
│  │                     MCP Endpoints                           │     │
│  │                                                             │     │
│  │  POST /mcp                                                  │     │
│  │    - Check Accept header                                    │     │
│  │    - Pass format preference to handler                      │     │
│  │                                                             │     │
│  └──────────────────────────┬─────────────────────────────────┘     │
│                              │                                       │
│                              ▼                                       │
│  ┌────────────────────────────────────────────────────────────┐     │
│  │                     MCPGateway                              │     │
│  │                                                             │     │
│  │  _format_tool_result(result, format="json"|"toon")         │     │
│  │    - Detect if TOON beneficial                              │     │
│  │    - Convert or keep JSON                                   │     │
│  │    - Return with appropriate content type                   │     │
│  │                                                             │     │
│  └──────────────────────────┬─────────────────────────────────┘     │
│                              │                                       │
│  ┌────────────────────────────────────────────────────────────┐     │
│  │                   TOON Transformer (new)                    │     │
│  │                                                             │     │
│  │  - should_use_toon(data) → bool                            │     │
│  │  - to_toon(data) → str                                     │     │
│  │  - Uses toon-python library                                 │     │
│  │                                                             │     │
│  └────────────────────────────────────────────────────────────┘     │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Implementation Details

### 1. New Dependency

```toml
# In pyproject.toml
[project.dependencies]
# ... existing ...
toon-python = ">=0.1.0"
```

### 2. TOON Transformer Module

```python
# src/forge_armory/toon/transformer.py

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Lazy import to avoid startup cost if TOON not used
_toon_module = None


def _get_toon():
    """Lazy load toon-python module."""
    global _toon_module
    if _toon_module is None:
        try:
            import toon
            _toon_module = toon
        except ImportError:
            logger.warning("toon-python not installed, TOON format unavailable")
            _toon_module = False
    return _toon_module if _toon_module else None


def should_use_toon(data: Any) -> bool:
    """Determine if data would benefit from TOON format.

    TOON excels at:
    - Uniform arrays of objects (same keys)
    - Tabular data structures
    - Flat or shallow nesting

    TOON is less effective for:
    - Deeply nested structures
    - Irregular/heterogeneous objects
    - Simple primitives or short strings

    Args:
        data: The data to evaluate

    Returns:
        True if TOON would provide token savings
    """
    if not isinstance(data, (dict, list)):
        return False

    # Check for uniform array of objects (best case for TOON)
    if isinstance(data, list) and len(data) >= 2:
        if all(isinstance(item, dict) for item in data):
            # Check if all objects have same keys
            try:
                first_keys = set(data[0].keys())
                if all(set(item.keys()) == first_keys for item in data):
                    return True
            except (AttributeError, IndexError):
                pass

    # Check for dict with array values that are uniform
    if isinstance(data, dict):
        for value in data.values():
            if isinstance(value, list) and len(value) >= 2:
                if all(isinstance(item, dict) for item in value):
                    try:
                        first_keys = set(value[0].keys())
                        if all(set(item.keys()) == first_keys for item in value):
                            return True
                    except (AttributeError, IndexError):
                        pass

    return False


def to_toon(data: Any) -> str | None:
    """Convert data to TOON format.

    Args:
        data: JSON-serializable data

    Returns:
        TOON-formatted string, or None if conversion fails
    """
    toon = _get_toon()
    if toon is None:
        return None

    try:
        return toon.encode(data)
    except Exception as e:
        logger.warning("TOON encoding failed: %s", e)
        return None


def to_json(data: Any) -> str:
    """Convert data to JSON format (fallback)."""
    return json.dumps(data)


def transform_result(data: Any, prefer_toon: bool = False) -> tuple[str, str]:
    """Transform data to requested format.

    Args:
        data: The data to transform
        prefer_toon: Whether client prefers TOON format

    Returns:
        Tuple of (formatted_string, content_type)
    """
    if prefer_toon and should_use_toon(data):
        toon_result = to_toon(data)
        if toon_result is not None:
            return toon_result, "text/toon"

    # Fallback to JSON
    return to_json(data), "application/json"
```

### 3. Format Detection from Request

```python
# src/forge_armory/server.py (additions)

from enum import Enum


class OutputFormat(str, Enum):
    JSON = "json"
    TOON = "toon"


def get_preferred_format(request: Request) -> OutputFormat:
    """Extract preferred output format from Accept header.

    Supports:
    - Accept: text/toon → TOON format
    - Accept: application/json → JSON format (default)
    - No header → JSON format (default)
    """
    accept = request.headers.get("accept", "application/json")

    if "text/toon" in accept:
        return OutputFormat.TOON

    return OutputFormat.JSON
```

### 4. Modified MCP Handler

```python
# In server.py - updated handle_mcp_request

async def handle_mcp_request(self, request: Request) -> JSONResponse:
    """Handle incoming MCP JSON-RPC requests."""
    context = get_request_context(request)
    preferred_format = get_preferred_format(request)

    try:
        body = await request.json()
    except json.JSONDecodeError:
        return self._error_response(-32700, "Parse error", None)

    method = body.get("method", "")
    params = body.get("params", {})
    request_id = body.get("id")

    # ... existing routing logic ...

    if method == "tools/call":
        result = await self._handle_call_tool(params, context, preferred_format)

    # ... rest of handler ...
```

### 5. Modified Tool Result Formatting

```python
# In server.py - updated _format_tool_result

from forge_armory.toon.transformer import transform_result, should_use_toon

def _format_tool_result(
    self,
    result: Any,
    preferred_format: OutputFormat = OutputFormat.JSON
) -> dict[str, Any]:
    """Format tool result for MCP response.

    Args:
        result: Raw tool result from backend
        preferred_format: Client's preferred output format

    Returns:
        MCP-formatted result with content array
    """
    # Extract the actual data to transform
    if isinstance(result, list):
        # FastMCP returns list of content items - check first item
        if result and isinstance(result[0], dict) and result[0].get("type") == "text":
            # Already MCP content format, extract text
            try:
                data = json.loads(result[0].get("text", "{}"))
            except json.JSONDecodeError:
                data = result[0].get("text", "")
        else:
            data = result
    elif isinstance(result, dict):
        data = result
    elif isinstance(result, str):
        # Try to parse as JSON
        try:
            data = json.loads(result)
        except json.JSONDecodeError:
            data = result
    else:
        data = result

    # Transform based on preference
    prefer_toon = preferred_format == OutputFormat.TOON
    formatted, content_type = transform_result(data, prefer_toon)

    # Build MCP content structure
    return {
        "content": [{
            "type": "text",
            "text": formatted,
        }],
        "_meta": {
            "content_format": "toon" if content_type == "text/toon" else "json"
        }
    }
```

### 6. Response Headers

```python
# In server.py - set response content type

async def handle_mcp_request(self, request: Request) -> JSONResponse:
    # ... existing logic ...

    # Determine actual content type used
    content_type = "application/json"
    if result and "_meta" in result:
        if result["_meta"].get("content_format") == "toon":
            content_type = "text/toon"
        # Remove _meta from response
        del result["_meta"]

    return JSONResponse(
        content={"jsonrpc": "2.0", "result": result, "id": request_id},
        headers={"X-Content-Format": content_type}  # Custom header for clarity
    )
```

---

## Configuration

### Environment Variables

```bash
# TOON settings (all optional)
ARMORY_TOON_ENABLED=true              # Enable TOON format support
ARMORY_TOON_MIN_ARRAY_SIZE=2          # Minimum array size to consider TOON
```

### Settings Class

```python
# In settings.py

class Settings(BaseSettings):
    # ... existing ...

    # TOON format settings
    toon_enabled: bool = True
    toon_min_array_size: int = 2
```

---

## Client Integration (Orchestrator)

For forge-orchestrator to use TOON:

### MCP Client Configuration

```python
# In forge-orchestrator mcp_client.py

class ArmoryMCPClient:
    def __init__(self, base_url: str, use_toon: bool = False):
        self.base_url = base_url
        self.use_toon = use_toon

    def _get_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.use_toon:
            headers["Accept"] = "text/toon"
        return headers

    async def call_tool(self, name: str, arguments: dict) -> Any:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/mcp",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {"name": name, "arguments": arguments},
                    "id": 1
                },
                headers=self._get_headers()
            )
            return response.json()
```

### Chat Request Extension

```python
# In forge-orchestrator models

class ChatRequest(BaseModel):
    # ... existing fields ...
    use_toon_format: bool = False  # New field
```

### forge-ui Toggle

The UI would add a toggle similar to the tools toggle:

```typescript
// In forge-ui chat header
const useToonFormat = ref(false)

// Pass to chat request
const sendMessage = async (content: string) => {
  await fetch('/api/chat', {
    method: 'POST',
    body: JSON.stringify({
      messages: [...],
      use_toon_format: useToonFormat.value
    })
  })
}
```

---

## Testing Strategy

### Unit Tests

```python
# tests/test_toon_transformer.py

class TestShouldUseToon:
    """Test TOON applicability detection."""

    def test_uniform_array_returns_true(self):
        """Uniform object array should use TOON."""
        data = [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
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

    def test_simple_dict_returns_false(self):
        """Simple flat dict should not use TOON."""
        data = {"temperature": 20, "city": "London"}
        assert should_use_toon(data) is False

    def test_string_returns_false(self):
        """Strings should not use TOON."""
        assert should_use_toon("hello") is False


class TestToToon:
    """Test TOON conversion."""

    def test_converts_uniform_array(self):
        """Verify TOON output format."""
        data = [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
        ]
        result = to_toon(data)
        assert result is not None
        # Verify TOON structure (header + rows)
        assert "[2]" in result or "id,name" in result


class TestTransformResult:
    """Test the main transform function."""

    def test_returns_toon_when_preferred_and_beneficial(self):
        """Returns TOON format when requested and data is suitable."""
        data = [{"a": 1}, {"a": 2}]
        formatted, content_type = transform_result(data, prefer_toon=True)
        assert content_type == "text/toon"

    def test_returns_json_when_toon_not_beneficial(self):
        """Falls back to JSON when TOON wouldn't help."""
        data = {"simple": "object"}
        formatted, content_type = transform_result(data, prefer_toon=True)
        assert content_type == "application/json"

    def test_returns_json_when_not_preferred(self):
        """Returns JSON when client doesn't prefer TOON."""
        data = [{"a": 1}, {"a": 2}]
        formatted, content_type = transform_result(data, prefer_toon=False)
        assert content_type == "application/json"
```

### Integration Tests

```python
# tests/test_mcp_toon.py

class TestMCPToonFormat:
    """Test TOON format via MCP endpoint."""

    async def test_accept_toon_header(self, client):
        """TOON format returned when Accept header present."""
        # Setup: backend returns array data
        response = await client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": "test__list_items", "arguments": {}},
                "id": 1
            },
            headers={"Accept": "text/toon"}
        )

        assert response.status_code == 200
        data = response.json()
        # Check format indicator
        assert response.headers.get("X-Content-Format") == "text/toon"

    async def test_default_json_format(self, client):
        """JSON format returned by default."""
        response = await client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": "test__list_items", "arguments": {}},
                "id": 1
            }
        )

        assert response.status_code == 200
        # Should be JSON format
        assert response.headers.get("X-Content-Format") in (None, "application/json")
```

---

## Implementation Phases

### Phase 1: Core TOON Transformer ✅ COMPLETE

**Goal:** Add TOON conversion capability

**Tasks:**
1. ✅ Add `toon-python` dependency
2. ✅ Create `src/forge_armory/toon/transformer.py`
3. ✅ Implement `should_use_toon()` heuristics
4. ✅ Implement `to_toon()` wrapper
5. ✅ Write unit tests (34 tests)

**Deliverables:**
- ✅ TOON transformer module (`src/forge_armory/toon/`)
- ✅ Unit tests passing (111 total tests)

### Phase 2: MCP Integration ✅ COMPLETE

**Goal:** Wire TOON into MCP request/response flow

**Tasks:**
1. ✅ Add `get_preferred_format()` helper
2. ✅ Update `_format_tool_result()` to accept format preference
3. ✅ Update `handle_mcp_request()` to check Accept header
4. ✅ Add `X-Content-Format` response header
5. ✅ Write integration tests (6 new tests)

**Deliverables:**
- ✅ MCP endpoint supports `Accept: text/toon`
- ✅ Mount endpoints support `Accept: text/toon`
- ✅ `X-Content-Format` response header
- ✅ All 117 tests passing

### Phase 3: Orchestrator Support ✅ COMPLETE

**Goal:** Enable orchestrator to request TOON

**Tasks:**
1. ✅ Add `use_toon_format: bool = False` to ChatRequest model (server.py)
2. ✅ Update MCP client to send `Accept: text/toon` header when enabled
3. ✅ Pass setting through chat_stream → run_stream → MCPServerStreamableHTTP
4. ✅ All 31 orchestrator tests passing

**Deliverables:**
- ✅ ChatRequest model accepts `use_toon_format` field
- ✅ MCPServerStreamableHTTP created with Accept header when TOON enabled
- ✅ Orchestrator tests pass

### Phase 4: UI Toggle ✅ COMPLETE

**Goal:** User-facing TOON toggle in forge-ui

**Tasks:**
1. ✅ Add `useToonFormat: boolean` to `AdvancedViewSettings` type
2. ✅ Add default value `false` in `useConversation.ts`
3. ✅ Add toggle button to chat input header (next to Tools toggle)
4. ✅ Persist preference in local storage (via existing settings mechanism)
5. ✅ Include `use_toon_format` in chat API requests
6. ✅ Visual indicator: orange accent when enabled, status dot glow

**Deliverables:**
- ✅ TOON toggle in forge-ui chat header (advanced mode only)
- ✅ Orange visual indicator when active
- ✅ Preference persisted in localStorage
- ✅ Vue type check passes

---

## Dependencies

### New Python Packages

```toml
# In pyproject.toml
[project.dependencies]
# ... existing ...
toon-python = ">=0.1.0"
```

### System Requirements

- No additional system requirements
- toon-python is pure Python

---

## Open Questions / Future Work

### For Later Consideration

1. **Metrics tracking**: Track token savings from TOON
   - Compare JSON vs TOON byte sizes
   - Report in admin UI

2. **Selective TOON per tool**: Some tools might not benefit
   - Tool-level format hints in metadata
   - Auto-detect based on historical data shapes

3. **TOON for tool definitions**: Could also reduce context for tool schemas
   - Lower priority than results
   - Needs MCP protocol consideration

4. **Client caching**: Cache TOON conversions for repeated data patterns
   - Low priority, conversion is fast

5. **Streaming TOON**: For large result sets
   - Future consideration if needed

---

## Test Server: mcp-weather

The existing `mcp-weather` server in the Agentic Forge ecosystem returns structured JSON data ideal for testing TOON conversion.

### Tools Returning Structured Data

| Tool | Return Type | Data Shape | TOON Benefit |
|------|-------------|------------|--------------|
| `geocode` | `list[Location]` | 1-10 uniform objects | ~40% savings |
| `get_forecast` | `Forecast` | `daily: list[DailyForecast]` (7 objects) | ~35% savings |
| `get_forecast(hourly=True)` | `Forecast` | `hourly: list[HourlyForecast]` (168 objects) | ~50% savings |
| `get_air_quality` | `AirQuality` | Nested object (less benefit) | ~15% savings |

### Example Test Data

**`geocode("London", limit=3)` returns:**
```json
[
  {"name": "London", "country": "United Kingdom", "country_code": "GB", "latitude": 51.5074, "longitude": -0.1278, "timezone": "Europe/London", "population": 8982000, "admin1": "England"},
  {"name": "London", "country": "Canada", "country_code": "CA", "latitude": 42.9849, "longitude": -81.2453, "timezone": "America/Toronto", "population": 383822, "admin1": "Ontario"},
  {"name": "London", "country": "United States", "country_code": "US", "latitude": 37.129, "longitude": -84.0833, "timezone": "America/New_York", "population": 8126, "admin1": "Kentucky"}
]
```

**Expected TOON output:**
```
[3]{name,country,country_code,latitude,longitude,timezone,population,admin1}:
London,United Kingdom,GB,51.5074,-0.1278,Europe/London,8982000,England
London,Canada,CA,42.9849,-81.2453,America/Toronto,383822,Ontario
London,United States,US,37.129,-84.0833,America/New_York,8126,Kentucky
```

### Running the Test Server

```bash
# From the agentic-forge directory
cd mcp-servers/mcp-weather
uv sync
uv run mcp-weather --port 4050

# Or via Docker Compose (from forge-devtools)
docker compose up mcp-weather
```

### Test Scenarios

1. **High-value test**: `get_forecast(city="Berlin", days=7, hourly=True)`
   - Returns 168 hourly forecast objects
   - Expected 45-50% token reduction

2. **Medium test**: `geocode("Springfield", limit=10)`
   - Returns ~10 location objects
   - Expected 35-40% token reduction

3. **Low-value test**: `get_current_weather(city="Tokyo")`
   - Returns single nested object
   - Expected minimal or no benefit (TOON should fall back to JSON)

---

## References

- [TOON Format Official](https://toonformat.dev/)
- [TOON GitHub](https://github.com/toon-format/toon)
- [toon-python PyPI](https://pypi.org/project/toon-python/)
- [blueprint/docs/VISION.md](../blueprint/docs/VISION.md) - Project vision with TOON

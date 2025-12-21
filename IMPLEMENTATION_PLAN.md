# Forge Armory Implementation Plan

## Quick Status

| Phase | Description | Status | Tests |
|-------|-------------|--------|-------|
| 1 | Project setup | ✓ COMPLETE | - |
| 2 | Database layer | ✓ COMPLETE | 17 |
| 3 | Gateway connections | ✓ COMPLETE | 18 |
| 4 | Admin API | ✓ COMPLETE | 17 |
| 5 | CLI commands | ✓ COMPLETE | 3 |
| 6 | Gateway server | ✓ COMPLETE | - |
| **7** | **Integration tests** | **← NEXT** | - |
| 8 | Documentation | Pending | - |

**Total: 60 tests passing** | Type checking: 0 errors | Linting: Clean

---

## Project Overview

**forge-armory** is an MCP protocol gateway that aggregates multiple MCP servers.

> "Armory is to MCP servers what OpenRouter is to LLMs"

**Architecture:**
```
                    Client (Claude, etc.)
                           │
                           ▼
┌──────────────────────────────────────────────────────┐
│                    forge-armory                       │
├──────────────────────────────────────────────────────┤
│  POST /mcp              Aggregated MCP endpoint       │
│  POST /mcp/{prefix}     Direct backend access         │
│  GET  /.well-known/     Discovery metadata            │
│  /admin/*               REST API for management       │
├──────────────────────────────────────────────────────┤
│  BackendManager         Runtime MCP connections       │
├──────────────────────────────────────────────────────┤
│  PostgreSQL             backends, tools, tool_calls   │
└──────────────────────────────────────────────────────┘
         │                    │
         ▼                    ▼
   ┌──────────┐        ┌──────────┐
   │ Backend A │        │ Backend B │
   └──────────┘        └──────────┘
```

**Key Design Decisions:**
- Database `tools` table IS the tool registry (no in-memory cache)
- Tools are prefixed with `{backend_prefix}__{tool_name}` in aggregated endpoint
- Direct mount endpoints expose tools without prefix
- `mount_enabled` flag controls whether `/mcp/{prefix}` is available

---

## Project Structure

```
forge-armory/
├── src/forge_armory/
│   ├── __init__.py          # Version: 0.1.0
│   ├── __main__.py          # Entry point
│   ├── settings.py          # DATABASE_URL, HOST, PORT config
│   ├── cli.py               # Full CLI with backend, serve, metrics
│   ├── server.py            # Starlette + MCP gateway server
│   ├── db/
│   │   ├── __init__.py      # Exports all DB components
│   │   ├── engine.py        # Async SQLAlchemy engine
│   │   ├── models.py        # Backend, Tool, ToolCall ORM models
│   │   └── repository.py    # Repository pattern + Pydantic schemas
│   ├── gateway/
│   │   ├── __init__.py      # Exports gateway components
│   │   ├── connection.py    # BackendConnection (MCP client wrapper)
│   │   ├── manager.py       # BackendManager (connection pool)
│   │   └── exceptions.py    # Gateway exceptions
│   └── admin/
│       ├── __init__.py      # Exports admin components
│       ├── routes.py        # Starlette routes for /admin/*
│       └── schemas.py       # Pydantic request/response models
├── tests/
│   ├── conftest.py          # Shared fixtures
│   ├── test_cli.py          # CLI tests (3)
│   ├── test_db.py           # Database tests (17)
│   ├── test_gateway.py      # Gateway tests (18)
│   └── test_admin.py        # Admin API tests (17)
├── alembic/                 # Database migrations
├── pyproject.toml           # Dependencies & config
└── README.md
```

---

## CLI Commands

```bash
# Backend management
armory backend list                    # List all backends
armory backend add NAME --url URL      # Add a backend
armory backend remove NAME             # Remove a backend
armory backend enable NAME             # Enable a backend
armory backend disable NAME            # Disable a backend
armory backend refresh NAME            # Refresh tools from backend

# Server
armory serve [--host HOST] [--port PORT] [--reload]

# Metrics
armory metrics [--backend NAME]        # View tool call statistics

# Info
armory info                            # Show gateway info
armory --version                       # Show version
```

---

## API Endpoints

### MCP Protocol

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/mcp` | POST | Aggregated endpoint (all tools with prefixes) |
| `/mcp/{prefix}` | POST | Direct backend access (tools without prefix) |
| `/.well-known/mcp.json` | GET | Discovery metadata |

**MCP Methods Supported:**
- `initialize` - Server capabilities
- `tools/list` - List available tools
- `tools/call` - Call a tool
- `ping` - Health check

### Admin API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/admin/backends` | GET | List all backends |
| `/admin/backends` | POST | Create backend |
| `/admin/backends/{name}` | GET | Get backend details |
| `/admin/backends/{name}` | PUT | Update backend |
| `/admin/backends/{name}` | DELETE | Delete backend |
| `/admin/backends/{name}/refresh` | POST | Refresh tools |
| `/admin/backends/{name}/enable` | POST | Enable backend |
| `/admin/backends/{name}/disable` | POST | Disable backend |
| `/admin/tools` | GET | List all tools |
| `/admin/metrics` | GET | Get call metrics |

---

## Database Models

### Backend
```python
id: UUID (PK)
name: str (unique, indexed)
url: str | None              # HTTP URL
command: list | None         # Stdio command (future)
enabled: bool = True
timeout: float = 30.0
prefix: str | None           # Tool prefix (defaults to name)
mount_enabled: bool = True   # Enable /mcp/{prefix} endpoint
created_at, updated_at: datetime

@property
def effective_prefix(self) -> str:
    """Returns prefix if set, else name."""
```

### Tool
```python
id: UUID (PK)
backend_id: UUID (FK -> backends, CASCADE)
name: str                    # Original tool name
prefixed_name: str           # e.g., "weather__get_forecast" (unique, indexed)
description: str | None
input_schema: dict           # JSON Schema
refreshed_at: datetime
```

### ToolCall
```python
id: UUID (PK)
tool_id: UUID | None (FK -> tools, SET NULL)
backend_name: str (indexed)
tool_name: str
arguments: dict
success: bool
error_message: str | None
latency_ms: int
called_at: datetime (indexed)
```

---

## Configuration

Environment variables (prefix: `ARMORY_`):

| Variable | Default | Description |
|----------|---------|-------------|
| `ARMORY_DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/forge_armory` | Database connection |
| `ARMORY_HOST` | `0.0.0.0` | Server bind host |
| `ARMORY_PORT` | `8080` | Server bind port |

---

## Remaining Phases

### Phase 7: Integration Tests
- End-to-end tests with real database
- Test MCP protocol flow
- Test tool routing across backends
- Mark with `@pytest.mark.integration`

### Phase 8: Documentation
- README updates
- API documentation
- Deployment guide
- Example usage

---

## Development Commands

```bash
cd /MyWork/Projects/agentic-forge/forge-armory

# Install deps
uv sync

# Run tests
uv run pytest -v

# Type check
uv run basedpyright

# Lint
uv run ruff check .

# Format
uv run ruff format .

# Start server
uv run armory serve

# Pre-commit hooks
uv run pre-commit run --all-files
```

---

## Example Usage

```bash
# Add a weather backend
armory backend add weather --url http://localhost:8001/mcp --prefix wx

# Add a search backend (no direct mount)
armory backend add brave --url http://localhost:8002/mcp --prefix search --no-mount

# List backends
armory backend list

# Start the server
armory serve --port 8080

# Now clients can connect to:
# - http://localhost:8080/mcp          (all tools: wx__get_forecast, search__web_search)
# - http://localhost:8080/mcp/wx       (weather tools only: get_forecast)
```

---

## Tool Prefixing Example

Given backends:
| Backend | Prefix | Mount Enabled |
|---------|--------|---------------|
| `mcp-weather` | `weather` | ✓ |
| `brave-search` | `search` | ✗ |

Tools exposed:
| Endpoint | Tool Name |
|----------|-----------|
| `/mcp` | `weather__get_forecast` |
| `/mcp` | `weather__get_current` |
| `/mcp` | `search__web_search` |
| `/mcp/weather` | `get_forecast` |
| `/mcp/weather` | `get_current` |
| `/mcp/search` | *(not available - mount disabled)* |

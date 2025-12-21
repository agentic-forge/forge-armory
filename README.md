# Forge Armory

MCP protocol gateway that aggregates tools from multiple MCP servers.

> "Armory is to MCP servers what OpenRouter is to LLMs"

## Features

- **MCP Gateway**: Aggregates tools from multiple backend MCP servers
- **Dynamic Configuration**: Database-backed configuration with runtime updates
- **Admin API**: REST API for managing backends
- **CLI**: Command-line interface for backend management
- **Metrics**: Track tool calls, latency, and errors

## Installation

```bash
uv sync
```

## Quick Start

```bash
# Start the gateway server
armory serve

# Add a backend
armory backend add weather --url http://localhost:8000/mcp

# List backends
armory backend list

# View metrics
armory metrics
```

## Environment Variables

```bash
ARMORY_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/forge_armory
ARMORY_HOST=0.0.0.0
ARMORY_PORT=8080
```

## Development

```bash
# Install dependencies
uv sync

# Run tests
uv run pytest

# Type checking
uv run basedpyright

# Linting
uv run ruff check .

# Install pre-commit hooks
uv run pre-commit install
```

## License

MIT

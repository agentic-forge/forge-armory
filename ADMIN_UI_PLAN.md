# Armory Admin UI - Implementation Plan

## Overview

Web-based admin dashboard for managing forge-armory MCP gateway. Built with Vue.js 3 + TypeScript + Vite + Bun, embedded within the forge-armory repository.

### Goals

1. Visual management of MCP backend servers
2. Real-time view of registered tools
3. Basic metrics overview
4. Future: Tool call history, tool testing interface

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Framework | Vue.js 3 (Composition API) |
| Language | TypeScript |
| Build Tool | Vite |
| Package Manager | Bun |
| Styling | Tailwind CSS |
| HTTP Client | fetch (native) or axios |
| State Management | Pinia (if needed) |
| Routing | Vue Router |

### Directory Structure

```
forge-armory/
├── src/forge_armory/          # Python backend
│   ├── server.py              # Starlette app (serves API + static)
│   └── admin/                 # Admin REST API
├── admin-ui/                  # Vue.js frontend (NEW)
│   ├── package.json
│   ├── bun.lockb
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── tailwind.config.js
│   ├── index.html
│   ├── src/
│   │   ├── main.ts
│   │   ├── App.vue
│   │   ├── router/
│   │   │   └── index.ts
│   │   ├── views/
│   │   │   ├── DashboardView.vue
│   │   │   ├── BackendsView.vue
│   │   │   ├── ToolsView.vue
│   │   │   └── MetricsView.vue
│   │   ├── components/
│   │   │   ├── layout/
│   │   │   │   ├── Sidebar.vue
│   │   │   │   └── Header.vue
│   │   │   ├── backends/
│   │   │   │   ├── BackendList.vue
│   │   │   │   ├── BackendCard.vue
│   │   │   │   └── BackendForm.vue
│   │   │   ├── tools/
│   │   │   │   ├── ToolList.vue
│   │   │   │   └── ToolCard.vue
│   │   │   └── metrics/
│   │   │       ├── MetricsOverview.vue
│   │   │       └── CallHistory.vue
│   │   ├── api/
│   │   │   └── client.ts      # API client for /admin/*
│   │   ├── types/
│   │   │   └── index.ts       # TypeScript interfaces
│   │   └── assets/
│   │       └── styles.css
│   └── dist/                  # Built output (served by Starlette)
└── tests/
```

---

## Backend API Endpoints

The frontend will consume these existing `/admin/*` endpoints:

### Backends

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/admin/backends` | List all backends |
| POST | `/admin/backends` | Create new backend |
| GET | `/admin/backends/{name}` | Get backend details |
| PUT | `/admin/backends/{name}` | Update backend |
| DELETE | `/admin/backends/{name}` | Delete backend |
| POST | `/admin/backends/{name}/refresh` | Refresh tools |
| POST | `/admin/backends/{name}/enable` | Enable backend |
| POST | `/admin/backends/{name}/disable` | Disable backend |

### Tools

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/admin/tools` | List all tools |

### Metrics

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/admin/metrics` | Get aggregated metrics |
| GET | `/admin/metrics?backend={name}` | Filter by backend |

### Future Endpoints (to be added)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/admin/calls` | List recent tool calls |
| GET | `/admin/calls/{id}` | Get call details (args, response) |
| GET | `/admin/tools/{prefixed_name}` | Get tool details |
| POST | `/admin/tools/{prefixed_name}/test` | Test a tool |

---

## UI Design

### Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  ┌─────────┐                                         [Refresh]  │
│  │ ARMORY  │  Forge Armory Admin                                │
│  └─────────┘                                                    │
├─────────────┬───────────────────────────────────────────────────┤
│             │                                                   │
│  Dashboard  │  ┌─────────────────────────────────────────────┐  │
│             │  │                                             │  │
│  Backends   │  │              Main Content Area              │  │
│             │  │                                             │  │
│  Tools      │  │                                             │  │
│             │  │                                             │  │
│  Metrics    │  │                                             │  │
│             │  │                                             │  │
│  ─────────  │  │                                             │  │
│  Settings   │  │                                             │  │
│             │  └─────────────────────────────────────────────┘  │
└─────────────┴───────────────────────────────────────────────────┘
```

### Dashboard View

Overview with key metrics at a glance.

```
┌─────────────────────────────────────────────────────────────────┐
│  Dashboard                                                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  Backends    │  │    Tools     │  │  Calls (24h) │          │
│  │      3       │  │      12      │  │     156      │          │
│  │  2 connected │  │  from 3 svcs │  │  98% success │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│                                                                 │
│  Recent Activity                                                │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 12:34:56  weather__get_forecast  ✓  45ms               │   │
│  │ 12:34:52  search__web_search     ✓  230ms              │   │
│  │ 12:34:48  github__create_issue   ✗  timeout            │   │
│  │ 12:34:45  weather__get_current   ✓  38ms               │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Backends View

List and manage backend MCP servers.

```
┌─────────────────────────────────────────────────────────────────┐
│  Backends                                    [+ Add Backend]    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  ● mcp-weather                              [Refresh]   │   │
│  │    URL: http://localhost:8001/mcp                       │   │
│  │    Prefix: weather  │  Mount: ✓  │  Tools: 3            │   │
│  │    Status: Connected                    [Disable] [Delete]  │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  ○ brave-search                             [Refresh]   │   │
│  │    URL: http://localhost:8002/mcp                       │   │
│  │    Prefix: search  │  Mount: ✗  │  Tools: 2             │   │
│  │    Status: Disabled                     [Enable] [Delete]  │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Add/Edit Backend Modal

```
┌─────────────────────────────────────────────────────────────────┐
│  Add Backend                                              [×]   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Name *                                                         │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ mcp-weather                                             │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  URL *                                                          │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ http://localhost:8001/mcp                               │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  Prefix (defaults to name)                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ weather                                                 │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ☑ Enable direct mount (/mcp/{prefix})                         │
│  ☑ Enable on creation                                          │
│                                                                 │
│  Timeout (seconds)                                              │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 30                                                      │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│                                    [Cancel]  [Add Backend]      │
└─────────────────────────────────────────────────────────────────┘
```

### Tools View

Browse all registered tools across backends.

```
┌─────────────────────────────────────────────────────────────────┐
│  Tools                                      [Filter: All ▼]     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Search: [________________________] 🔍                          │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  weather__get_forecast                                  │   │
│  │  Get weather forecast for a location                    │   │
│  │  Backend: mcp-weather  │  Last refreshed: 5 min ago     │   │
│  │                                              [Test]     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  weather__get_current                                   │   │
│  │  Get current weather conditions                         │   │
│  │  Backend: mcp-weather  │  Last refreshed: 5 min ago     │   │
│  │                                              [Test]     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  search__web_search                                     │   │
│  │  Search the web using Brave Search                      │   │
│  │  Backend: brave-search  │  Last refreshed: 1 hour ago   │   │
│  │                                              [Test]     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Metrics View

Tool call statistics and history.

```
┌─────────────────────────────────────────────────────────────────┐
│  Metrics                           [Time: Last 24h ▼]           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Overview                                                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ Total Calls  │  │ Success Rate │  │ Avg Latency  │          │
│  │     156      │  │    98.1%     │  │    87ms      │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│                                                                 │
│  By Backend                                                     │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Backend        │ Calls │ Success │ Errors │ Avg Latency │   │
│  ├─────────────────────────────────────────────────────────┤   │
│  │ mcp-weather    │   89  │   89    │    0   │    42ms     │   │
│  │ brave-search   │   52  │   50    │    2   │   180ms     │   │
│  │ github         │   15  │   14    │    1   │    95ms     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  Recent Calls                                    [View All]     │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Time     │ Tool                  │ Status │ Latency     │   │
│  ├─────────────────────────────────────────────────────────┤   │
│  │ 12:34:56 │ weather__get_forecast │   ✓    │   45ms      │   │
│  │ 12:34:52 │ search__web_search    │   ✓    │  230ms      │   │
│  │ 12:34:48 │ github__create_issue  │   ✗    │  timeout    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## TypeScript Types

```typescript
// types/index.ts

export interface Backend {
  id: string;
  name: string;
  url: string | null;
  enabled: boolean;
  timeout: number;
  prefix: string | null;
  mount_enabled: boolean;
  effective_prefix: string;
  created_at: string;
  updated_at: string;
  tool_count: number;
}

export interface BackendCreate {
  name: string;
  url: string;
  prefix?: string;
  mount_enabled?: boolean;
  enabled?: boolean;
  timeout?: number;
}

export interface BackendUpdate {
  url?: string;
  prefix?: string;
  mount_enabled?: boolean;
  enabled?: boolean;
  timeout?: number;
}

export interface Tool {
  id: string;
  backend_name: string;
  name: string;
  prefixed_name: string;
  description: string | null;
  input_schema: Record<string, unknown>;
  refreshed_at: string;
}

export interface ToolCall {
  id: string;
  tool_id: string | null;
  backend_name: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  success: boolean;
  error_message: string | null;
  latency_ms: number;
  called_at: string;
  // Future: response data
}

export interface Metrics {
  total_calls: number;
  success_count: number;
  error_count: number;
  success_rate: number;
  avg_latency_ms: number;
  min_latency_ms: number;
  max_latency_ms: number;
}

export interface BackendListResponse {
  backends: Backend[];
  total: number;
}

export interface ToolListResponse {
  tools: Tool[];
  total: number;
}
```

---

## API Client

```typescript
// api/client.ts

const API_BASE = '/admin';

export const api = {
  // Backends
  async listBackends(): Promise<BackendListResponse> {
    const res = await fetch(`${API_BASE}/backends`);
    return res.json();
  },

  async createBackend(data: BackendCreate): Promise<Backend> {
    const res = await fetch(`${API_BASE}/backends`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return res.json();
  },

  async getBackend(name: string): Promise<Backend> {
    const res = await fetch(`${API_BASE}/backends/${name}`);
    return res.json();
  },

  async updateBackend(name: string, data: BackendUpdate): Promise<Backend> {
    const res = await fetch(`${API_BASE}/backends/${name}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return res.json();
  },

  async deleteBackend(name: string): Promise<void> {
    await fetch(`${API_BASE}/backends/${name}`, { method: 'DELETE' });
  },

  async refreshBackend(name: string): Promise<{ tools_count: number }> {
    const res = await fetch(`${API_BASE}/backends/${name}/refresh`, {
      method: 'POST',
    });
    return res.json();
  },

  async enableBackend(name: string): Promise<Backend> {
    const res = await fetch(`${API_BASE}/backends/${name}/enable`, {
      method: 'POST',
    });
    return res.json();
  },

  async disableBackend(name: string): Promise<Backend> {
    const res = await fetch(`${API_BASE}/backends/${name}/disable`, {
      method: 'POST',
    });
    return res.json();
  },

  // Tools
  async listTools(): Promise<ToolListResponse> {
    const res = await fetch(`${API_BASE}/tools`);
    return res.json();
  },

  // Metrics
  async getMetrics(backend?: string): Promise<Metrics> {
    const url = backend
      ? `${API_BASE}/metrics?backend=${backend}`
      : `${API_BASE}/metrics`;
    const res = await fetch(url);
    return res.json();
  },

  // Future: Tool calls history
  async listCalls(limit?: number): Promise<ToolCall[]> {
    const url = limit
      ? `${API_BASE}/calls?limit=${limit}`
      : `${API_BASE}/calls`;
    const res = await fetch(url);
    return res.json();
  },
};
```

---

## Backend Changes Required

### 1. Serve Static Files

Update `server.py` to serve the built Vue.js app:

```python
from fastapi.staticfiles import StaticFiles

# Mount static files for admin UI
app.mount("/ui", StaticFiles(directory="admin-ui/dist", html=True), name="ui")
```

### 2. Add Tool Calls Endpoint (Future)

```python
# In admin/routes.py

async def list_calls(request: Request) -> JSONResponse:
    """List recent tool calls.

    GET /admin/calls?limit=50&backend=weather
    """
    limit = int(request.query_params.get("limit", 50))
    backend = request.query_params.get("backend")

    async with session_maker() as session:
        repo = ToolCallRepository(session)
        calls = await repo.list_recent(backend_name=backend, limit=limit)

    return _json_response({
        "calls": [
            {
                "id": str(c.id),
                "tool_id": str(c.tool_id) if c.tool_id else None,
                "backend_name": c.backend_name,
                "tool_name": c.tool_name,
                "arguments": c.arguments,
                "success": c.success,
                "error_message": c.error_message,
                "latency_ms": c.latency_ms,
                "called_at": c.called_at.isoformat(),
            }
            for c in calls
        ],
        "total": len(calls),
    })
```

---

## Implementation Phases

### Phase 1: Project Setup & Layout
- [ ] Initialize Vue.js + Vite + TypeScript project in `admin-ui/`
- [ ] Configure Tailwind CSS
- [ ] Set up Vue Router with basic routes
- [ ] Create layout components (Sidebar, Header)
- [ ] Configure Vite proxy for development (`/admin` → backend)
- [ ] Create API client (`api/client.ts`)

### Phase 2: Backends Management
- [ ] Implement BackendsView with list
- [ ] Add BackendCard component
- [ ] Implement Add Backend modal/form
- [ ] Enable/Disable toggle
- [ ] Refresh tools action
- [ ] Delete confirmation

### Phase 3: Tools View
- [ ] Implement ToolsView with list
- [ ] Create ToolCard component
- [ ] Add search/filter functionality
- [ ] Group by backend option
- [ ] Basic metrics overview on dashboard

### Future Phases (Post-MVP)
- Tool call history with `/admin/calls` endpoint
- Tool testing interface
- Dark mode

---

## Development Workflow

### Setup

```bash
cd forge-armory/admin-ui

# Install dependencies
bun install

# Start dev server (with proxy to backend)
bun run dev
```

### Build

```bash
# Build for production
bun run build

# Output in admin-ui/dist/
```

### Running with Backend

```bash
# Terminal 1: Start Armory backend
armory serve --port 8080

# Terminal 2: Start UI dev server
cd admin-ui && bun run dev

# Or after building, access at http://localhost:8080/ui/
```

---

## Vite Configuration

```typescript
// vite.config.ts
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  base: '/ui/',
  server: {
    port: 3000,
    proxy: {
      '/admin': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
  },
})
```

---

## Commands Reference

```bash
# Development
cd admin-ui
bun install              # Install dependencies
bun run dev              # Start dev server at :3000
bun run build            # Build for production
bun run preview          # Preview production build

# With backend
armory serve             # Start backend at :8080
# Access UI at http://localhost:8080/ui/ (after build)
```

---

## Future Enhancements (Post-MVP)

1. **Tool Call History** - View past tool calls with arguments and responses
2. **Tool Testing Interface** - Execute tools directly from UI with JSON input
3. **Real-time Updates** - WebSocket for live call feed
4. **Backend Health Checks** - Periodic ping with status indicator
5. **Import/Export** - Backup and restore backend configurations

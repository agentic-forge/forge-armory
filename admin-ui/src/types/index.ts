export interface Backend {
  id: string
  name: string
  url: string | null
  enabled: boolean
  timeout: number
  prefix: string | null
  mount_enabled: boolean
  effective_prefix: string
  created_at: string
  updated_at: string
  tool_count: number
}

export interface BackendCreate {
  name: string
  url: string
  prefix?: string
  mount_enabled?: boolean
  enabled?: boolean
  timeout?: number
}

export interface BackendUpdate {
  url?: string
  prefix?: string
  mount_enabled?: boolean
  enabled?: boolean
  timeout?: number
}

export interface Tool {
  id: string
  backend_name: string
  name: string
  prefixed_name: string
  description: string | null
  input_schema: Record<string, unknown>
  refreshed_at: string
}

export interface ToolCall {
  id: string
  tool_id: string | null
  backend_name: string
  tool_name: string
  arguments: Record<string, unknown>
  success: boolean
  error_message: string | null
  latency_ms: number
  called_at: string
}

export interface Metrics {
  total_calls: number
  success_count: number
  error_count: number
  success_rate: number
  avg_latency_ms: number
  min_latency_ms: number
  max_latency_ms: number
}

export interface BackendListResponse {
  backends: Backend[]
  total: number
}

export interface ToolListResponse {
  tools: Tool[]
  total: number
}

export interface RefreshResponse {
  backend_name: string
  tools_count: number
  tools: string[]
}

export interface MessageResponse {
  message: string
}

export interface ErrorResponse {
  error: string
  detail?: string
}

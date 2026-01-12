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
  // Request context fields
  client_ip: string | null
  request_id: string | null
  session_id: string | null
  caller: string | null
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

export interface EnhancedMetrics extends Metrics {
  p50_latency_ms: number | null
  p95_latency_ms: number | null
  p99_latency_ms: number | null
}

export interface ToolCallListResponse {
  calls: ToolCall[]
  total: number
  limit: number
  offset: number
}

export interface ToolMetrics {
  tool_name: string
  backend_name: string
  total_calls: number
  success_count: number
  error_count: number
  success_rate: number
  avg_latency_ms: number
  min_latency_ms: number
  max_latency_ms: number
  p95_latency_ms: number | null
  last_called_at: string | null
}

export interface ToolMetricsListResponse {
  tools: ToolMetrics[]
  total: number
}

export interface TimeSeriesPoint {
  timestamp: string
  total_calls: number
  success_count: number
  error_count: number
  avg_latency_ms: number
}

export interface TimeSeriesResponse {
  period: string
  granularity: string
  data: TimeSeriesPoint[]
}

export type TimePeriod = '1h' | '24h' | '7d' | '30d' | 'all'

export interface MetricsParams {
  backend?: string
  tool?: string
  period?: TimePeriod
}

export interface ToolCallsParams {
  backend?: string
  tool?: string
  success?: boolean
  period?: TimePeriod
  limit?: number
  offset?: number
}

export interface ToolMetricsParams {
  backend?: string
  period?: TimePeriod
  order_by?: 'total_calls' | 'error_count' | 'avg_latency_ms' | 'p95_latency_ms'
  order?: 'asc' | 'desc'
  limit?: number
}

export interface TimeSeriesParams {
  period: TimePeriod
  backend?: string
  tool?: string
  granularity?: 'minute' | 'hour' | 'day'
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

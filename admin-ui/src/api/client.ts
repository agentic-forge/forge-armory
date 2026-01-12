import type {
  Backend,
  BackendCreate,
  BackendListResponse,
  BackendUpdate,
  EnhancedMetrics,
  Metrics,
  MetricsParams,
  RefreshResponse,
  TimeSeriesParams,
  TimeSeriesResponse,
  ToolCallListResponse,
  ToolCallsParams,
  ToolListResponse,
  ToolMetricsListResponse,
  ToolMetricsParams,
} from '@/types'

const API_BASE = '/admin'

class ApiError extends Error {
  status: number
  statusText: string
  detail?: string

  constructor(status: number, statusText: string, detail?: string) {
    super(detail || statusText)
    this.name = 'ApiError'
    this.status = status
    this.statusText = statusText
    this.detail = detail
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail: string | undefined
    try {
      const data = await response.json()
      detail = data.detail || data.error
    } catch {
      // Ignore JSON parse errors
    }
    throw new ApiError(response.status, response.statusText, detail)
  }
  return response.json()
}

export const api = {
  // Backends
  async listBackends(): Promise<BackendListResponse> {
    const res = await fetch(`${API_BASE}/backends`)
    return handleResponse(res)
  },

  async createBackend(data: BackendCreate): Promise<Backend> {
    const res = await fetch(`${API_BASE}/backends`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    return handleResponse(res)
  },

  async getBackend(name: string): Promise<Backend> {
    const res = await fetch(`${API_BASE}/backends/${encodeURIComponent(name)}`)
    return handleResponse(res)
  },

  async updateBackend(name: string, data: BackendUpdate): Promise<Backend> {
    const res = await fetch(`${API_BASE}/backends/${encodeURIComponent(name)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    return handleResponse(res)
  },

  async deleteBackend(name: string): Promise<void> {
    const res = await fetch(`${API_BASE}/backends/${encodeURIComponent(name)}`, {
      method: 'DELETE',
    })
    if (!res.ok) {
      let detail: string | undefined
      try {
        const data = await res.json()
        detail = data.detail || data.error
      } catch {
        // Ignore
      }
      throw new ApiError(res.status, res.statusText, detail)
    }
  },

  async refreshBackend(name: string): Promise<RefreshResponse> {
    const res = await fetch(
      `${API_BASE}/backends/${encodeURIComponent(name)}/refresh`,
      { method: 'POST' }
    )
    return handleResponse(res)
  },

  async enableBackend(name: string): Promise<Backend> {
    const res = await fetch(
      `${API_BASE}/backends/${encodeURIComponent(name)}/enable`,
      { method: 'POST' }
    )
    return handleResponse(res)
  },

  async disableBackend(name: string): Promise<Backend> {
    const res = await fetch(
      `${API_BASE}/backends/${encodeURIComponent(name)}/disable`,
      { method: 'POST' }
    )
    return handleResponse(res)
  },

  // Tools
  async listTools(): Promise<ToolListResponse> {
    const res = await fetch(`${API_BASE}/tools`)
    return handleResponse(res)
  },

  // Metrics
  async getMetrics(backend?: string): Promise<Metrics> {
    const url = backend
      ? `${API_BASE}/metrics?backend=${encodeURIComponent(backend)}`
      : `${API_BASE}/metrics`
    const res = await fetch(url)
    return handleResponse(res)
  },

  async getEnhancedMetrics(params?: MetricsParams): Promise<EnhancedMetrics> {
    const searchParams = new URLSearchParams()
    if (params?.backend) searchParams.set('backend', params.backend)
    if (params?.tool) searchParams.set('tool', params.tool)
    if (params?.period) searchParams.set('period', params.period)
    const query = searchParams.toString()
    const url = `${API_BASE}/metrics/enhanced${query ? '?' + query : ''}`
    const res = await fetch(url)
    return handleResponse(res)
  },

  async listToolCalls(params?: ToolCallsParams): Promise<ToolCallListResponse> {
    const searchParams = new URLSearchParams()
    if (params?.backend) searchParams.set('backend', params.backend)
    if (params?.tool) searchParams.set('tool', params.tool)
    if (params?.success !== undefined) searchParams.set('success', String(params.success))
    if (params?.period) searchParams.set('period', params.period)
    if (params?.limit !== undefined) searchParams.set('limit', String(params.limit))
    if (params?.offset !== undefined) searchParams.set('offset', String(params.offset))
    const query = searchParams.toString()
    const url = `${API_BASE}/metrics/calls${query ? '?' + query : ''}`
    const res = await fetch(url)
    return handleResponse(res)
  },

  async getToolMetrics(params?: ToolMetricsParams): Promise<ToolMetricsListResponse> {
    const searchParams = new URLSearchParams()
    if (params?.backend) searchParams.set('backend', params.backend)
    if (params?.period) searchParams.set('period', params.period)
    if (params?.order_by) searchParams.set('order_by', params.order_by)
    if (params?.order) searchParams.set('order', params.order)
    if (params?.limit !== undefined) searchParams.set('limit', String(params.limit))
    const query = searchParams.toString()
    const url = `${API_BASE}/metrics/by-tool${query ? '?' + query : ''}`
    const res = await fetch(url)
    return handleResponse(res)
  },

  async getTimeSeries(params: TimeSeriesParams): Promise<TimeSeriesResponse> {
    const searchParams = new URLSearchParams()
    searchParams.set('period', params.period)
    if (params.backend) searchParams.set('backend', params.backend)
    if (params.tool) searchParams.set('tool', params.tool)
    if (params.granularity) searchParams.set('granularity', params.granularity)
    const url = `${API_BASE}/metrics/timeseries?${searchParams.toString()}`
    const res = await fetch(url)
    return handleResponse(res)
  },
}

export { ApiError }

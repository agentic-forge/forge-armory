<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useToast } from 'primevue/usetoast'
import Card from 'primevue/card'
import Select from 'primevue/select'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import ProgressSpinner from 'primevue/progressspinner'
import Tag from 'primevue/tag'
import TabView from 'primevue/tabview'
import TabPanel from 'primevue/tabpanel'
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import TimePeriodSelector from '@/components/metrics/TimePeriodSelector.vue'
import { api } from '@/api/client'
import type {
  Backend,
  EnhancedMetrics,
  TimePeriod,
  ToolCall,
  ToolMetrics,
  TimeSeriesPoint,
} from '@/types'

const toast = useToast()

// Shared state
const backends = ref<Backend[]>([])
const selectedBackend = ref<string | null>(null)
const selectedPeriod = ref<TimePeriod>('24h')

// Overview tab state
const overviewLoading = ref(true)
const metrics = ref<EnhancedMetrics | null>(null)
const backendMetrics = ref<Array<{ backend: Backend; metrics: EnhancedMetrics }>>([])

// Tool Calls tab state
const callsLoading = ref(false)
const toolCalls = ref<ToolCall[]>([])
const toolCallsTotal = ref(0)
const callsOffset = ref(0)
const callsLimit = ref(20)
const callsStatusFilter = ref<boolean | null>(null)
const callsToolFilter = ref('')
const expandedRows = ref<Record<string, boolean>>({})

// By Tool tab state
const toolMetricsLoading = ref(false)
const toolMetricsList = ref<ToolMetrics[]>([])

// Trends tab state
const trendsLoading = ref(false)
const timeseriesData = ref<TimeSeriesPoint[]>([])

// Active tab tracking
const activeTab = ref(0)

async function loadBackends() {
  try {
    const res = await api.listBackends()
    backends.value = res.backends
  } catch {
    // Ignore
  }
}

async function loadOverview() {
  overviewLoading.value = true
  try {
    const metricsRes = await api.getEnhancedMetrics({
      backend: selectedBackend.value || undefined,
      period: selectedPeriod.value,
    })
    metrics.value = metricsRes

    // Load metrics for each backend
    const metricsPromises = backends.value.map(async (backend) => {
      try {
        const m = await api.getEnhancedMetrics({
          backend: backend.name,
          period: selectedPeriod.value,
        })
        return { backend, metrics: m }
      } catch {
        return {
          backend,
          metrics: {
            total_calls: 0,
            success_count: 0,
            error_count: 0,
            success_rate: 0,
            avg_latency_ms: 0,
            min_latency_ms: 0,
            max_latency_ms: 0,
            p50_latency_ms: null,
            p95_latency_ms: null,
            p99_latency_ms: null,
          },
        }
      }
    })
    backendMetrics.value = await Promise.all(metricsPromises)
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Error',
      detail: 'Failed to load metrics',
      life: 3000,
    })
  } finally {
    overviewLoading.value = false
  }
}

async function loadToolCalls() {
  callsLoading.value = true
  try {
    const res = await api.listToolCalls({
      backend: selectedBackend.value || undefined,
      tool: callsToolFilter.value || undefined,
      success: callsStatusFilter.value ?? undefined,
      period: selectedPeriod.value,
      limit: callsLimit.value,
      offset: callsOffset.value,
    })
    toolCalls.value = res.calls
    toolCallsTotal.value = res.total
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Error',
      detail: 'Failed to load tool calls',
      life: 3000,
    })
  } finally {
    callsLoading.value = false
  }
}

async function loadToolMetrics() {
  toolMetricsLoading.value = true
  try {
    const res = await api.getToolMetrics({
      backend: selectedBackend.value || undefined,
      period: selectedPeriod.value,
      order_by: 'total_calls',
      order: 'desc',
      limit: 100,
    })
    toolMetricsList.value = res.tools
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Error',
      detail: 'Failed to load tool metrics',
      life: 3000,
    })
  } finally {
    toolMetricsLoading.value = false
  }
}

async function loadTrends() {
  trendsLoading.value = true
  try {
    const res = await api.getTimeSeries({
      period: selectedPeriod.value,
      backend: selectedBackend.value || undefined,
    })
    timeseriesData.value = res.data
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Error',
      detail: 'Failed to load trends',
      life: 3000,
    })
  } finally {
    trendsLoading.value = false
  }
}

function onTabChange(event: { index: number }) {
  activeTab.value = event.index
  loadActiveTabData()
}

function loadActiveTabData() {
  switch (activeTab.value) {
    case 0:
      loadOverview()
      break
    case 1:
      loadToolCalls()
      break
    case 2:
      loadToolMetrics()
      break
    case 3:
      loadTrends()
      break
  }
}

function onPage(event: { first: number; rows: number }) {
  callsOffset.value = event.first
  callsLimit.value = event.rows
  loadToolCalls()
}

function formatSuccessRate(rate: number): string {
  return `${(rate * 100).toFixed(1)}%`
}

function getSeverity(rate: number): 'success' | 'warn' | 'danger' {
  if (rate >= 0.95) return 'success'
  if (rate >= 0.8) return 'warn'
  return 'danger'
}

function getLatencyClass(latency: number): string {
  if (latency < 100) return 'latency-fast'
  if (latency < 500) return 'latency-normal'
  if (latency < 1000) return 'latency-slow'
  return 'latency-very-slow'
}

function parseUTCDate(dateStr: string): Date {
  // Server returns naive UTC timestamps (without 'Z' suffix)
  // Append 'Z' if no timezone info to ensure JS treats it as UTC
  if (!dateStr.endsWith('Z') && !dateStr.includes('+') && !dateStr.includes('-', 10)) {
    return new Date(dateStr + 'Z')
  }
  return new Date(dateStr)
}

function formatRelativeTime(dateStr: string): string {
  const date = parseUTCDate(dateStr)
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  const seconds = Math.floor(diff / 1000)
  const minutes = Math.floor(seconds / 60)
  const hours = Math.floor(minutes / 60)
  const days = Math.floor(hours / 24)

  if (seconds < 60) return `${seconds}s ago`
  if (minutes < 60) return `${minutes}m ago`
  if (hours < 24) return `${hours}h ago`
  return `${days}d ago`
}

function formatAbsoluteTime(dateStr: string): string {
  return parseUTCDate(dateStr).toLocaleString()
}

function formatJson(obj: Record<string, unknown>): string {
  return JSON.stringify(obj, null, 2)
}

// Watch for filter changes
watch([selectedBackend, selectedPeriod], () => {
  loadActiveTabData()
})

watch([callsStatusFilter, callsToolFilter], () => {
  callsOffset.value = 0
  if (activeTab.value === 1) {
    loadToolCalls()
  }
})

onMounted(async () => {
  await loadBackends()
  loadOverview()
})
</script>

<template>
  <div class="page-header">
    <h2 class="page-title">Metrics</h2>
    <div class="header-controls">
      <TimePeriodSelector v-model="selectedPeriod" />
      <Select
        v-model="selectedBackend"
        :options="[
          { label: 'All Backends', value: null },
          ...backends.map((b) => ({ label: b.name, value: b.name })),
        ]"
        optionLabel="label"
        optionValue="value"
        placeholder="Filter by backend"
        style="min-width: 180px"
      />
    </div>
  </div>

  <TabView @tab-change="onTabChange">
    <!-- Overview Tab -->
    <TabPanel header="Overview">
      <div v-if="overviewLoading" class="loading-overlay">
        <ProgressSpinner />
      </div>
      <div v-else>
        <!-- Overview Stats -->
        <div class="stats-grid">
          <Card class="stat-card">
            <template #content>
              <div class="stat-label">Total Calls</div>
              <div class="stat-value">{{ metrics?.total_calls ?? 0 }}</div>
            </template>
          </Card>

          <Card class="stat-card">
            <template #content>
              <div class="stat-label">Success Rate</div>
              <div class="stat-value">
                {{ formatSuccessRate(metrics?.success_rate ?? 0) }}
              </div>
              <div class="stat-detail">
                {{ metrics?.success_count ?? 0 }} success /
                {{ metrics?.error_count ?? 0 }} errors
              </div>
            </template>
          </Card>

          <Card class="stat-card">
            <template #content>
              <div class="stat-label">Avg Latency</div>
              <div class="stat-value">
                {{ metrics?.avg_latency_ms?.toFixed(0) ?? 0 }}ms
              </div>
              <div class="stat-detail">
                min {{ metrics?.min_latency_ms ?? 0 }}ms / max
                {{ metrics?.max_latency_ms ?? 0 }}ms
              </div>
            </template>
          </Card>

          <Card class="stat-card">
            <template #content>
              <div class="stat-label">P95 Latency</div>
              <div class="stat-value">
                {{ metrics?.p95_latency_ms ?? '-' }}{{ metrics?.p95_latency_ms ? 'ms' : '' }}
              </div>
              <div class="stat-detail">
                P50: {{ metrics?.p50_latency_ms ?? '-' }}ms /
                P99: {{ metrics?.p99_latency_ms ?? '-' }}ms
              </div>
            </template>
          </Card>
        </div>

        <!-- Per-Backend Metrics Table -->
        <Card style="margin-top: 1.5rem">
          <template #title>By Backend</template>
          <template #content>
            <DataTable
              :value="backendMetrics"
              :paginator="backendMetrics.length > 10"
              :rows="10"
              stripedRows
            >
              <Column field="backend.name" header="Backend" sortable>
                <template #body="{ data }">
                  <div style="display: flex; align-items: center; gap: 0.5rem">
                    <span
                      class="backend-status-indicator"
                      :class="data.backend.enabled ? 'enabled' : 'disabled'"
                    ></span>
                    {{ data.backend.name }}
                  </div>
                </template>
              </Column>
              <Column field="metrics.total_calls" header="Calls" sortable />
              <Column field="metrics.success_count" header="Success" sortable />
              <Column field="metrics.error_count" header="Errors" sortable>
                <template #body="{ data }">
                  <span :style="data.metrics.error_count > 0 ? 'color: var(--p-red-500)' : ''">
                    {{ data.metrics.error_count }}
                  </span>
                </template>
              </Column>
              <Column field="metrics.success_rate" header="Success Rate" sortable>
                <template #body="{ data }">
                  <Tag
                    :value="formatSuccessRate(data.metrics.success_rate)"
                    :severity="getSeverity(data.metrics.success_rate)"
                  />
                </template>
              </Column>
              <Column field="metrics.avg_latency_ms" header="Avg Latency" sortable>
                <template #body="{ data }">
                  {{ data.metrics.avg_latency_ms?.toFixed(0) ?? 0 }}ms
                </template>
              </Column>
              <Column field="metrics.p95_latency_ms" header="P95" sortable>
                <template #body="{ data }">
                  {{ data.metrics.p95_latency_ms ?? '-' }}{{ data.metrics.p95_latency_ms ? 'ms' : '' }}
                </template>
              </Column>
            </DataTable>
          </template>
        </Card>
      </div>
    </TabPanel>

    <!-- Tool Calls Tab -->
    <TabPanel header="Tool Calls">
      <div class="filter-bar">
        <span class="p-input-icon-left search-input">
          <i class="pi pi-search" />
          <InputText
            v-model="callsToolFilter"
            placeholder="Filter by tool name..."
            style="width: 100%"
          />
        </span>
        <Select
          v-model="callsStatusFilter"
          :options="[
            { label: 'All Status', value: null },
            { label: 'Success', value: true },
            { label: 'Failed', value: false },
          ]"
          optionLabel="label"
          optionValue="value"
          placeholder="Status"
          style="min-width: 140px"
        />
        <Button
          icon="pi pi-refresh"
          :loading="callsLoading"
          @click="loadToolCalls"
          severity="secondary"
        />
      </div>

      <div v-if="callsLoading && toolCalls.length === 0" class="loading-overlay">
        <ProgressSpinner />
      </div>

      <DataTable
        v-else
        v-model:expandedRows="expandedRows"
        :value="toolCalls"
        :paginator="true"
        :rows="callsLimit"
        :totalRecords="toolCallsTotal"
        :lazy="true"
        :loading="callsLoading"
        @page="onPage"
        stripedRows
        dataKey="id"
      >
        <Column expander style="width: 3rem" />
        <Column field="called_at" header="Time" sortable style="width: 120px">
          <template #body="{ data }">
            <span v-tooltip="formatAbsoluteTime(data.called_at)">
              {{ formatRelativeTime(data.called_at) }}
            </span>
          </template>
        </Column>
        <Column field="tool_name" header="Tool" sortable>
          <template #body="{ data }">
            <code>{{ data.tool_name }}</code>
          </template>
        </Column>
        <Column field="backend_name" header="Backend" sortable style="width: 140px" />
        <Column field="success" header="Status" style="width: 100px">
          <template #body="{ data }">
            <Tag
              :value="data.success ? 'Success' : 'Failed'"
              :severity="data.success ? 'success' : 'danger'"
            />
          </template>
        </Column>
        <Column field="latency_ms" header="Latency" sortable style="width: 100px">
          <template #body="{ data }">
            <span :class="getLatencyClass(data.latency_ms)">
              {{ data.latency_ms }}ms
            </span>
          </template>
        </Column>
        <Column field="client_ip" header="Client IP" style="width: 130px">
          <template #body="{ data }">
            <code v-if="data.client_ip" class="client-ip">{{ data.client_ip }}</code>
            <span v-else class="text-muted">-</span>
          </template>
        </Column>
        <template #expansion="{ data }">
          <div class="call-details">
            <div class="detail-row">
              <div class="detail-section">
                <h4>Request Context</h4>
                <div class="context-grid">
                  <div class="context-item">
                    <span class="context-label">Request ID:</span>
                    <code v-if="data.request_id">{{ data.request_id }}</code>
                    <span v-else class="text-muted">-</span>
                  </div>
                  <div class="context-item">
                    <span class="context-label">Client IP:</span>
                    <code v-if="data.client_ip">{{ data.client_ip }}</code>
                    <span v-else class="text-muted">-</span>
                  </div>
                  <div class="context-item">
                    <span class="context-label">Session ID:</span>
                    <code v-if="data.session_id">{{ data.session_id }}</code>
                    <span v-else class="text-muted">-</span>
                  </div>
                  <div class="context-item">
                    <span class="context-label">Caller:</span>
                    <code v-if="data.caller">{{ data.caller }}</code>
                    <span v-else class="text-muted">-</span>
                  </div>
                </div>
              </div>
            </div>
            <div class="detail-section">
              <h4>Arguments</h4>
              <pre>{{ formatJson(data.arguments) }}</pre>
            </div>
            <div v-if="data.error_message" class="detail-section error">
              <h4>Error</h4>
              <p>{{ data.error_message }}</p>
            </div>
          </div>
        </template>
        <template #empty>
          <div class="empty-state">
            <i class="pi pi-inbox empty-state-icon"></i>
            <div class="empty-state-title">No tool calls found</div>
            <div class="empty-state-description">
              No tool calls match the current filters.
            </div>
          </div>
        </template>
      </DataTable>
    </TabPanel>

    <!-- By Tool Tab -->
    <TabPanel header="By Tool">
      <div v-if="toolMetricsLoading" class="loading-overlay">
        <ProgressSpinner />
      </div>
      <DataTable
        v-else
        :value="toolMetricsList"
        :paginator="toolMetricsList.length > 20"
        :rows="20"
        stripedRows
        sortField="total_calls"
        :sortOrder="-1"
      >
        <Column field="tool_name" header="Tool" sortable>
          <template #body="{ data }">
            <code>{{ data.tool_name }}</code>
          </template>
        </Column>
        <Column field="backend_name" header="Backend" sortable style="width: 140px" />
        <Column field="total_calls" header="Calls" sortable style="width: 100px" />
        <Column field="error_count" header="Errors" sortable style="width: 100px">
          <template #body="{ data }">
            <span :style="data.error_count > 0 ? 'color: var(--p-red-500)' : ''">
              {{ data.error_count }}
            </span>
          </template>
        </Column>
        <Column field="success_rate" header="Success Rate" sortable style="width: 120px">
          <template #body="{ data }">
            <Tag
              :value="formatSuccessRate(data.success_rate)"
              :severity="getSeverity(data.success_rate)"
            />
          </template>
        </Column>
        <Column field="avg_latency_ms" header="Avg Latency" sortable style="width: 120px">
          <template #body="{ data }">
            {{ data.avg_latency_ms?.toFixed(0) ?? 0 }}ms
          </template>
        </Column>
        <Column field="p95_latency_ms" header="P95" sortable style="width: 100px">
          <template #body="{ data }">
            {{ data.p95_latency_ms ?? '-' }}{{ data.p95_latency_ms ? 'ms' : '' }}
          </template>
        </Column>
        <Column field="last_called_at" header="Last Called" sortable style="width: 120px">
          <template #body="{ data }">
            <span v-if="data.last_called_at" v-tooltip="formatAbsoluteTime(data.last_called_at)">
              {{ formatRelativeTime(data.last_called_at) }}
            </span>
            <span v-else>-</span>
          </template>
        </Column>
        <template #empty>
          <div class="empty-state">
            <i class="pi pi-inbox empty-state-icon"></i>
            <div class="empty-state-title">No tool metrics</div>
            <div class="empty-state-description">
              No tools have been called yet.
            </div>
          </div>
        </template>
      </DataTable>
    </TabPanel>

    <!-- Trends Tab -->
    <TabPanel header="Trends">
      <div v-if="trendsLoading" class="loading-overlay">
        <ProgressSpinner />
      </div>
      <div v-else-if="timeseriesData.length === 0" class="empty-state">
        <i class="pi pi-chart-line empty-state-icon"></i>
        <div class="empty-state-title">No trend data</div>
        <div class="empty-state-description">
          No tool calls in the selected time period.
        </div>
      </div>
      <div v-else class="trends-container">
        <Card>
          <template #title>Call Volume Over Time</template>
          <template #content>
            <DataTable :value="timeseriesData" stripedRows>
              <Column field="timestamp" header="Time">
                <template #body="{ data }">
                  {{ formatAbsoluteTime(data.timestamp) }}
                </template>
              </Column>
              <Column field="total_calls" header="Total Calls" />
              <Column field="success_count" header="Success" />
              <Column field="error_count" header="Errors">
                <template #body="{ data }">
                  <span :style="data.error_count > 0 ? 'color: var(--p-red-500)' : ''">
                    {{ data.error_count }}
                  </span>
                </template>
              </Column>
              <Column field="avg_latency_ms" header="Avg Latency">
                <template #body="{ data }">
                  {{ data.avg_latency_ms?.toFixed(0) ?? 0 }}ms
                </template>
              </Column>
            </DataTable>
          </template>
        </Card>
      </div>
    </TabPanel>
  </TabView>
</template>

<style scoped>
.header-controls {
  display: flex;
  gap: var(--spacing-md);
  align-items: center;
}

/* Latency indicators */
.latency-fast {
  color: var(--p-green-500);
}
.latency-normal {
  color: var(--p-text-color);
}
.latency-slow {
  color: var(--p-yellow-500);
}
.latency-very-slow {
  color: var(--p-red-500);
}

/* Call details expansion */
.call-details {
  padding: var(--spacing-lg);
  background-color: var(--p-surface-ground);
  border-radius: var(--border-radius);
  margin: var(--spacing-sm) 0;
}

.call-details .detail-section {
  margin-bottom: var(--spacing-md);
}

.call-details .detail-section:last-child {
  margin-bottom: 0;
}

.call-details .detail-section h4 {
  font-size: 0.875rem;
  color: var(--p-text-muted-color);
  margin-bottom: var(--spacing-sm);
  font-weight: 600;
}

.call-details .detail-section.error {
  color: var(--p-red-500);
}

.call-details .detail-section.error h4 {
  color: var(--p-red-400);
}

.call-details pre {
  padding: var(--spacing-md);
  background: var(--p-surface-card);
  border-radius: var(--border-radius);
  overflow-x: auto;
  font-size: 0.875rem;
  border: 1px solid var(--p-surface-border);
  margin: 0;
}

code {
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size: 0.875rem;
}

.client-ip {
  font-size: 0.8rem;
  background: var(--p-surface-ground);
  padding: 0.125rem 0.375rem;
  border-radius: 4px;
}

.text-muted {
  color: var(--p-text-muted-color);
}

/* Request context display */
.detail-row {
  margin-bottom: var(--spacing-md);
}

.context-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--spacing-md);
}

.context-item {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.context-label {
  font-size: 0.75rem;
  color: var(--p-text-muted-color);
  font-weight: 500;
}

.context-item code {
  font-size: 0.8rem;
  background: var(--p-surface-card);
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  border: 1px solid var(--p-surface-border);
}

.trends-container {
  margin-top: var(--spacing-md);
}

/* Adjust empty state for tabs */
.empty-state {
  padding: 3rem;
}
</style>

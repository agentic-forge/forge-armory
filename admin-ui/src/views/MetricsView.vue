<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useToast } from 'primevue/usetoast'
import Card from 'primevue/card'
import Select from 'primevue/select'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import ProgressSpinner from 'primevue/progressspinner'
import Tag from 'primevue/tag'
import { api } from '@/api/client'
import type { Backend, Metrics } from '@/types'

const toast = useToast()

const loading = ref(true)
const backends = ref<Backend[]>([])
const selectedBackend = ref<string | null>(null)
const metrics = ref<Metrics | null>(null)
const backendMetrics = ref<Array<{ backend: Backend; metrics: Metrics }>>([])

async function loadData() {
  loading.value = true
  try {
    const [backendsRes, metricsRes] = await Promise.all([
      api.listBackends(),
      api.getMetrics(),
    ])
    backends.value = backendsRes.backends
    metrics.value = metricsRes

    // Load metrics for each backend
    const metricsPromises = backends.value.map(async (backend) => {
      try {
        const m = await api.getMetrics(backend.name)
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
    loading.value = false
  }
}

async function filterByBackend() {
  loading.value = true
  try {
    metrics.value = await api.getMetrics(selectedBackend.value || undefined)
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Error',
      detail: 'Failed to load metrics',
      life: 3000,
    })
  } finally {
    loading.value = false
  }
}

function formatSuccessRate(rate: number): string {
  return `${(rate * 100).toFixed(1)}%`
}

function getSeverity(rate: number): 'success' | 'warn' | 'danger' {
  if (rate >= 0.95) return 'success'
  if (rate >= 0.8) return 'warn'
  return 'danger'
}

onMounted(loadData)
</script>

<template>
  <div class="page-header">
    <h2 class="page-title">Metrics</h2>
    <Select
      v-model="selectedBackend"
      :options="[
        { label: 'All Backends', value: null },
        ...backends.map((b) => ({ label: b.name, value: b.name })),
      ]"
      optionLabel="label"
      optionValue="value"
      placeholder="Filter by backend"
      @change="filterByBackend"
      style="min-width: 200px"
    />
  </div>

  <div v-if="loading" class="loading-overlay">
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
          <Column field="metrics.total_calls" header="Calls" sortable>
            <template #body="{ data }">
              {{ data.metrics.total_calls }}
            </template>
          </Column>
          <Column field="metrics.success_count" header="Success" sortable>
            <template #body="{ data }">
              {{ data.metrics.success_count }}
            </template>
          </Column>
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
        </DataTable>
      </template>
    </Card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import Card from 'primevue/card'
import Button from 'primevue/button'
import ProgressSpinner from 'primevue/progressspinner'
import { api } from '@/api/client'
import type { Backend, Tool, Metrics } from '@/types'

const router = useRouter()
const loading = ref(true)
const backends = ref<Backend[]>([])
const tools = ref<Tool[]>([])
const metrics = ref<Metrics | null>(null)

async function loadData() {
  loading.value = true
  try {
    const [backendsRes, toolsRes, metricsRes] = await Promise.all([
      api.listBackends(),
      api.listTools(),
      api.getMetrics(),
    ])
    backends.value = backendsRes.backends
    tools.value = toolsRes.tools
    metrics.value = metricsRes
  } catch (error) {
    console.error('Failed to load dashboard data:', error)
  } finally {
    loading.value = false
  }
}

const connectedBackends = () => backends.value.filter((b) => b.enabled).length

onMounted(loadData)
</script>

<template>
  <div v-if="loading" class="loading-overlay">
    <ProgressSpinner />
  </div>

  <div v-else>
    <div class="stats-grid">
      <Card class="stat-card">
        <template #content>
          <div class="stat-label">Backends</div>
          <div class="stat-value">{{ backends.length }}</div>
          <div class="stat-detail">{{ connectedBackends() }} enabled</div>
        </template>
      </Card>

      <Card class="stat-card">
        <template #content>
          <div class="stat-label">Tools</div>
          <div class="stat-value">{{ tools.length }}</div>
          <div class="stat-detail">from {{ backends.length }} backends</div>
        </template>
      </Card>

      <Card class="stat-card">
        <template #content>
          <div class="stat-label">Total Calls</div>
          <div class="stat-value">{{ metrics?.total_calls ?? 0 }}</div>
          <div class="stat-detail">
            {{ ((metrics?.success_rate ?? 0) * 100).toFixed(1) }}% success
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

    <div class="dashboard-sections">
      <Card>
        <template #title>
          <div
            style="
              display: flex;
              justify-content: space-between;
              align-items: center;
            "
          >
            <span>Recent Backends</span>
            <Button
              label="View All"
              severity="secondary"
              text
              size="small"
              @click="router.push('/backends')"
            />
          </div>
        </template>
        <template #content>
          <div v-if="backends.length === 0" class="empty-state">
            <i class="pi pi-server empty-state-icon"></i>
            <div class="empty-state-title">No backends configured</div>
            <div class="empty-state-description">
              Add a backend to start aggregating MCP tools
            </div>
            <Button
              label="Add Backend"
              icon="pi pi-plus"
              @click="router.push('/backends')"
            />
          </div>
          <div v-else class="backend-grid">
            <div
              v-for="backend in backends.slice(0, 3)"
              :key="backend.id"
              class="backend-card"
            >
              <div class="backend-header">
                <div class="backend-title">
                  <span
                    class="backend-status-indicator"
                    :class="backend.enabled ? 'enabled' : 'disabled'"
                  ></span>
                  <span class="backend-name">{{ backend.name }}</span>
                </div>
              </div>
              <div class="backend-details">
                <span class="backend-detail">
                  <i class="pi pi-link"></i>
                  {{ backend.url }}
                </span>
                <span class="backend-detail">
                  <i class="pi pi-wrench"></i>
                  {{ backend.tool_count }} tools
                </span>
              </div>
            </div>
          </div>
        </template>
      </Card>

      <Card style="margin-top: 1.5rem">
        <template #title>
          <div
            style="
              display: flex;
              justify-content: space-between;
              align-items: center;
            "
          >
            <span>Recent Tools</span>
            <Button
              label="View All"
              severity="secondary"
              text
              size="small"
              @click="router.push('/tools')"
            />
          </div>
        </template>
        <template #content>
          <div v-if="tools.length === 0" class="empty-state">
            <i class="pi pi-wrench empty-state-icon"></i>
            <div class="empty-state-title">No tools available</div>
            <div class="empty-state-description">
              Tools will appear after connecting backends
            </div>
          </div>
          <div v-else class="tool-grid">
            <div
              v-for="tool in tools.slice(0, 5)"
              :key="tool.id"
              class="tool-card"
            >
              <div class="tool-header">
                <span class="tool-name">{{ tool.prefixed_name }}</span>
              </div>
              <div class="tool-description">
                {{ tool.description || 'No description' }}
              </div>
              <div class="tool-meta">
                <span>Backend: {{ tool.backend_name }}</span>
              </div>
            </div>
          </div>
        </template>
      </Card>
    </div>
  </div>
</template>

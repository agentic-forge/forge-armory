<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useToast } from 'primevue/usetoast'
import InputText from 'primevue/inputtext'
import Select from 'primevue/select'
import ProgressSpinner from 'primevue/progressspinner'
import Tag from 'primevue/tag'
import Dialog from 'primevue/dialog'
import Button from 'primevue/button'
import { api } from '@/api/client'
import type { Tool, Backend } from '@/types'

const toast = useToast()

const loading = ref(true)
const tools = ref<Tool[]>([])
const backends = ref<Backend[]>([])
const searchQuery = ref('')
const selectedBackend = ref<string | null>(null)
const showSchemaDialog = ref(false)
const selectedTool = ref<Tool | null>(null)

async function loadData() {
  loading.value = true
  try {
    const [toolsRes, backendsRes] = await Promise.all([
      api.listTools(),
      api.listBackends(),
    ])
    tools.value = toolsRes.tools
    backends.value = backendsRes.backends
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Error',
      detail: 'Failed to load tools',
      life: 3000,
    })
  } finally {
    loading.value = false
  }
}

const backendOptions = computed(() => [
  { label: 'All Backends', value: null },
  ...backends.value.map((b) => ({ label: b.name, value: b.name })),
])

const filteredTools = computed(() => {
  let result = tools.value

  if (selectedBackend.value) {
    result = result.filter((t) => t.backend_name === selectedBackend.value)
  }

  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase()
    result = result.filter(
      (t) =>
        t.prefixed_name.toLowerCase().includes(query) ||
        t.description?.toLowerCase().includes(query)
    )
  }

  return result
})

function formatDate(dateStr: string) {
  const date = new Date(dateStr)
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  const minutes = Math.floor(diff / 60000)
  const hours = Math.floor(diff / 3600000)
  const days = Math.floor(diff / 86400000)

  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes} min ago`
  if (hours < 24) return `${hours} hour${hours > 1 ? 's' : ''} ago`
  return `${days} day${days > 1 ? 's' : ''} ago`
}

function showSchema(tool: Tool) {
  selectedTool.value = tool
  showSchemaDialog.value = true
}

function formatSchema(schema: Record<string, unknown>): string {
  return JSON.stringify(schema, null, 2)
}

onMounted(loadData)
</script>

<template>
  <div class="page-header">
    <h2 class="page-title">Tools</h2>
  </div>

  <div class="filter-bar">
    <span class="p-input-icon-left search-input">
      <i class="pi pi-search" style="left: 0.75rem; top: 50%; transform: translateY(-50%); position: absolute;" />
      <InputText
        v-model="searchQuery"
        placeholder="Search tools..."
        style="width: 100%; padding-left: 2.5rem;"
      />
    </span>
    <Select
      v-model="selectedBackend"
      :options="backendOptions"
      optionLabel="label"
      optionValue="value"
      placeholder="Filter by backend"
      style="min-width: 200px"
    />
  </div>

  <div v-if="loading" class="loading-overlay">
    <ProgressSpinner />
  </div>

  <div v-else-if="tools.length === 0" class="empty-state">
    <i class="pi pi-wrench empty-state-icon"></i>
    <div class="empty-state-title">No tools available</div>
    <div class="empty-state-description">
      Tools will appear after connecting and refreshing backends
    </div>
  </div>

  <div v-else-if="filteredTools.length === 0" class="empty-state">
    <i class="pi pi-search empty-state-icon"></i>
    <div class="empty-state-title">No matching tools</div>
    <div class="empty-state-description">
      Try adjusting your search or filter
    </div>
  </div>

  <div v-else class="tool-grid">
    <div v-for="tool in filteredTools" :key="tool.id" class="tool-card">
      <div class="tool-header">
        <span class="tool-name">{{ tool.prefixed_name }}</span>
        <Button
          icon="pi pi-code"
          severity="secondary"
          text
          rounded
          size="small"
          @click="showSchema(tool)"
          v-tooltip.top="'View schema'"
        />
      </div>
      <div class="tool-description">
        {{ tool.description || 'No description available' }}
      </div>
      <div class="tool-meta">
        <Tag :value="tool.backend_name" severity="info" />
        <span style="color: var(--p-text-muted-color)">
          Refreshed {{ formatDate(tool.refreshed_at) }}
        </span>
      </div>
    </div>
  </div>

  <div
    v-if="!loading && filteredTools.length > 0"
    style="margin-top: 1rem; color: var(--p-text-muted-color); font-size: 0.875rem"
  >
    Showing {{ filteredTools.length }} of {{ tools.length }} tools
  </div>

  <!-- Schema Dialog -->
  <Dialog
    v-model:visible="showSchemaDialog"
    :header="`Tool Schema: ${selectedTool?.prefixed_name}`"
    :style="{ width: '600px' }"
    :modal="true"
  >
    <div v-if="selectedTool">
      <div style="margin-bottom: 1rem">
        <strong>Description:</strong>
        <p style="margin-top: 0.5rem; color: var(--p-text-muted-color)">
          {{ selectedTool.description || 'No description' }}
        </p>
      </div>
      <div>
        <strong>Input Schema:</strong>
        <pre
          style="
            margin-top: 0.5rem;
            padding: 1rem;
            background: var(--p-surface-ground);
            border-radius: 8px;
            overflow-x: auto;
            font-size: 0.875rem;
          "
        >{{ formatSchema(selectedTool.input_schema) }}</pre>
      </div>
    </div>
  </Dialog>
</template>

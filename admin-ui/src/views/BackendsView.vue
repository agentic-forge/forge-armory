<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useToast } from 'primevue/usetoast'
import { useConfirm } from 'primevue/useconfirm'
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import InputNumber from 'primevue/inputnumber'
import Checkbox from 'primevue/checkbox'
import ProgressSpinner from 'primevue/progressspinner'
import Tag from 'primevue/tag'
import { api, ApiError } from '@/api/client'
import type { Backend, BackendCreate } from '@/types'

const toast = useToast()
const confirm = useConfirm()

const loading = ref(true)
const backends = ref<Backend[]>([])
const showAddDialog = ref(false)
const showEditDialog = ref(false)
const saving = ref(false)
const refreshingBackend = ref<string | null>(null)

const newBackend = ref<BackendCreate>({
  name: '',
  url: '',
  prefix: '',
  mount_enabled: true,
  enabled: true,
  timeout: 30,
})

const editingBackend = ref<Backend | null>(null)
const editForm = ref({
  url: '',
  prefix: '',
  mount_enabled: true,
  timeout: 30,
})

async function loadBackends() {
  loading.value = true
  try {
    const response = await api.listBackends()
    backends.value = response.backends
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Error',
      detail: 'Failed to load backends',
      life: 3000,
    })
  } finally {
    loading.value = false
  }
}

function openAddDialog() {
  newBackend.value = {
    name: '',
    url: '',
    prefix: '',
    mount_enabled: true,
    enabled: true,
    timeout: 30,
  }
  showAddDialog.value = true
}

async function createBackend() {
  saving.value = true
  try {
    const data: BackendCreate = {
      name: newBackend.value.name,
      url: newBackend.value.url,
      enabled: newBackend.value.enabled,
      timeout: newBackend.value.timeout,
      mount_enabled: newBackend.value.mount_enabled,
    }
    if (newBackend.value.prefix) {
      data.prefix = newBackend.value.prefix
    }
    await api.createBackend(data)
    toast.add({
      severity: 'success',
      summary: 'Success',
      detail: `Backend '${newBackend.value.name}' created`,
      life: 3000,
    })
    showAddDialog.value = false
    await loadBackends()
  } catch (error) {
    const message =
      error instanceof ApiError ? error.detail : 'Failed to create backend'
    toast.add({
      severity: 'error',
      summary: 'Error',
      detail: message,
      life: 5000,
    })
  } finally {
    saving.value = false
  }
}

function openEditDialog(backend: Backend) {
  editingBackend.value = backend
  editForm.value = {
    url: backend.url || '',
    prefix: backend.prefix || '',
    mount_enabled: backend.mount_enabled,
    timeout: backend.timeout,
  }
  showEditDialog.value = true
}

async function updateBackend() {
  if (!editingBackend.value) return
  saving.value = true
  try {
    await api.updateBackend(editingBackend.value.name, {
      url: editForm.value.url,
      prefix: editForm.value.prefix || undefined,
      mount_enabled: editForm.value.mount_enabled,
      timeout: editForm.value.timeout,
    })
    toast.add({
      severity: 'success',
      summary: 'Success',
      detail: `Backend '${editingBackend.value.name}' updated`,
      life: 3000,
    })
    showEditDialog.value = false
    await loadBackends()
  } catch (error) {
    const message =
      error instanceof ApiError ? error.detail : 'Failed to update backend'
    toast.add({
      severity: 'error',
      summary: 'Error',
      detail: message,
      life: 5000,
    })
  } finally {
    saving.value = false
  }
}

async function toggleBackend(backend: Backend) {
  try {
    if (backend.enabled) {
      await api.disableBackend(backend.name)
      toast.add({
        severity: 'info',
        summary: 'Disabled',
        detail: `Backend '${backend.name}' disabled`,
        life: 3000,
      })
    } else {
      await api.enableBackend(backend.name)
      toast.add({
        severity: 'success',
        summary: 'Enabled',
        detail: `Backend '${backend.name}' enabled`,
        life: 3000,
      })
    }
    await loadBackends()
  } catch (error) {
    const message =
      error instanceof ApiError ? error.detail : 'Failed to toggle backend'
    toast.add({
      severity: 'error',
      summary: 'Error',
      detail: message,
      life: 5000,
    })
  }
}

async function refreshBackend(backend: Backend) {
  refreshingBackend.value = backend.name
  try {
    const result = await api.refreshBackend(backend.name)
    toast.add({
      severity: 'success',
      summary: 'Refreshed',
      detail: `Found ${result.tools_count} tools`,
      life: 3000,
    })
    await loadBackends()
  } catch (error) {
    const message =
      error instanceof ApiError ? error.detail : 'Failed to refresh backend'
    toast.add({
      severity: 'error',
      summary: 'Error',
      detail: message,
      life: 5000,
    })
  } finally {
    refreshingBackend.value = null
  }
}

function confirmDelete(backend: Backend) {
  confirm.require({
    message: `Are you sure you want to delete backend '${backend.name}'? This will also remove all cached tools.`,
    header: 'Delete Backend',
    icon: 'pi pi-exclamation-triangle',
    rejectProps: {
      label: 'Cancel',
      severity: 'secondary',
      outlined: true,
    },
    acceptProps: {
      label: 'Delete',
      severity: 'danger',
    },
    accept: async () => {
      try {
        await api.deleteBackend(backend.name)
        toast.add({
          severity: 'success',
          summary: 'Deleted',
          detail: `Backend '${backend.name}' deleted`,
          life: 3000,
        })
        await loadBackends()
      } catch (error) {
        const message =
          error instanceof ApiError ? error.detail : 'Failed to delete backend'
        toast.add({
          severity: 'error',
          summary: 'Error',
          detail: message,
          life: 5000,
        })
      }
    },
  })
}

function formatDate(dateStr: string) {
  return new Date(dateStr).toLocaleString()
}

onMounted(loadBackends)
</script>

<template>
  <div class="page-header">
    <h2 class="page-title">Backends</h2>
    <Button label="Add Backend" icon="pi pi-plus" @click="openAddDialog" />
  </div>

  <div v-if="loading" class="loading-overlay">
    <ProgressSpinner />
  </div>

  <div v-else-if="backends.length === 0" class="empty-state">
    <i class="pi pi-server empty-state-icon"></i>
    <div class="empty-state-title">No backends configured</div>
    <div class="empty-state-description">
      Add your first MCP backend to start aggregating tools
    </div>
    <Button label="Add Backend" icon="pi pi-plus" @click="openAddDialog" />
  </div>

  <div v-else class="backend-grid">
    <div v-for="backend in backends" :key="backend.id" class="backend-card">
      <div class="backend-header">
        <div class="backend-title">
          <span
            class="backend-status-indicator"
            :class="backend.enabled ? 'enabled' : 'disabled'"
          ></span>
          <span class="backend-name">{{ backend.name }}</span>
          <Tag
            v-if="backend.enabled"
            value="Enabled"
            severity="success"
            style="margin-left: 0.5rem"
          />
          <Tag v-else value="Disabled" severity="secondary" style="margin-left: 0.5rem" />
        </div>
        <div class="backend-actions">
          <Button
            icon="pi pi-refresh"
            severity="secondary"
            text
            rounded
            size="small"
            :loading="refreshingBackend === backend.name"
            @click="refreshBackend(backend)"
            v-tooltip.top="'Refresh tools'"
          />
          <Button
            icon="pi pi-pencil"
            severity="secondary"
            text
            rounded
            size="small"
            @click="openEditDialog(backend)"
            v-tooltip.top="'Edit'"
          />
        </div>
      </div>

      <div class="backend-details">
        <span class="backend-detail">
          <i class="pi pi-link"></i>
          {{ backend.url }}
        </span>
        <span class="backend-detail">
          <i class="pi pi-tag"></i>
          Prefix: {{ backend.effective_prefix }}
        </span>
        <span class="backend-detail">
          <i class="pi pi-wrench"></i>
          {{ backend.tool_count }} tools
        </span>
        <span v-if="backend.mount_enabled" class="backend-detail">
          <i class="pi pi-check-circle"></i>
          Mount enabled
        </span>
      </div>

      <div class="backend-footer">
        <span class="backend-meta">
          Created: {{ formatDate(backend.created_at) }}
        </span>
        <div class="backend-actions">
          <Button
            v-if="backend.enabled"
            label="Disable"
            severity="secondary"
            outlined
            size="small"
            @click="toggleBackend(backend)"
          />
          <Button
            v-else
            label="Enable"
            severity="success"
            outlined
            size="small"
            @click="toggleBackend(backend)"
          />
          <Button
            label="Delete"
            severity="danger"
            outlined
            size="small"
            @click="confirmDelete(backend)"
          />
        </div>
      </div>
    </div>
  </div>

  <!-- Add Backend Dialog -->
  <Dialog
    v-model:visible="showAddDialog"
    header="Add Backend"
    :style="{ width: '500px' }"
    :modal="true"
    :closable="!saving"
  >
    <div class="form-field">
      <label class="form-label" for="name">Name *</label>
      <InputText
        id="name"
        v-model="newBackend.name"
        placeholder="e.g., mcp-weather"
        style="width: 100%"
      />
      <small class="form-hint">Unique identifier for this backend</small>
    </div>

    <div class="form-field">
      <label class="form-label" for="url">URL *</label>
      <InputText
        id="url"
        v-model="newBackend.url"
        placeholder="e.g., http://localhost:8001/mcp"
        style="width: 100%"
      />
      <small class="form-hint">MCP server endpoint URL</small>
    </div>

    <div class="form-field">
      <label class="form-label" for="prefix">Prefix</label>
      <InputText
        id="prefix"
        v-model="newBackend.prefix"
        placeholder="e.g., weather (defaults to name)"
        style="width: 100%"
      />
      <small class="form-hint">Tool name prefix (e.g., weather__get_forecast)</small>
    </div>

    <div class="form-field">
      <label class="form-label" for="timeout">Timeout (seconds)</label>
      <InputNumber
        id="timeout"
        v-model="newBackend.timeout"
        :min="1"
        :max="300"
        style="width: 100%"
      />
    </div>

    <div class="form-field">
      <div style="display: flex; align-items: center; gap: 0.5rem">
        <Checkbox
          v-model="newBackend.mount_enabled"
          inputId="mount_enabled"
          :binary="true"
        />
        <label for="mount_enabled">Enable direct mount (/mcp/{prefix})</label>
      </div>
    </div>

    <div class="form-field">
      <div style="display: flex; align-items: center; gap: 0.5rem">
        <Checkbox
          v-model="newBackend.enabled"
          inputId="enabled"
          :binary="true"
        />
        <label for="enabled">Enable on creation</label>
      </div>
    </div>

    <div class="dialog-footer">
      <Button
        label="Cancel"
        severity="secondary"
        @click="showAddDialog = false"
        :disabled="saving"
      />
      <Button
        label="Add Backend"
        icon="pi pi-plus"
        @click="createBackend"
        :loading="saving"
        :disabled="!newBackend.name || !newBackend.url"
      />
    </div>
  </Dialog>

  <!-- Edit Backend Dialog -->
  <Dialog
    v-model:visible="showEditDialog"
    :header="`Edit Backend: ${editingBackend?.name}`"
    :style="{ width: '500px' }"
    :modal="true"
    :closable="!saving"
  >
    <div class="form-field">
      <label class="form-label" for="edit-url">URL *</label>
      <InputText
        id="edit-url"
        v-model="editForm.url"
        placeholder="e.g., http://localhost:8001/mcp"
        style="width: 100%"
      />
    </div>

    <div class="form-field">
      <label class="form-label" for="edit-prefix">Prefix</label>
      <InputText
        id="edit-prefix"
        v-model="editForm.prefix"
        placeholder="e.g., weather"
        style="width: 100%"
      />
    </div>

    <div class="form-field">
      <label class="form-label" for="edit-timeout">Timeout (seconds)</label>
      <InputNumber
        id="edit-timeout"
        v-model="editForm.timeout"
        :min="1"
        :max="300"
        style="width: 100%"
      />
    </div>

    <div class="form-field">
      <div style="display: flex; align-items: center; gap: 0.5rem">
        <Checkbox
          v-model="editForm.mount_enabled"
          inputId="edit_mount_enabled"
          :binary="true"
        />
        <label for="edit_mount_enabled"
          >Enable direct mount (/mcp/{prefix})</label
        >
      </div>
    </div>

    <div class="dialog-footer">
      <Button
        label="Cancel"
        severity="secondary"
        @click="showEditDialog = false"
        :disabled="saving"
      />
      <Button
        label="Save Changes"
        icon="pi pi-check"
        @click="updateBackend"
        :loading="saving"
        :disabled="!editForm.url"
      />
    </div>
  </Dialog>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useToast } from 'primevue/usetoast'
import { useConfirm } from 'primevue/useconfirm'
import Button from 'primevue/button'
import Card from 'primevue/card'
import InputNumber from 'primevue/inputnumber'
import ProgressSpinner from 'primevue/progressspinner'
import ProgressBar from 'primevue/progressbar'
import Textarea from 'primevue/textarea'
import Tag from 'primevue/tag'
import { api, ApiError } from '@/api/client'
import type { ToolRagConfig, ToolRagStatus } from '@/types'

const toast = useToast()
const confirm = useConfirm()

// Default template with placeholder
const PLACEHOLDER = '{{TOOL_LIST}}'
const DEFAULT_TEMPLATE = `Search for tools to help with your task. Available capabilities include:

${PLACEHOLDER}

Describe what you need in natural language.`

const loading = ref(true)
const saving = ref(false)
const regenerating = ref(false)
const loadingPreview = ref(false)
const config = ref<ToolRagConfig | null>(null)
const status = ref<ToolRagStatus | null>(null)
const previewRendered = ref('')
const showPreview = ref(false)

// Form state
const formThreshold = ref(0.5)
const formMaxResults = ref(5)
const formManifest = ref('')

const hasChanges = computed(() => {
  if (!config.value) return false
  return (
    formThreshold.value !== config.value.default_threshold ||
    formMaxResults.value !== config.value.default_max_results ||
    formManifest.value !== config.value.capability_manifest
  )
})

async function loadData() {
  loading.value = true
  try {
    const [configResponse, statusResponse] = await Promise.all([
      api.getToolRagConfig(),
      api.getToolRagStatus(),
    ])
    config.value = configResponse
    status.value = statusResponse

    // Initialize form state
    formThreshold.value = configResponse.default_threshold
    formMaxResults.value = configResponse.default_max_results
    formManifest.value = configResponse.capability_manifest
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Error',
      detail: 'Failed to load Tool RAG settings',
      life: 3000,
    })
  } finally {
    loading.value = false
  }
}

async function saveSettings() {
  saving.value = true
  try {
    const updated = await api.updateToolRagConfig({
      default_threshold: formThreshold.value,
      default_max_results: formMaxResults.value,
      capability_manifest: formManifest.value,
    })
    config.value = updated
    toast.add({
      severity: 'success',
      summary: 'Success',
      detail: 'Tool RAG settings saved',
      life: 3000,
    })
    // Refresh preview if it was open
    if (showPreview.value) {
      await loadPreview()
    }
  } catch (error) {
    const message =
      error instanceof ApiError ? error.detail : 'Failed to save settings'
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

function confirmRegenerate() {
  confirm.require({
    message: 'This will regenerate embeddings for all tools. This may take a while depending on the number of tools. Continue?',
    header: 'Regenerate Embeddings',
    icon: 'pi pi-refresh',
    rejectProps: {
      label: 'Cancel',
      severity: 'secondary',
      outlined: true,
    },
    acceptProps: {
      label: 'Regenerate',
      severity: 'warn',
    },
    accept: async () => {
      await regenerateEmbeddings()
    },
  })
}

async function regenerateEmbeddings() {
  regenerating.value = true
  try {
    const result = await api.regenerateEmbeddings()
    toast.add({
      severity: 'success',
      summary: 'Success',
      detail: result.message,
      life: 5000,
    })
    // Reload status to update counts
    status.value = await api.getToolRagStatus()
  } catch (error) {
    const message =
      error instanceof ApiError ? error.detail : 'Failed to regenerate embeddings'
    toast.add({
      severity: 'error',
      summary: 'Error',
      detail: message,
      life: 5000,
    })
  } finally {
    regenerating.value = false
  }
}

async function loadPreview() {
  loadingPreview.value = true
  try {
    const preview = await api.previewManifest()
    previewRendered.value = preview.rendered
    showPreview.value = true
  } catch (error) {
    const message =
      error instanceof ApiError ? error.detail : 'Failed to load preview'
    toast.add({
      severity: 'error',
      summary: 'Error',
      detail: message,
      life: 5000,
    })
  } finally {
    loadingPreview.value = false
  }
}

function insertDefaultTemplate() {
  formManifest.value = DEFAULT_TEMPLATE
}

function insertPlaceholder() {
  formManifest.value += '{{TOOL_LIST}}'
}

function resetForm() {
  if (config.value) {
    formThreshold.value = config.value.default_threshold
    formMaxResults.value = config.value.default_max_results
    formManifest.value = config.value.capability_manifest
  }
  showPreview.value = false
}

function formatDate(dateStr: string) {
  return new Date(dateStr).toLocaleString()
}

onMounted(loadData)
</script>

<template>
  <div class="page-header">
    <h2 class="page-title">Tool RAG Settings</h2>
    <div style="display: flex; gap: 0.5rem">
      <Button
        label="Reset"
        icon="pi pi-undo"
        severity="secondary"
        outlined
        :disabled="!hasChanges || saving"
        @click="resetForm"
      />
      <Button
        label="Save Changes"
        icon="pi pi-check"
        :disabled="!hasChanges"
        :loading="saving"
        @click="saveSettings"
      />
    </div>
  </div>

  <div v-if="loading" class="loading-overlay">
    <ProgressSpinner />
  </div>

  <div v-else class="settings-grid">
    <!-- Status Card -->
    <Card class="settings-card">
      <template #title>
        <div class="card-header">
          <span>Embedding Status</span>
          <Tag
            v-if="status?.enabled"
            value="Enabled"
            severity="success"
          />
          <Tag
            v-else
            value="Disabled"
            severity="secondary"
          />
        </div>
      </template>
      <template #content>
        <div class="status-info">
          <div class="status-row">
            <span class="status-label">Embedding Model</span>
            <span class="status-value monospace">{{ status?.embedding_model }}</span>
          </div>

          <div class="status-row">
            <span class="status-label">Indexed Tools</span>
            <span class="status-value">
              {{ status?.indexed_tools }} / {{ status?.total_tools }}
              <span class="status-percentage">({{ status?.indexing_percentage }}%)</span>
            </span>
          </div>

          <div class="progress-container">
            <ProgressBar
              :value="status?.indexing_percentage || 0"
              :showValue="false"
              style="height: 8px"
            />
          </div>

          <div class="regenerate-section">
            <Button
              label="Regenerate Embeddings"
              icon="pi pi-refresh"
              severity="secondary"
              outlined
              :loading="regenerating"
              :disabled="!status?.enabled"
              @click="confirmRegenerate"
            />
            <small class="form-hint">
              Recompute embeddings for all tools. Use this after changing the embedding model.
            </small>
          </div>
        </div>
      </template>
    </Card>

    <!-- Search Defaults Card -->
    <Card class="settings-card">
      <template #title>Search Defaults</template>
      <template #content>
        <div class="form-field">
          <label class="form-label" for="threshold">Similarity Threshold</label>
          <InputNumber
            id="threshold"
            v-model="formThreshold"
            :min="0"
            :max="1"
            :minFractionDigits="1"
            :maxFractionDigits="2"
            :step="0.05"
            style="width: 100%"
          />
          <small class="form-hint">
            Minimum similarity score (0-1) for tool matches. Higher values = stricter matching.
            Default: 0.5
          </small>
        </div>

        <div class="form-field">
          <label class="form-label" for="maxResults">Max Results</label>
          <InputNumber
            id="maxResults"
            v-model="formMaxResults"
            :min="1"
            :max="50"
            style="width: 100%"
          />
          <small class="form-hint">
            Maximum number of tools returned per search. Default: 5
          </small>
        </div>
      </template>
    </Card>

    <!-- Capability Manifest Template Card -->
    <Card class="settings-card manifest-card">
      <template #title>
        <div class="card-header">
          <span>Capability Manifest Template</span>
          <span v-if="config?.updated_at" class="updated-at">
            Last updated: {{ formatDate(config.updated_at) }}
          </span>
        </div>
      </template>
      <template #content>
        <div class="form-field">
          <div class="template-actions">
            <Button
              label="Insert Default Template"
              icon="pi pi-file"
              severity="secondary"
              outlined
              size="small"
              @click="insertDefaultTemplate"
            />
            <Button
              label="Insert {{TOOL_LIST}}"
              icon="pi pi-plus"
              severity="secondary"
              outlined
              size="small"
              @click="insertPlaceholder"
            />
          </div>
          <Textarea
            v-model="formManifest"
            rows="8"
            :placeholder="`Enter your manifest template here. Use ${PLACEHOLDER} as a placeholder for the auto-generated tool list.`"
            style="width: 100%; font-family: monospace; font-size: 0.875rem"
          />
          <small class="form-hint">
            Use <code>{{ PLACEHOLDER }}</code> as a placeholder for the auto-generated list of tools grouped by backend.
            Your custom text around the placeholder will be preserved when tools change.
          </small>
        </div>

        <!-- Preview Section -->
        <div class="preview-section">
          <div class="preview-header">
            <span class="preview-title">Preview (what LLMs will see)</span>
            <Button
              :label="showPreview ? 'Refresh Preview' : 'Show Preview'"
              :icon="loadingPreview ? 'pi pi-spin pi-spinner' : 'pi pi-eye'"
              severity="secondary"
              outlined
              size="small"
              :disabled="loadingPreview"
              @click="loadPreview"
            />
          </div>
          <div v-if="showPreview" class="preview-content">
            <pre>{{ previewRendered }}</pre>
          </div>
          <div v-else class="preview-placeholder">
            Click "Show Preview" to see the rendered manifest with the current tool list.
          </div>
        </div>
      </template>
    </Card>
  </div>
</template>

<style scoped>
.settings-grid {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
}

.settings-card {
  background-color: var(--p-surface-card);
  border: 1px solid var(--p-surface-border);
  border-radius: var(--border-radius);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--spacing-md);
}

.updated-at {
  font-size: 0.75rem;
  font-weight: normal;
  color: var(--p-text-muted-color);
}

.status-info {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.status-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.status-label {
  color: var(--p-text-muted-color);
  font-size: 0.875rem;
}

.status-value {
  font-weight: 500;
  color: var(--p-text-color);
}

.status-percentage {
  color: var(--p-text-muted-color);
  margin-left: var(--spacing-xs);
}

.monospace {
  font-family: monospace;
  font-size: 0.875rem;
}

.progress-container {
  margin: var(--spacing-sm) 0;
}

.regenerate-section {
  margin-top: var(--spacing-md);
  padding-top: var(--spacing-md);
  border-top: 1px solid var(--p-surface-border);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.manifest-card {
  flex: 1;
}

.template-actions {
  display: flex;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-sm);
}

.form-hint code {
  background-color: var(--p-surface-hover);
  padding: 0.125rem 0.375rem;
  border-radius: 4px;
  font-family: monospace;
  font-size: 0.8125rem;
}

.preview-section {
  margin-top: var(--spacing-lg);
  padding-top: var(--spacing-lg);
  border-top: 1px solid var(--p-surface-border);
}

.preview-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-md);
}

.preview-title {
  font-weight: 500;
  color: var(--p-text-color);
}

.preview-content {
  background-color: var(--p-surface-ground);
  border: 1px solid var(--p-surface-border);
  border-radius: var(--border-radius);
  padding: var(--spacing-md);
  overflow-x: auto;
}

.preview-content pre {
  margin: 0;
  white-space: pre-wrap;
  word-wrap: break-word;
  font-family: monospace;
  font-size: 0.875rem;
  color: var(--p-text-color);
}

.preview-placeholder {
  color: var(--p-text-muted-color);
  font-size: 0.875rem;
  font-style: italic;
}

@media (min-width: 1024px) {
  .settings-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    grid-template-rows: auto 1fr;
    gap: var(--spacing-lg);
  }

  .manifest-card {
    grid-column: 1 / -1;
  }
}
</style>

<script setup lang="ts">
import { useRoute } from 'vue-router'
import { computed } from 'vue'
import Button from 'primevue/button'

const route = useRoute()

const pageTitle = computed(() => {
  const titles: Record<string, string> = {
    dashboard: 'Dashboard',
    backends: 'Backends',
    tools: 'Tools',
    metrics: 'Metrics',
  }
  return titles[route.name as string] || 'Dashboard'
})

const emit = defineEmits<{
  refresh: []
}>()

function handleRefresh() {
  emit('refresh')
  window.location.reload()
}
</script>

<template>
  <header class="app-header">
    <h1 class="header-title">{{ pageTitle }}</h1>
    <div class="header-actions">
      <Button
        icon="pi pi-refresh"
        severity="secondary"
        text
        rounded
        aria-label="Refresh"
        @click="handleRefresh"
      />
    </div>
  </header>
</template>

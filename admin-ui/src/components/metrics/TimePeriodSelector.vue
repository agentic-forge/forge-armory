<script setup lang="ts">
import SelectButton from 'primevue/selectbutton'
import type { TimePeriod } from '@/types'

const model = defineModel<TimePeriod>({ default: '24h' })

const periods = [
  { label: '1h', value: '1h' },
  { label: '24h', value: '24h' },
  { label: '7d', value: '7d' },
  { label: '30d', value: '30d' },
  { label: 'All', value: 'all' },
]
</script>

<template>
  <SelectButton
    v-model="model"
    :options="periods"
    optionLabel="label"
    optionValue="value"
    :allowEmpty="false"
  />
</template>

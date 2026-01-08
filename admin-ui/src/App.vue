<script setup lang="ts">
import { RouterView } from 'vue-router'
import Toast from 'primevue/toast'
import ConfirmDialog from 'primevue/confirmdialog'
import Sidebar from '@/components/layout/Sidebar.vue'
import Header from '@/components/layout/Header.vue'
</script>

<template>
  <Toast position="top-right" />
  <ConfirmDialog />
  <div class="app-layout">
    <Sidebar />
    <div class="main-content">
      <Header />
      <main class="page-content">
        <RouterView />
      </main>
    </div>
  </div>
</template>

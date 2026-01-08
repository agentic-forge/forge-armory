<script setup lang="ts">
import { RouterLink } from 'vue-router'

const navItems = [
  { name: 'Dashboard', icon: 'pi-home', to: '/' },
  { name: 'Backends', icon: 'pi-server', to: '/backends' },
  { name: 'Tools', icon: 'pi-wrench', to: '/tools' },
  { name: 'Metrics', icon: 'pi-chart-bar', to: '/metrics' },
]
</script>

<template>
  <aside class="sidebar">
    <div class="sidebar-header">
      <RouterLink to="/" class="sidebar-logo">
        <i class="pi pi-box sidebar-logo-icon"></i>
        <span class="sidebar-logo-text">Forge Armory</span>
      </RouterLink>
    </div>
    <nav class="sidebar-nav">
      <RouterLink
        v-for="item in navItems"
        :key="item.name"
        :to="item.to"
        class="nav-item"
      >
        <i :class="['pi', item.icon]"></i>
        <span>{{ item.name }}</span>
      </RouterLink>
    </nav>
  </aside>
</template>

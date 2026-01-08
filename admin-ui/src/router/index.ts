import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory('/ui/'),
  routes: [
    {
      path: '/',
      name: 'dashboard',
      component: () => import('@/views/DashboardView.vue'),
    },
    {
      path: '/backends',
      name: 'backends',
      component: () => import('@/views/BackendsView.vue'),
    },
    {
      path: '/tools',
      name: 'tools',
      component: () => import('@/views/ToolsView.vue'),
    },
    {
      path: '/metrics',
      name: 'metrics',
      component: () => import('@/views/MetricsView.vue'),
    },
  ],
})

export default router

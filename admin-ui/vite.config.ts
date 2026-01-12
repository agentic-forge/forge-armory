import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

// API URL for proxy - defaults to localhost for local dev, can be overridden for Docker
const apiUrl = process.env.VITE_API_URL || 'http://localhost:4042'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  base: '/ui/',
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  server: {
    port: 4043,
    proxy: {
      '/admin': {
        target: apiUrl,
        changeOrigin: true,
      },
    },
  },
  preview: {
    port: 4043,
    proxy: {
      '/admin': {
        target: apiUrl,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
  },
})

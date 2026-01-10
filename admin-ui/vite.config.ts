import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

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
        target: 'http://localhost:4042',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
  },
})

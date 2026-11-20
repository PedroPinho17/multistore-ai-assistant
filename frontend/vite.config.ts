import { fileURLToPath, URL } from 'node:url'
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

const API = 'http://127.0.0.1:8002'

// https://vite.dev/config/
export default defineConfig({
  base: '/app/',
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    proxy: {
      // HTML (browser navigation) stays on Vite; fetch/XHR go to the FastAPI backend.
      '^/(?!src/|@|node_modules/|app/).*': {
        target: API,
        changeOrigin: true,
        bypass(req) {
          const accept = req.headers.accept ?? ''
          if (accept.includes('text/html')) return req.url
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: false,
    include: ['src/**/*.{test,spec}.ts', 'src/__tests__/**/*.ts'],
    setupFiles: ['src/test-setup.ts'],
  },
})

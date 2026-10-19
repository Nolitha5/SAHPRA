import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// In development the dashboard runs on :5173 and forwards /api to the Python
// server on :8000, so the browser never needs the API's address or any key.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: false },
    },
  },
  test: {
    include: ['src/**/*.test.{ts,tsx}'],
  },
})

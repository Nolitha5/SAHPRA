import { readFileSync } from 'node:fs'
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

/** The API port: M2_API_PORT from the environment, else from member2-rag/.env, else 8000. */
function apiPort(): string {
  if (process.env.M2_API_PORT) return process.env.M2_API_PORT
  try {
    const env = readFileSync(new URL('./member2-rag/.env', import.meta.url), 'utf8')
    const match = env.match(/^\s*M2_API_PORT\s*=\s*(\d+)\s*$/m)
    if (match) return match[1]
  } catch {
    // No .env yet: use the default.
  }
  return '8000'
}

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: `http://127.0.0.1:${apiPort()}`, changeOrigin: false },
    },
  },
  test: {
    include: ['src/**/*.test.{ts,tsx}'],
  },
})

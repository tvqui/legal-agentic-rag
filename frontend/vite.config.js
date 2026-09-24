import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '')
  const target = env.VITE_BACKEND_TARGET || 'http://127.0.0.1:8000'
  // BACKEND_PROXY_TOKEN intentionally has no VITE_ prefix, so Vite does not
  // expose it to browser JavaScript. It is used only by the local dev proxy.
  const token = env.BACKEND_PROXY_TOKEN || ''
  const headers = { 'ngrok-skip-browser-warning': 'true' }
  if (token) headers.Authorization = `Bearer ${token}`
  return {
    plugins: [react()],
    server: {
      proxy: {
        '/api': {
          target,
          changeOrigin: true,
          secure: true,
          headers,
          rewrite: (path) => path.replace(/^\/api/, ''),
        },
      },
    },
  }
})

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: '0.0.0.0',
    watch: {
      usePolling: true,
    },
    proxy: {
      '/api': {
        target: 'http://localhost:18765',
        changeOrigin: true
      },
      '/query': {
        target: 'http://localhost:18765',
        changeOrigin: true
      }
    }
  }
})

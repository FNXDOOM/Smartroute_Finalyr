import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  // Load MapLibre worker without pre-bundling.
  optimizeDeps: {
    exclude: ['maplibre-gl'],
  },
  server: {
    // Pin HMR to stable localhost address.
    hmr: {
      protocol: 'ws',
      host: 'localhost',
    },
  },
})

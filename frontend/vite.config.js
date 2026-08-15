import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Pin HMR to a stable ws://localhost address so that Clerk's development
    // handshake redirect (which appends ?token=… to the URL) does not corrupt
    // Vite's WebSocket connection string.
    hmr: {
      protocol: 'ws',
      host: 'localhost',
    },
  },
})

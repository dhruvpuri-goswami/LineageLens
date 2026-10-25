import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { '@': path.resolve(__dirname, 'src') } },
  build: {
    outDir: path.resolve(__dirname, '../lineagelens/static'),
    emptyOutDir: true,
    chunkSizeWarningLimit: 1600,
  },
  server: { port: 5173, proxy: { '/api': 'http://127.0.0.1:8765' } },
})

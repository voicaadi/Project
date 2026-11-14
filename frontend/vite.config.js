import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'https://devopsadi.com',
        changeOrigin: true,
        secure: true,
      },
      '/health': {
        target: 'https://devopsadi.com',
        changeOrigin: true,
        secure: true,
      },
    },
  },
})

import react, { reactCompilerPreset } from '@vitejs/plugin-react'
import babel from '@rolldown/plugin-babel'
import { defineConfig } from 'vite'
import dashboardApiContract from '../contracts/dashboard_api.json' with { type: 'json' }

export default defineConfig({
  plugins: [
    react(),
    babel({ presets: [reactCompilerPreset()] }),
  ],
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      [dashboardApiContract.assistant.path]: {
        target: dashboardApiContract.assistant.upstream,
        changeOrigin: true,
      },
      '/api/findings': {
        target: 'http://127.0.0.1:5001',
        changeOrigin: true,
      },
      '/api': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
      },
    },
  },
})

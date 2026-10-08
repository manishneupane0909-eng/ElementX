import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // The portfolio demo (VITE_DEMO_MODE=true, set by `--mode demo` via .env.demo) ships the
  // static snapshots in public-demo/. The normal app does not include them.
  const demo = loadEnv(mode, process.cwd(), 'VITE_').VITE_DEMO_MODE === 'true'

  return {
    plugins: [react()],
    publicDir: demo ? 'public-demo' : 'public',
    server: {
      port: 5173,
      proxy: {
        '/api': {
          target: 'http://localhost:8000',
          changeOrigin: true,
        },
      },
    },
  }
})

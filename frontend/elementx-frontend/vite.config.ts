import type { IncomingMessage, ServerResponse } from 'node:http'
import type { PreviewServer, ViteDevServer } from 'vite'
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

const CALENDLY_URL = 'https://calendly.com/manishneupane0909/30min'

function sendScheduleRedirect(req: IncomingMessage, res: ServerResponse, next: () => void) {
  const path = req.url?.split('?')[0]
  if (path !== '/schedule' && path !== '/schedule/') {
    next()
    return
  }
  res.statusCode = 302
  res.setHeader('Location', CALENDLY_URL)
  res.end()
}

/** Dev and preview: /schedule is an HTTP redirect. Render uses the same destination in render.demo.yaml. */
function scheduleRedirect() {
  const apply = (server: ViteDevServer | PreviewServer) => {
    server.middlewares.use(sendScheduleRedirect)
  }
  return {
    name: 'elementx-schedule-redirect',
    configureServer: apply,
    configurePreviewServer: apply,
  }
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // The portfolio demo (VITE_DEMO_MODE=true, set by `--mode demo` via .env.demo) ships the
  // static snapshots in public-demo/. The normal app does not include them.
  const demo = loadEnv(mode, process.cwd(), 'VITE_').VITE_DEMO_MODE === 'true'

  return {
    plugins: [react(), ...(demo ? [scheduleRedirect()] : [])],
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

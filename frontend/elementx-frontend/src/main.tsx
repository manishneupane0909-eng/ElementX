import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import AuthProvider from './auth/AuthProvider.tsx'
import ThemeProvider from './theme/ThemeProvider.tsx'
import { DEMO_MODE } from './demo/demoMode.ts'

if (DEMO_MODE) document.title = 'ElementX: Portfolio demo'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider>
      <AuthProvider>
        <App />
      </AuthProvider>
    </ThemeProvider>
  </StrictMode>,
)

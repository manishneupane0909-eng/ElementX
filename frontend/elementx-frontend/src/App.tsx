import { useState } from 'react'
import { useAuth } from './auth/useAuth'
import AuthScreen from './components/AuthScreen'
import AppShell from './components/shell/AppShell'
import type { NavItem } from './components/shell/AppShell'
import Notice from './components/ui/Notice'
import {
  CopilotIcon,
  MagnetometryIcon,
  MaterialsIcon,
  SamplesIcon,
} from './components/ui/Icons'
import MagnetometryUpload from './components/MagnetometryUpload'
import PhysicsCopilot from './components/PhysicsCopilot'
import SampleList from './components/SampleList'
import Search from './components/search'
import './App.css'

type AppMode = 'analytics' | 'magnetometry' | 'samples' | 'copilot'

const ELEMENTS: Record<string, number> = {
  H: 1.008, He: 4.003, Li: 6.941, Be: 9.012, B: 10.81, C: 12.01,
  N: 14.01, O: 16.0, F: 19.0, Ne: 20.18, Na: 22.99, Mg: 24.31,
  Al: 26.98, Si: 28.09, P: 30.97, S: 32.07, Cl: 35.45, Ar: 39.95,
  K: 39.1, Ca: 40.08, Sc: 44.96, Ti: 47.87, V: 50.94, Cr: 52.0,
  Mn: 54.94, Fe: 55.845, Co: 58.933, Ni: 58.693, Cu: 63.546, Zn: 65.38,
  Ga: 69.72, Ge: 72.63, As: 74.92, Se: 78.96, Br: 79.9, Kr: 83.8,
  Rb: 85.47, Sr: 87.62, Y: 88.91, Zr: 91.22, Nb: 92.91, Mo: 95.95,
  Tc: 98.0, Ru: 101.07, Rh: 102.91, Pd: 106.42, Ag: 107.87, Cd: 112.41,
  In: 114.82, Sn: 118.71, Sb: 121.76, Te: 127.6, I: 126.9, Xe: 131.29,
  Cs: 132.91, Ba: 137.33, La: 138.91, Ce: 140.12, Pr: 140.91, Nd: 144.24,
  Pm: 145.0, Sm: 150.36, Eu: 151.96, Gd: 157.25, Tb: 158.93, Dy: 162.5,
  Ho: 164.93, Er: 167.26, Tm: 168.93, Yb: 173.05, Lu: 174.97, Hf: 178.49,
  Ta: 180.95, W: 183.84, Re: 186.21, Os: 190.23, Ir: 192.22, Pt: 195.08,
  Au: 196.97, Hg: 200.59, Tl: 204.38, Pb: 207.2, Bi: 208.98, Po: 209.0,
  At: 210.0, Rn: 222.0,
}

function normalizeSymbol(input: string): string {
  const raw = input.trim()
  if (!raw) return ''
  if (raw.length === 1) return raw.toUpperCase()
  if (raw.length === 2) return raw[0].toUpperCase() + raw[1].toLowerCase()
  return raw
}

const NAV_ITEMS: (NavItem & { id: AppMode })[] = [
  { id: 'samples', label: 'Samples', icon: <SamplesIcon /> },
  { id: 'magnetometry', label: 'Magnetometry', icon: <MagnetometryIcon /> },
  { id: 'analytics', label: 'Materials', title: 'Materials Explorer', icon: <MaterialsIcon /> },
  { id: 'copilot', label: 'Physics Copilot', icon: <CopilotIcon /> },
]

function Workspace() {
  const { user, signOut } = useAuth()
  const [mode, setMode] = useState<AppMode>('samples')

  return (
    <AppShell
      items={NAV_ITEMS}
      activeId={mode}
      onSelect={(id) => setMode(id as AppMode)}
      user={user}
      onSignOut={signOut}
    >
      {mode === 'samples' && <SampleList />}
      {mode === 'magnetometry' && <MagnetometryUpload />}
      {mode === 'analytics' && <Search elements={ELEMENTS} normalizeSymbol={normalizeSymbol} />}
      {mode === 'copilot' && <PhysicsCopilot />}
    </AppShell>
  )
}

function App() {
  const { status, user } = useAuth()

  if (status === 'checking') {
    return (
      <div className="auth-shell">
        <main className="auth-main">
          <Notice kind="loading">Restoring your session…</Notice>
        </main>
      </div>
    )
  }

  if (status !== 'authenticated' || !user) {
    return <AuthScreen />
  }

  // Keyed by account so no workspace state can carry over between users.
  return <Workspace key={user.id} />
}

export default App

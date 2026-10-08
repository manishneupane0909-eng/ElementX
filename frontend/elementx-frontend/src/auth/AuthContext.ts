import { createContext } from 'react'
import type { AuthUser } from '../services/apiClient'

export type AuthStatus = 'checking' | 'authenticated' | 'anonymous'

export interface AuthContextValue {
  status: AuthStatus
  user: AuthUser | null
  /** One-shot message shown on the login screen (e.g. session expired). */
  notice: string | null
  signIn: (email: string, password: string) => Promise<void>
  signUp: (input: {
    name: string
    institution: string
    email: string
    password: string
  }) => Promise<void>
  signOut: () => void
}

export const AuthContext = createContext<AuthContextValue | null>(null)

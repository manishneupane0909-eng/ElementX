import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { AuthContext, type AuthContextValue, type AuthStatus } from './AuthContext'
import {
  UNAUTHORIZED_EVENT,
  clearSession,
  getStoredUser,
  getToken,
  isTokenExpired,
  tokenExpiryMs,
  type AuthUser,
} from '../services/apiClient'
import { login, register } from '../services/authApi'
import { getCopilotStatus } from '../services/magnetApi'

const SESSION_EXPIRED_NOTICE = 'Your session has expired. Please sign in again.'
// setTimeout cannot exceed a signed 32-bit integer of milliseconds.
const MAX_TIMER_MS = 2_147_483_647

function restoreSession(): AuthUser | null {
  const token = getToken()
  const user = getStoredUser()
  if (!token || !user) {
    clearSession()
    return null
  }
  if (isTokenExpired(token)) {
    clearSession()
    return null
  }
  return user
}

export default function AuthProvider({ children }: { children: ReactNode }) {
  const [initialUser] = useState<AuthUser | null>(restoreSession)
  const [user, setUser] = useState<AuthUser | null>(initialUser)
  const [status, setStatus] = useState<AuthStatus>(initialUser ? 'checking' : 'anonymous')
  const [notice, setNotice] = useState<string | null>(null)

  const expire = useCallback(() => {
    clearSession()
    setUser(null)
    setStatus('anonymous')
    setNotice(SESSION_EXPIRED_NOTICE)
  }, [])

  // Verify a restored session against the server once; a 401 triggers UNAUTHORIZED_EVENT.
  useEffect(() => {
    if (!initialUser) return
    let cancelled = false
    getCopilotStatus()
      .catch(() => undefined) // network errors keep the session; 401 is handled by the event
      .finally(() => {
        if (!cancelled) {
          setStatus((current) => (current === 'checking' ? 'authenticated' : current))
        }
      })
    return () => {
      cancelled = true
    }
  }, [initialUser])

  // Server rejected the token (expired / invalid / secret rotated).
  useEffect(() => {
    window.addEventListener(UNAUTHORIZED_EVENT, expire)
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, expire)
  }, [expire])

  // Sign out automatically when the token's own expiry passes.
  useEffect(() => {
    if (!user) return
    const token = getToken()
    const expiry = token ? tokenExpiryMs(token) : null
    if (expiry === null) return
    const delay = Math.min(Math.max(expiry - Date.now(), 0), MAX_TIMER_MS)
    const timer = window.setTimeout(() => {
      if (!getToken() || isTokenExpired(getToken() as string)) {
        expire()
      }
    }, delay)
    return () => window.clearTimeout(timer)
  }, [user, expire])

  const signIn = useCallback<AuthContextValue['signIn']>(async (email, password) => {
    const result = await login(email, password)
    setNotice(null)
    setUser(result.user)
    setStatus('authenticated')
  }, [])

  const signUp = useCallback<AuthContextValue['signUp']>(async (input) => {
    const result = await register(input)
    setNotice(null)
    setUser(result.user)
    setStatus('authenticated')
  }, [])

  const signOut = useCallback(() => {
    clearSession()
    setUser(null)
    setStatus('anonymous')
    setNotice(null)
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({ status, user, notice, signIn, signUp, signOut }),
    [status, user, notice, signIn, signUp, signOut],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

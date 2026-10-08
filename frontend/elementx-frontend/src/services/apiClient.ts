/**
 * Shared API plumbing: base URL, JWT session storage and an authenticated fetch.
 *
 * The backend contract is unchanged: `POST /api/auth/login|register` return
 * `{ token, user }` and every protected route expects `Authorization: Bearer <token>`.
 * Identity is never sent by the client; the server derives it from the verified token.
 */

export const API_BASE_URL =
  import.meta.env.VITE_API_URL?.replace(/\/$/, '') ?? ''

export interface AuthUser {
  id: string
  email: string
  name: string
}

/** Fired when the server rejects the stored token (expired or invalid). */
export const UNAUTHORIZED_EVENT = 'elementx:unauthorized'

const TOKEN_KEY = 'elementx.token'
const USER_KEY = 'elementx.user'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function getStoredUser(): AuthUser | null {
  const raw = localStorage.getItem(USER_KEY)
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw) as Partial<AuthUser>
    if (
      typeof parsed.id === 'string' &&
      typeof parsed.email === 'string' &&
      typeof parsed.name === 'string'
    ) {
      return { id: parsed.id, email: parsed.email, name: parsed.name }
    }
  } catch {
    // fall through
  }
  return null
}

export function saveSession(token: string, user: AuthUser): void {
  localStorage.setItem(TOKEN_KEY, token)
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

export function clearSession(): void {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

/** Expiry (ms since epoch) from the JWT `exp` claim, or null if unreadable. */
export function tokenExpiryMs(token: string): number | null {
  try {
    const payload = token.split('.')[1]
    if (!payload) return null
    const base64 = payload.replace(/-/g, '+').replace(/_/g, '/')
    const padded = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), '=')
    const claims = JSON.parse(atob(padded)) as { exp?: unknown }
    return typeof claims.exp === 'number' ? claims.exp * 1000 : null
  } catch {
    return null
  }
}

export function isTokenExpired(token: string, now: number = Date.now()): boolean {
  const expiry = tokenExpiryMs(token)
  return expiry !== null && expiry <= now
}

/**
 * `fetch` that attaches the session token. A 401 while a session exists clears it and
 * notifies the app so the user is returned to the login screen.
 */
export async function authFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const token = getToken()
  const headers = new Headers(init.headers)
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  const response = await fetch(input, { ...init, headers })

  if (response.status === 401 && token) {
    clearSession()
    window.dispatchEvent(new Event(UNAUTHORIZED_EVENT))
  }
  return response
}

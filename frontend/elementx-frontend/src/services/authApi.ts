import { DEMO_MODE } from '../demo/demoMode'
import { API_BASE_URL, saveSession, type AuthUser } from './apiClient'

export class AuthError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'AuthError'
    this.status = status
  }
}

interface AuthResponse {
  token: string
  user: AuthUser
}

interface ErrorBody {
  detail?: string | { msg?: string }[]
}

async function readError(response: Response, fallback: string): Promise<string> {
  try {
    const body = (await response.json()) as ErrorBody
    if (typeof body.detail === 'string') return body.detail
    if (Array.isArray(body.detail) && body.detail.length > 0) {
      return body.detail
        .map((item) => item.msg)
        .filter(Boolean)
        .join('; ')
    }
  } catch {
    // ignore unreadable body
  }
  return fallback
}

async function submit(
  path: string,
  body: Record<string, string>,
  fallback: string,
): Promise<AuthResponse> {
  if (DEMO_MODE) throw new AuthError(0, 'Sign-in and registration are disabled in the portfolio demo.')
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
  } catch {
    throw new AuthError(0, 'Cannot reach the ElementX server. Check your connection and try again.')
  }

  if (!response.ok) {
    throw new AuthError(response.status, await readError(response, fallback))
  }

  const data = (await response.json()) as Partial<AuthResponse>
  if (!data.token || !data.user) {
    throw new AuthError(response.status, fallback)
  }
  saveSession(data.token, data.user)
  return { token: data.token, user: data.user }
}

export function login(email: string, password: string): Promise<AuthResponse> {
  return submit('/api/auth/login', { email, password }, 'Sign-in failed. Check your email and password.')
}

export function register(input: {
  name: string
  institution: string
  email: string
  password: string
}): Promise<AuthResponse> {
  return submit('/api/auth/register', input, 'Registration failed. Please try again.')
}

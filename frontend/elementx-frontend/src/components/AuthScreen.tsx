import { useState } from 'react'
import type { FormEvent } from 'react'
import { useAuth } from '../auth/useAuth'

type AuthMode = 'login' | 'register'

const MIN_PASSWORD_LENGTH = 8

export default function AuthScreen() {
  const { signIn, signUp, notice } = useAuth()
  const [mode, setMode] = useState<AuthMode>('login')
  const [name, setName] = useState('')
  const [institution, setInstitution] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const switchMode = (next: AuthMode) => {
    setMode(next)
    setError(null)
  }

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)

    if (mode === 'register') {
      if (!name.trim()) {
        setError('Please enter your name.')
        return
      }
      if (password.length < MIN_PASSWORD_LENGTH) {
        setError(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`)
        return
      }
    }

    setSubmitting(true)
    try {
      if (mode === 'login') {
        await signIn(email.trim(), password)
      } else {
        await signUp({
          name: name.trim(),
          institution: institution.trim(),
          email: email.trim(),
          password,
        })
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Authentication failed.')
      setSubmitting(false)
    }
  }

  const isRegister = mode === 'register'

  return (
    <div className="app-shell auth-shell">
      <main className="auth-main">
        <section className="panel auth-panel" aria-labelledby="auth-title">
          <header className="panel-header">
            <h1 className="auth-brand">ElementX</h1>
            <h2 id="auth-title">{isRegister ? 'Create your account' : 'Sign in'}</h2>
            <p>
              {isRegister
                ? 'Your research samples and saved experiments are private to your account.'
                : 'Sign in to open your research samples and saved experiments.'}
            </p>
          </header>

          {notice && (
            <div className="status-banner status-banner--info" role="status">
              {notice}
            </div>
          )}

          <form className="auth-form" onSubmit={(event) => void handleSubmit(event)} noValidate>
            {isRegister && (
              <>
                <label className="field-label" htmlFor="auth-name">
                  Name
                </label>
                <input
                  id="auth-name"
                  className="text-input"
                  autoComplete="name"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  disabled={submitting}
                />
                <label className="field-label" htmlFor="auth-institution">
                  Institution (optional)
                </label>
                <input
                  id="auth-institution"
                  className="text-input"
                  autoComplete="organization"
                  value={institution}
                  onChange={(event) => setInstitution(event.target.value)}
                  disabled={submitting}
                />
              </>
            )}

            <label className="field-label" htmlFor="auth-email">
              Email
            </label>
            <input
              id="auth-email"
              className="text-input"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              disabled={submitting}
            />

            <label className="field-label" htmlFor="auth-password">
              Password
            </label>
            <input
              id="auth-password"
              className="text-input"
              type="password"
              autoComplete={isRegister ? 'new-password' : 'current-password'}
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              disabled={submitting}
            />

            {error && (
              <div className="status-banner status-banner--error" role="alert">
                {error}
              </div>
            )}

            <button
              type="submit"
              className="primary-btn"
              disabled={submitting || !email.trim() || !password}
            >
              {submitting
                ? isRegister
                  ? 'Creating account…'
                  : 'Signing in…'
                : isRegister
                  ? 'Create account'
                  : 'Sign in'}
            </button>
          </form>

          <p className="auth-switch">
            {isRegister ? 'Already have an account?' : 'New to ElementX?'}{' '}
            <button
              type="button"
              className="link-btn"
              onClick={() => switchMode(isRegister ? 'login' : 'register')}
              disabled={submitting}
            >
              {isRegister ? 'Sign in' : 'Create an account'}
            </button>
          </p>
        </section>
      </main>
    </div>
  )
}

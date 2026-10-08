import { useState } from 'react'
import type { FormEvent } from 'react'
import { useAuth } from '../auth/useAuth'
import ThemeToggle from './shell/ThemeToggle'
import Button from './ui/Button'
import Notice from './ui/Notice'
import TextField from './ui/TextField'

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
    <div className="auth-shell">
      <div className="auth-theme">
        <ThemeToggle />
      </div>
      <main className="auth-main">
        <section className="auth-panel" aria-labelledby="auth-title">
          <p className="auth-brand">ElementX</p>
          <header className="auth-header">
            <h1 id="auth-title">{isRegister ? 'Create account' : 'Sign in'}</h1>
            <p>
              {isRegister
                ? 'Your samples and saved experiments are private to your account.'
                : 'Open your samples and saved experiments.'}
            </p>
          </header>

          {notice && <Notice kind="info">{notice}</Notice>}

          <form className="auth-form" onSubmit={(event) => void handleSubmit(event)} noValidate>
            {isRegister && (
              <>
                <TextField
                  label="Name"
                  autoComplete="name"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  disabled={submitting}
                />
                <TextField
                  label="Institution (optional)"
                  autoComplete="organization"
                  value={institution}
                  onChange={(event) => setInstitution(event.target.value)}
                  disabled={submitting}
                />
              </>
            )}

            <TextField
              label="Email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              disabled={submitting}
            />

            <TextField
              label="Password"
              type="password"
              autoComplete={isRegister ? 'new-password' : 'current-password'}
              required
              hint={isRegister ? `At least ${MIN_PASSWORD_LENGTH} characters.` : undefined}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              disabled={submitting}
            />

            {error && <Notice kind="error">{error}</Notice>}

            <Button
              type="submit"
              variant="primary"
              disabled={submitting || !email.trim() || !password}
            >
              {submitting
                ? isRegister
                  ? 'Creating account…'
                  : 'Signing in…'
                : isRegister
                  ? 'Create account'
                  : 'Sign in'}
            </Button>
          </form>

          <p className="auth-switch">
            {isRegister ? 'Already have an account?' : 'New to ElementX?'}{' '}
            <Button
              variant="link"
              onClick={() => switchMode(isRegister ? 'login' : 'register')}
              disabled={submitting}
            >
              {isRegister ? 'Sign in' : 'Create an account'}
            </Button>
          </p>
        </section>
      </main>
    </div>
  )
}

// Pre-build guard for production builds (npm run build:production).
//
// VITE_* variables are inlined into the public JavaScript bundle, so this refuses to
// build when the API URL is missing/unsafe or when a VITE_* variable looks like a secret.
// Only variable *names* are ever printed, never values.

const problems = []
const env = process.env

const apiUrl = (env.VITE_API_URL ?? '').trim()
if (!apiUrl) {
  problems.push(
    'VITE_API_URL is not set. Without it the app would call its own static host instead of the backend API.',
  )
} else {
  let parsed
  try {
    parsed = new URL(apiUrl)
  } catch {
    problems.push('VITE_API_URL is not a valid absolute URL (expected https://<backend-host>).')
  }
  if (parsed) {
    const localHosts = new Set(['localhost', '127.0.0.1'])
    if (parsed.protocol !== 'https:' && !(parsed.protocol === 'http:' && localHosts.has(parsed.hostname))) {
      problems.push('VITE_API_URL must use https:// (http:// is only allowed for localhost previews).')
    }
    if (parsed.username || parsed.password) {
      problems.push('VITE_API_URL must not contain credentials.')
    }
    if (parsed.search || parsed.hash) {
      problems.push('VITE_API_URL must not contain a query string or fragment.')
    }
  }
}

const SECRET_NAME = /(SECRET|PASSWORD|PASSWD|TOKEN|PRIVATE|CREDENTIAL|API_?KEY|MONGO|DATABASE)/i
for (const name of Object.keys(env)) {
  if (name.startsWith('VITE_') && name !== 'VITE_API_URL' && SECRET_NAME.test(name)) {
    problems.push(`${name} looks like a secret, and VITE_* values are published in the bundle.`)
  }
}

if (problems.length > 0) {
  console.error('Production build configuration is invalid:')
  for (const problem of problems) console.error(`  - ${problem}`)
  process.exit(1)
}
console.log('Production build configuration OK (VITE_API_URL is set and safe).')

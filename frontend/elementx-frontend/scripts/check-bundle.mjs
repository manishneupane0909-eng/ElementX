// Post-build guard: fail if the built bundle contains anything that looks like a credential.
//
// Usage: node scripts/check-bundle.mjs [distDir]
// Checks (1) the *values* of well-known server secrets present in the build environment
// and (2) common credential patterns. Matches are reported by file and rule, never printed.

import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'

const distDir = process.argv[2] ?? 'dist'

const SECRET_ENV_NAMES = [
  'JWT_SECRET',
  'MONGODB_URI',
  'MP_API_KEY',
  'MATERIALS_PROJECT_API_KEY',
  'GEMINI_API_KEY',
  'GOOGLE_API_KEY',
  'OPENAI_API_KEY',
]
const PATTERNS = [
  ['mongodb connection string with credentials', /mongodb(\+srv)?:\/\/[^\s"'`/]+:[^\s"'`@]+@/i],
  ['Google API key', /AIza[0-9A-Za-z_-]{35}/],
  ['OpenAI-style secret key', /sk-[A-Za-z0-9_-]{20,}/],
  ['private key block', /-----BEGIN [A-Z ]*PRIVATE KEY-----/],
  ['default development JWT secret', /superlongrandomkey/i],
  ['hard-coded bearer token', /Bearer\s+eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\./],
]

function* walk(dir) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) yield* walk(full)
    else yield full
  }
}

const secretValues = SECRET_ENV_NAMES.map((name) => [name, (process.env[name] ?? '').trim()]).filter(
  ([, value]) => value.length >= 8,
)

const findings = []
let scanned = 0
for (const file of walk(distDir)) {
  if (!/\.(js|css|html|map|json|txt|svg)$/i.test(file)) continue
  scanned += 1
  const text = readFileSync(file, 'utf8')
  for (const [name, value] of secretValues) {
    if (text.includes(value)) findings.push(`${file}: contains the value of ${name}`)
  }
  for (const [label, pattern] of PATTERNS) {
    if (pattern.test(text)) findings.push(`${file}: matches pattern "${label}"`)
  }
}

if (scanned === 0) {
  console.error(`No build output found in ${distDir}; run the build first.`)
  process.exit(1)
}
if (findings.length > 0) {
  console.error('Credential-like content found in the frontend bundle:')
  for (const finding of findings) console.error(`  - ${finding}`)
  process.exit(1)
}
console.log(`Bundle check OK: ${scanned} files scanned, no credentials found.`)

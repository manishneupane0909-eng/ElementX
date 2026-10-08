// Verifies WCAG contrast for the design tokens in src/styles/tokens.css, for both themes.
//   Text pairs must reach 4.5:1 (AA). Non-text pairs (control borders, plot series) 3:1.
// Usage: node scripts/check-contrast.mjs   (exits 1 on any failure)

import { readFileSync } from 'node:fs'

const css = readFileSync(new URL('../src/styles/tokens.css', import.meta.url), 'utf8')

function block(selector) {
  const start = css.indexOf(selector)
  if (start < 0) throw new Error(`Missing ${selector}`)
  const open = css.indexOf('{', start)
  return css.slice(open + 1, css.indexOf('}', open))
}

function parse(body) {
  const out = {}
  for (const match of body.matchAll(/--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})\s*;/g)) out[match[1]] = match[2]
  return out
}

const themes = {
  dark: parse(block(":root,\n:root[data-theme='dark']")),
  light: { ...parse(block(":root[data-theme='light']")) },
}

function luminance(hex) {
  const channel = (i) => {
    const v = parseInt(hex.slice(1 + i * 2, 3 + i * 2), 16) / 255
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4
  }
  return 0.2126 * channel(0) + 0.7152 * channel(1) + 0.0722 * channel(2)
}

function ratio(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

const TEXT = 4.5
const NONTEXT = 3
const surfaces = ['canvas', 'surface', 'surface-sunken', 'surface-hover']

const checks = []
for (const bg of surfaces) {
  checks.push(['text', bg, TEXT], ['text-muted', bg, TEXT], ['accent-text', bg, TEXT])
}
for (const bg of ['surface', 'surface-sunken']) checks.push(['text-faint', bg, TEXT])
checks.push(
  ['on-accent', 'accent', TEXT],
  ['on-accent', 'accent-hover', TEXT],
  ['text', 'accent-subtle', TEXT],
  ['accent-text', 'accent-subtle', TEXT],
  ['plot-axis', 'plot-surface', TEXT],
  ['plot-series-1', 'plot-surface', NONTEXT],
  ['plot-series-2', 'plot-surface', NONTEXT],
  ['plot-ref', 'plot-surface', NONTEXT],
  ['secondary', 'surface', NONTEXT],
  ['control-border', 'surface', NONTEXT],
  ['control-border', 'surface-sunken', NONTEXT],
  ['control-border', 'canvas', NONTEXT],
  ['focus-ring', 'canvas', NONTEXT],
  ['focus-ring', 'surface', NONTEXT],
)
for (const kind of ['danger', 'warn', 'success', 'info']) checks.push([`${kind}-text`, `${kind}-bg`, TEXT])

let failures = 0
for (const [name, tokens] of Object.entries(themes)) {
  for (const [fg, bg, min] of checks) {
    if (!tokens[fg] || !tokens[bg]) {
      console.error(`[${name}] missing token ${!tokens[fg] ? fg : bg}`)
      failures += 1
      continue
    }
    const value = ratio(tokens[fg], tokens[bg])
    if (value < min) {
      console.error(`[${name}] ${fg} on ${bg}: ${value.toFixed(2)}:1 (needs ${min}:1)`)
      failures += 1
    }
  }
}
if (failures > 0) {
  console.error(`${failures} contrast check(s) failed.`)
  process.exit(1)
}
console.log(`Contrast OK: ${checks.length} pairs x ${Object.keys(themes).length} themes meet WCAG thresholds.`)

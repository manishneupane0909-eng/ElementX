const SUPERSCRIPT: Record<string, string> = {
  '-': '⁻',
  '0': '⁰',
  '1': '¹',
  '2': '²',
  '3': '³',
  '4': '⁴',
  '5': '⁵',
  '6': '⁶',
  '7': '⁷',
  '8': '⁸',
  '9': '⁹',
}

const MINUS = '−'

const DECIMAL_SEPARATOR =
  new Intl.NumberFormat().formatToParts(1.5).find((part) => part.type === 'decimal')?.value ?? '.'

/** Splits formatted fixed-point text at the decimal separator, keeping the separator. */
export function splitDecimal(text: string): [string, string] {
  const at = text.lastIndexOf(DECIMAL_SEPARATOR)
  return at < 0 ? [text, ''] : [text.slice(0, at), text.slice(at)]
}

/** Below this magnitude, fixed notation becomes a run of zeros that is hard to read. */
const SCIENTIFIC_BELOW = 1e-3

function withMinus(text: string): string {
  return text.startsWith('-') ? `${MINUS}${text.slice(1)}` : text
}

function significantDigits(fixed: string): number {
  const digits = fixed.replace('-', '').replace('.', '').replace(/^0+/, '').replace(/0+$/, '')
  return Math.max(digits.length, 1)
}

/**
 * Formats a measured value for display, rounded to at most `digits` decimal places.
 *
 * Very small magnitudes are written in scientific notation with exactly the significant digits
 * that the fixed-point rounding would have shown, so the displayed precision never changes.
 */
export function formatNumber(value: number | null | undefined, digits = 3): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '—'
  }
  if (!Number.isFinite(value)) {
    return value > 0 ? '∞' : `${MINUS}∞`
  }

  if (Math.abs(value) < SCIENTIFIC_BELOW) {
    const fixed = value.toFixed(Math.min(digits, 100))
    const rounded = Number(fixed)
    if (rounded !== 0 && Math.abs(rounded) < SCIENTIFIC_BELOW) {
      const precision = significantDigits(fixed) - 1
      const [mantissa, exponent] = rounded.toExponential(precision).split('e')
      const mantissaText = Number(mantissa).toLocaleString(undefined, {
        minimumFractionDigits: precision,
        maximumFractionDigits: precision,
      })
      const exponentText = String(Number(exponent))
        .split('')
        .map((char) => SUPERSCRIPT[char] ?? char)
        .join('')
      return `${withMinus(mantissaText)} × 10${exponentText}`
    }
  }

  return withMinus(
    value.toLocaleString(undefined, {
      maximumFractionDigits: digits,
      minimumFractionDigits: 0,
    }),
  )
}

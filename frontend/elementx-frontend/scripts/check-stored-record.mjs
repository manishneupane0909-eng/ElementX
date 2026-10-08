// Checks the stored-record parser against the backend's real output and edge cases.
//   - Real readouts captured from the backend (scripts/fixtures) must parse and round-trip.
//   - Synthetic readouts cover every line the backend template can emit.
//   - Anything that is not the exact template (model prose, edited values) must be rejected.
// Usage: node scripts/check-stored-record.mjs   (needs Node 22.18+ for TypeScript type stripping)

import { readFileSync } from 'node:fs'
import assert from 'node:assert/strict'

const { parseStoredRecord, serializeStoredRecord, LARGEST_MOMENT_LIMIT, MAXIMA_LIMIT, SAMPLE_HEADING } =
  await import('../src/components/storedRecord.ts')

const LEAD =
  'The language model is not configured, so this is a direct readout of your stored research records (no interpretation applied).'
const fixture = (name) => readFileSync(new URL(`./fixtures/${name}`, import.meta.url), 'utf8')
let checks = 0
const ok = (condition, message) => {
  assert.ok(condition, message)
  checks += 1
}
const roundTrips = (text) => {
  const parsed = parseStoredRecord(text)
  ok(parsed !== null, 'expected the readout to parse')
  assert.equal(serializeStoredRecord(parsed), text)
  checks += 1
  return parsed
}

// ---- Real backend output -------------------------------------------------------------------
{
  const text = fixture('stored-record-sample.txt')
  const record = roundTrips(text)
  ok(record.kind === 'sample', 'sample readout')
  ok(record.experiments.length === 2, 'two experiments')
  const mag = record.experiments.find((e) => e.kind === 'magnetometry')
  const xrd = record.experiments.find((e) => e.kind === 'xrd')
  ok(mag && xrd, 'one magnetometry and one XRD experiment')
  ok(mag.segments.length === 10, `ten M-H segments (got ${mag.segments.length})`)

  // Every value must appear in the source text exactly as the backend wrote it.
  for (const row of mag.segments) {
    for (const value of [row.meanT, row.hcNegative, row.hcPositive, row.mrNegative, row.mrPositive, row.largestMoment]) {
      ok(text.includes(value), `value ${value} present in source`)
    }
    ok(row.normalized?.kind === 'value', 'normalized value present')
  }
  const first = mag.segments[0]
  assert.deepEqual(
    [first.segment, first.meanT, first.hcNegative, first.hcPositive, first.mrNegative, first.mrPositive, first.largestMoment],
    ['1', '55.14', '-154.5', '131.2', '-0.01538', '0.0174', '0.453'],
  )
  checks += 1
  assert.deepEqual(mag.mass, {
    status: 'instrument_metadata',
    resolvedMassMg: '3.5',
    source: 'instrument_header',
    normalizationAllowed: 'True',
  })
  checks += 1
  assert.deepEqual(xrd.maxima, [
    { twoTheta: '21', intensity: '100' },
    { twoTheta: '22.5', intensity: '80' },
  ])
  checks += 1
  // The limitation wording the backend prints with each value is preserved in the template.
  ok(text.split(`(${LARGEST_MOMENT_LIMIT})`).length - 1 === mag.segments.length, 'limitation on every segment')
  ok(text.includes(`(${MAXIMA_LIMIT})`), 'XRD limitation present')
}
{
  const record = roundTrips(fixture('stored-record-overview.txt'))
  ok(record.kind === 'overview' && record.samples.length >= 1, 'overview readout')
  ok(record.samples[0].name === 'Fe2CoGe annealed 48 h' && record.samples[0].experiments === '2', 'overview row')
}

// ---- Synthetic readouts covering every template line --------------------------------------
const body = (lines) => `${LEAD}\n\n${lines.join('\n')}`
const header = (count, extra = []) => [
  SAMPLE_HEADING,
  'Name: Sample (A) with (formula: X) in the name',
  'Formula: not recorded',
  'Notes: none',
  `Saved experiments: ${count}`,
  ...extra,
]

roundTrips(body(header(0, ['No experiments have been saved for this sample yet.'])))
roundTrips(body(['The user has no saved research Samples yet.']))
roundTrips(body(['RESEARCH SAMPLES (names only; select one for stored measurement values)']))

{
  const text = body([
    ...header(3),
    "- Magnetometry experiment 'o'brien run.dat' (pipeline v2, uploaded 2026-01-02 03:04:05)",
    '  M-H segments: 13, M-T segments: 0, normalization_available: False',
    '  Mass provenance: not available',
    '  User-confirmed mass (mg): 2.5',
    `  M-H segment 4 at mean T = not available K: Hc(-) = not available Oe, Hc(+) = 1.5e-05 Oe, Mr(-) = -0.0003 emu, Mr(+) = 0 emu; high-field saturation evidence = low; largest measured |moment| = 0.1 emu (${LARGEST_MOMENT_LIMIT})`,
    '    Mass-normalized values: not available (reason: needs_confirmation)',
    '    Warning: first warning, with a comma',
    '    Warning: second warning',
    '  (1 further M-H segments omitted)',
    '  File warning: file level warning',
    "- XRD experiment 'pattern.xy' (pipeline v1, uploaded 2026-01-02 03:04:05)",
    '  Measured pattern: 40 points, 2-theta 20 to 23.9 deg, intensity 10 to 100',
    '  Candidate intensity maxima: none detected',
    '  File warning: unsorted angles',
    "- Experiment 'x.bin' (type other): no summary available",
  ])
  const record = roundTrips(text)
  const mag = record.experiments[0]
  ok(mag.file === "o'brien run.dat", 'quote in file name preserved')
  ok(mag.mass === null && mag.confirmedMassMg === '2.5', 'mass provenance not available + confirmed mass')
  ok(mag.segments[0].hcNegative === 'not available', 'unavailable value kept verbatim')
  ok(mag.segments[0].hcPositive === '1.5e-05', 'exponent kept verbatim')
  ok(mag.segments[0].normalized.kind === 'unavailable' && mag.segments[0].normalized.reason === 'needs_confirmation', 'unavailable reason')
  assert.deepEqual(mag.segments[0].warnings, ['first warning, with a comma', 'second warning'])
  checks += 1
  ok(mag.omitted === '(1 further M-H segments omitted)', 'omitted note')
  ok(record.experiments[1].maxima === null && record.experiments[1].fileWarnings.length === 1, 'no maxima')
  ok(record.experiments[2].kind === 'other', 'unknown experiment type')
}
{
  const text = body([
    SAMPLE_HEADING,
    'Name: N',
    'Formula: F',
    'Notes: line one',
    'line two of the notes',
    '',
    'after a blank line',
    'Saved experiments: 0',
    'No experiments have been saved for this sample yet.',
  ])
  const record = roundTrips(text)
  ok(record.notes === 'line one\nline two of the notes\n\nafter a blank line', 'multi-line notes preserved')
}

// ---- Anything that is not the exact template is rejected -----------------------------------
const mustReject = (label, text) => {
  ok(parseStoredRecord(text) === null, `rejects: ${label}`)
}
mustReject('model prose with a bullet list', 'Here is a summary:\n\n- Hc is about 140 Oe\n- Mr is small\n')
mustReject('prose that imitates one template line', `${LEAD}\n\n- Fe2CoGe (formula: Fe2CoGe), many saved experiment(s)`)
mustReject('unknown line inside an experiment', body([...header(1), "- XRD experiment 'a.xy' (pipeline v1, uploaded t)", '  Interpretation: this is bcc iron']))
mustReject('missing lead sentence', header(0).join('\n'))
{
  const real = fixture('stored-record-sample.txt')
  mustReject('trailing text added', `${real}\nExtra commentary.`)
  mustReject('value that does not fit the template', real.replace('Hc(-) = -154.5 Oe', 'Hc(-) = -154.5 Oe (approx.)'))
  mustReject('limitation removed', real.replace(` (${LARGEST_MOMENT_LIMIT})`, ''))
  mustReject('different lead sentence', real.replace('direct readout', 'summary'))
}

console.log(`Stored-record parser OK: ${checks} checks passed.`)

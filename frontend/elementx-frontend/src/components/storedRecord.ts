/**
 * Reads the backend's stored-record readout into typed fields for display.
 *
 * The readout is a fixed, deterministic template (backend/services/research_context.py): when no
 * language model answers, the backend returns its stored records as plain text. Only that
 * template is parsed here; text from a language model is never passed to this module.
 *
 * Every field is kept as the exact string the backend wrote, so no number is re-formatted,
 * rounded or converted. `parseStoredRecord` also re-serialises what it parsed and compares that
 * with the input; if a single character differs, it returns null and the caller shows the text
 * unchanged. A parse can therefore never drop or alter a value.
 */

export interface MhSegmentRow {
  segment: string
  meanT: string
  hcNegative: string
  hcPositive: string
  mrNegative: string
  mrPositive: string
  evidence: string
  largestMoment: string
  /** Mass-normalized Mr(+): a value with its source, or the reason it is unavailable. */
  normalized:
    | { kind: 'value'; value: string; massSource: string }
    | { kind: 'unavailable'; reason: string }
    | null
  warnings: string[]
}

export interface MassProvenanceLine {
  status: string
  resolvedMassMg: string
  source: string
  normalizationAllowed: string
}

export interface MagnetometryRecord {
  kind: 'magnetometry'
  file: string
  pipeline: string
  uploaded: string
  mhSegments: string
  mtSegments: string
  normalizationAvailable: string
  /** null when the readout says mass provenance is not available. */
  mass: MassProvenanceLine | null
  confirmedMassMg: string | null
  segments: MhSegmentRow[]
  omitted: string | null
  fileWarnings: string[]
}

export interface XrdMaximum {
  twoTheta: string
  intensity: string
}

export interface XrdRecord {
  kind: 'xrd'
  file: string
  pipeline: string
  uploaded: string
  points: string
  twoThetaMin: string
  twoThetaMax: string
  intensityMin: string
  intensityMax: string
  /** null when the readout reports no detected maxima. */
  maxima: XrdMaximum[] | null
  fileWarnings: string[]
}

export interface OtherRecord {
  kind: 'other'
  file: string
  type: string
}

export type ExperimentRecord = MagnetometryRecord | XrdRecord | OtherRecord

export interface SampleReadout {
  kind: 'sample'
  lead: string
  name: string
  formula: string
  notes: string
  savedExperiments: string
  noExperiments: boolean
  experiments: ExperimentRecord[]
}

export interface OverviewReadout {
  kind: 'overview'
  lead: string
  /** The one-line heading the backend prints above the list. */
  heading: string
  samples: { name: string; formula: string; experiments: string }[]
}

export interface EmptyOverviewReadout {
  kind: 'empty-overview'
  lead: string
  text: string
}

export type StoredRecord = SampleReadout | OverviewReadout | EmptyOverviewReadout

const LEAD =
  'The language model is not configured, so this is a direct readout of your stored research records (no interpretation applied).'
export const SAMPLE_HEADING = 'RESEARCH SAMPLE (stored records; values are read from saved analyses)'
const OVERVIEW_HEADING = 'RESEARCH SAMPLES (names only; select one for stored measurement values)'
const EMPTY_OVERVIEW = 'The user has no saved research Samples yet.'
const NO_EXPERIMENTS = 'No experiments have been saved for this sample yet.'
export const LARGEST_MOMENT_LIMIT = 'a measured maximum, NOT a saturation magnetization'
export const MAXIMA_LIMIT =
  'local maxima only; NOT assigned to any phase, hkl, lattice or crystallite size'

const MAG_HEAD = /^- Magnetometry experiment '(.*)' \(pipeline v(.*), uploaded (.*)\)$/
const XRD_HEAD = /^- XRD experiment '(.*)' \(pipeline v(.*), uploaded (.*)\)$/
const OTHER_HEAD = /^- Experiment '(.*)' \(type (.*)\): no summary available$/
const MAG_SUMMARY = /^ {2}M-H segments: (.*), M-T segments: (.*), normalization_available: (.*)$/
const MASS_LINE =
  /^ {2}Mass provenance: status=(.*), resolved_mass_mg=(.*), source=(.*), normalization_allowed=(.*)$/
const MASS_NONE = '  Mass provenance: not available'
const CONFIRMED = /^ {2}User-confirmed mass \(mg\): (.*)$/
const MH_LINE = new RegExp(
  '^ {2}M-H segment (.*) at mean T = (.*) K: Hc\\(-\\) = (.*) Oe, Hc\\(\\+\\) = (.*) Oe, ' +
    'Mr\\(-\\) = (.*) emu, Mr\\(\\+\\) = (.*) emu; high-field saturation evidence = (.*); ' +
    `largest measured \\|moment\\| = (.*) emu \\(${LARGEST_MOMENT_LIMIT}\\)$`,
)
const NORM_VALUE = /^ {4}Mass-normalized Mr\(\+\) = (.*) emu\/g \(mass source: (.*)\)$/
const NORM_NONE = /^ {4}Mass-normalized values: not available \(reason: (.*)\)$/
const SEGMENT_WARNING = /^ {4}Warning: (.*)$/
const OMITTED = /^ {2}\(\d+ further M-H segments omitted\)$/
const FILE_WARNING = /^ {2}File warning: (.*)$/
const XRD_PATTERN =
  /^ {2}Measured pattern: (.*) points, 2-theta (.*) to (.*) deg, intensity (.*) to (.*)$/
const XRD_MAXIMA = new RegExp(`^ {2}Candidate intensity maxima \\(${MAXIMA_LIMIT}\\): (.*)$`)
const XRD_NONE = '  Candidate intensity maxima: none detected'
const MAXIMUM = /^(.*) deg \(I=(.*)\)$/
const OVERVIEW_ITEM = /^- (.*) \(formula: (.*)\), (\d+) saved experiment\(s\)$/

function splitContext(text: string): { lead: string; body: string } | null {
  const normalised = text.replace(/\r\n?/g, '\n')
  if (!normalised.startsWith(`${LEAD}\n\n`)) return null
  return { lead: LEAD, body: normalised.slice(LEAD.length + 2) }
}

function parseMaxima(list: string): XrdMaximum[] | null {
  const maxima: XrdMaximum[] = []
  for (const item of list.split(', ')) {
    const match = MAXIMUM.exec(item)
    if (!match) return null
    maxima.push({ twoTheta: match[1], intensity: match[2] })
  }
  return maxima
}

function parseExperiments(lines: string[]): ExperimentRecord[] | null {
  const records: ExperimentRecord[] = []
  let mag: MagnetometryRecord | null = null
  let xrd: XrdRecord | null = null

  for (const line of lines) {
    let m: RegExpExecArray | null

    if ((m = MAG_HEAD.exec(line))) {
      mag = {
        kind: 'magnetometry',
        file: m[1],
        pipeline: m[2],
        uploaded: m[3],
        mhSegments: '',
        mtSegments: '',
        normalizationAvailable: '',
        mass: null,
        confirmedMassMg: null,
        segments: [],
        omitted: null,
        fileWarnings: [],
      }
      xrd = null
      records.push(mag)
    } else if ((m = XRD_HEAD.exec(line))) {
      xrd = {
        kind: 'xrd',
        file: m[1],
        pipeline: m[2],
        uploaded: m[3],
        points: '',
        twoThetaMin: '',
        twoThetaMax: '',
        intensityMin: '',
        intensityMax: '',
        maxima: null,
        fileWarnings: [],
      }
      mag = null
      records.push(xrd)
    } else if ((m = OTHER_HEAD.exec(line))) {
      mag = null
      xrd = null
      records.push({ kind: 'other', file: m[1], type: m[2] })
    } else if (mag && (m = MAG_SUMMARY.exec(line))) {
      mag.mhSegments = m[1]
      mag.mtSegments = m[2]
      mag.normalizationAvailable = m[3]
    } else if (mag && (m = MASS_LINE.exec(line))) {
      mag.mass = {
        status: m[1],
        resolvedMassMg: m[2],
        source: m[3],
        normalizationAllowed: m[4],
      }
    } else if (mag && line === MASS_NONE) {
      mag.mass = null
    } else if (mag && (m = CONFIRMED.exec(line))) {
      mag.confirmedMassMg = m[1]
    } else if (mag && (m = MH_LINE.exec(line))) {
      mag.segments.push({
        segment: m[1],
        meanT: m[2],
        hcNegative: m[3],
        hcPositive: m[4],
        mrNegative: m[5],
        mrPositive: m[6],
        evidence: m[7],
        largestMoment: m[8],
        normalized: null,
        warnings: [],
      })
    } else if (mag && mag.segments.length > 0 && (m = NORM_VALUE.exec(line))) {
      mag.segments[mag.segments.length - 1].normalized = {
        kind: 'value',
        value: m[1],
        massSource: m[2],
      }
    } else if (mag && mag.segments.length > 0 && (m = NORM_NONE.exec(line))) {
      mag.segments[mag.segments.length - 1].normalized = { kind: 'unavailable', reason: m[1] }
    } else if (mag && mag.segments.length > 0 && (m = SEGMENT_WARNING.exec(line))) {
      mag.segments[mag.segments.length - 1].warnings.push(m[1])
    } else if (mag && OMITTED.test(line)) {
      mag.omitted = line.trim()
    } else if (mag && (m = FILE_WARNING.exec(line))) {
      mag.fileWarnings.push(m[1])
    } else if (xrd && (m = XRD_PATTERN.exec(line))) {
      xrd.points = m[1]
      xrd.twoThetaMin = m[2]
      xrd.twoThetaMax = m[3]
      xrd.intensityMin = m[4]
      xrd.intensityMax = m[5]
    } else if (xrd && (m = XRD_MAXIMA.exec(line))) {
      const maxima = parseMaxima(m[1])
      if (!maxima) return null
      xrd.maxima = maxima
    } else if (xrd && line === XRD_NONE) {
      xrd.maxima = null
    } else if (xrd && (m = FILE_WARNING.exec(line))) {
      xrd.fileWarnings.push(m[1])
    } else {
      return null
    }
  }
  return records
}

/** Writes parsed fields back out in the backend's template, for the round-trip check. */
export function serializeStoredRecord(record: StoredRecord): string {
  const lines: string[] = []
  if (record.kind === 'empty-overview') {
    lines.push(record.text)
  } else if (record.kind === 'overview') {
    lines.push(record.heading)
    for (const sample of record.samples) {
      lines.push(`- ${sample.name} (formula: ${sample.formula}), ${sample.experiments} saved experiment(s)`)
    }
  } else {
    lines.push(
      SAMPLE_HEADING,
      `Name: ${record.name}`,
      `Formula: ${record.formula}`,
      `Notes: ${record.notes}`,
      `Saved experiments: ${record.savedExperiments}`,
    )
    if (record.noExperiments) lines.push(NO_EXPERIMENTS)
    for (const experiment of record.experiments) {
      if (experiment.kind === 'other') {
        lines.push(`- Experiment '${experiment.file}' (type ${experiment.type}): no summary available`)
      } else if (experiment.kind === 'xrd') {
        lines.push(
          `- XRD experiment '${experiment.file}' (pipeline v${experiment.pipeline}, uploaded ${experiment.uploaded})`,
          `  Measured pattern: ${experiment.points} points, 2-theta ${experiment.twoThetaMin} to ${experiment.twoThetaMax} deg, intensity ${experiment.intensityMin} to ${experiment.intensityMax}`,
          experiment.maxima
            ? `  Candidate intensity maxima (${MAXIMA_LIMIT}): ${experiment.maxima
                .map((maximum) => `${maximum.twoTheta} deg (I=${maximum.intensity})`)
                .join(', ')}`
            : XRD_NONE,
          ...experiment.fileWarnings.map((warning) => `  File warning: ${warning}`),
        )
      } else {
        lines.push(
          `- Magnetometry experiment '${experiment.file}' (pipeline v${experiment.pipeline}, uploaded ${experiment.uploaded})`,
          `  M-H segments: ${experiment.mhSegments}, M-T segments: ${experiment.mtSegments}, normalization_available: ${experiment.normalizationAvailable}`,
          experiment.mass
            ? `  Mass provenance: status=${experiment.mass.status}, resolved_mass_mg=${experiment.mass.resolvedMassMg}, source=${experiment.mass.source}, normalization_allowed=${experiment.mass.normalizationAllowed}`
            : MASS_NONE,
        )
        if (experiment.confirmedMassMg !== null) {
          lines.push(`  User-confirmed mass (mg): ${experiment.confirmedMassMg}`)
        }
        for (const row of experiment.segments) {
          lines.push(
            `  M-H segment ${row.segment} at mean T = ${row.meanT} K: Hc(-) = ${row.hcNegative} Oe, Hc(+) = ${row.hcPositive} Oe, Mr(-) = ${row.mrNegative} emu, Mr(+) = ${row.mrPositive} emu; high-field saturation evidence = ${row.evidence}; largest measured |moment| = ${row.largestMoment} emu (${LARGEST_MOMENT_LIMIT})`,
          )
          if (row.normalized?.kind === 'value') {
            lines.push(
              `    Mass-normalized Mr(+) = ${row.normalized.value} emu/g (mass source: ${row.normalized.massSource})`,
            )
          } else if (row.normalized?.kind === 'unavailable') {
            lines.push(
              `    Mass-normalized values: not available (reason: ${row.normalized.reason})`,
            )
          }
          for (const warning of row.warnings) lines.push(`    Warning: ${warning}`)
        }
        if (experiment.omitted) lines.push(`  ${experiment.omitted}`)
        for (const warning of experiment.fileWarnings) lines.push(`  File warning: ${warning}`)
      }
    }
  }
  return `${LEAD}\n\n${lines.join('\n')}`
}

function parseBody(lead: string, body: string): StoredRecord | null {
  const lines = body.split('\n')

  if (body === EMPTY_OVERVIEW) {
    return { kind: 'empty-overview', lead, text: EMPTY_OVERVIEW }
  }

  if (lines[0] === OVERVIEW_HEADING) {
    const samples: OverviewReadout['samples'] = []
    for (const line of lines.slice(1)) {
      const match = OVERVIEW_ITEM.exec(line)
      if (!match) return null
      samples.push({ name: match[1], formula: match[2], experiments: match[3] })
    }
    return { kind: 'overview', lead, heading: OVERVIEW_HEADING, samples }
  }

  if (lines[0] !== SAMPLE_HEADING) return null
  const name = /^Name: (.*)$/.exec(lines[1] ?? '')
  const formula = /^Formula: (.*)$/.exec(lines[2] ?? '')
  if (!name || !formula || !(lines[3] ?? '').startsWith('Notes: ')) return null

  // Notes are free text and may span several lines; they end at the "Saved experiments" line.
  let countLine = 4
  while (countLine < lines.length && !/^Saved experiments: \d+$/.test(lines[countLine])) {
    countLine += 1
  }
  if (countLine >= lines.length) return null
  const notes = [lines[3].slice('Notes: '.length), ...lines.slice(4, countLine)].join('\n')
  const savedExperiments = lines[countLine].slice('Saved experiments: '.length)

  let rest = lines.slice(countLine + 1)
  let noExperiments = false
  if (rest[0] === NO_EXPERIMENTS) {
    noExperiments = true
    rest = rest.slice(1)
  }
  const experiments = parseExperiments(rest)
  if (!experiments) return null

  return {
    kind: 'sample',
    lead,
    name: name[1],
    formula: formula[1],
    notes,
    savedExperiments,
    noExperiments,
    experiments,
  }
}

/**
 * Parses the backend's stored-record readout. Returns null unless the text matches the template
 * exactly and re-serialises to the identical text.
 */
export function parseStoredRecord(text: string): StoredRecord | null {
  const split = splitContext(text)
  if (!split) return null
  const record = parseBody(split.lead, split.body)
  if (!record) return null
  return serializeStoredRecord(record) === text.replace(/\r\n?/g, '\n') ? record : null
}

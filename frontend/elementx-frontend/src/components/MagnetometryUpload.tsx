import { useEffect, useState } from 'react'
import {
  analyzeMagnetometry,
  createSampleExperiment,
  MagnetApiError,
  type SavedMagnetometryExperiment,
  type HighFieldAnalysis,
  type HysteresisAnalysis,
  type MagnetometryAnalyzeResult,
  type MassProvenance,
  type MeasurementSegment,
  type MeasurementSegmentData,
  type MHAnalysisEntry,
  type NormalizedMoment,
  type NormalizedResults,
} from '../services/magnetApi'
import ScientificPlot, { type PlotPoint, type PlotReferenceLine } from './ScientificPlot'
import Button from './ui/Button'
import DataList, { ResultRow } from './ui/DataList'
import Disclosure from './ui/Disclosure'
import FileUploadBar from './ui/FileUploadBar'
import Notice from './ui/Notice'
import Section from './ui/Section'
import TextField from './ui/TextField'
import { formatNumber } from '../utils/number'

const MASS_CONFIRMATION_STATUSES = new Set([
  'conflict',
  'needs_confirmation',
  'missing',
])

function formatRange(values: number[] | undefined, digits: number, unit: string): string {
  if (!values || values.length < 2) {
    return '—'
  }
  return `${formatNumber(values[0], digits)} – ${formatNumber(values[1], digits)} ${unit}`
}

function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) {
    return '—'
  }
  return `${formatNumber(seconds, 1)} s`
}

function errorMessage(err: unknown, fallback: string): string {
  if (err instanceof MagnetApiError) {
    return err.detail
  }
  if (err instanceof Error) {
    return err.message
  }
  return fallback
}

function seriesPoints(
  xValues: number[] | undefined,
  yValues: number[] | undefined,
): PlotPoint[] {
  if (!xValues || !yValues || xValues.length === 0 || xValues.length !== yValues.length) {
    return []
  }
  return xValues.map((x, index) => ({ x, y: yValues[index] }))
}

function mhReferenceLines(hysteresis: HysteresisAnalysis): PlotReferenceLine[] {
  const lines: PlotReferenceLine[] = []
  if (hysteresis.Hc_negative_Oe !== null) {
    lines.push({ x: hysteresis.Hc_negative_Oe, label: 'Hc−', side: 'left' })
  }
  if (hysteresis.Hc_positive_Oe !== null) {
    lines.push({ x: hysteresis.Hc_positive_Oe, label: 'Hc+', side: 'right' })
  }
  return lines
}

function MeasuredCurve({
  data,
  xKey,
  xLabel,
  xUnit,
  referenceX,
  title,
  exportName,
}: {
  data: MeasurementSegmentData | undefined
  xKey: 'field_Oe' | 'temperature_K'
  xLabel: string
  xUnit: string
  referenceX?: PlotReferenceLine[]
  title: string
  exportName: string
}) {
  const points = seriesPoints(data?.[xKey], data?.moment_emu)
  return (
    <ScientificPlot
      points={points}
      xLabel={xLabel}
      yLabel="Magnetic Moment"
      xUnit={xUnit}
      yUnit="emu"
      referenceX={referenceX}
      title={title}
      exportName={exportName}
    />
  )
}

function fileStem(filename: string | null | undefined): string {
  return (filename ?? 'magnetometry').replace(/\.[^.]+$/, '')
}

function WarningList({ warnings }: { warnings: string[] }) {
  if (warnings.length === 0) {
    return null
  }

  return (
    <div className="note note--warn">
      <ul>
        {warnings.map((warning) => (
          <li key={warning}>{warning}</li>
        ))}
      </ul>
    </div>
  )
}

const MASS_SECTION_ID = 'sample-mass'

function SampleMassSection({
  provenance,
  confirmedMass,
  onConfirmedMassChange,
  onReanalyze,
  reanalyzeDisabled,
  allowConfirmation = true,
}: {
  provenance: MassProvenance
  confirmedMass: string
  onConfirmedMassChange: (value: string) => void
  onReanalyze: () => void
  reanalyzeDisabled: boolean
  allowConfirmation?: boolean
}) {
  const needsConfirmation = MASS_CONFIRMATION_STATUSES.has(provenance.resolution_status)
  const provenanceNeedsAttention =
    needsConfirmation ||
    provenance.sources_agree === false ||
    provenance.filename_masses_ambiguous
  const candidateCount = provenance.mass_candidates.length

  return (
    <div id={MASS_SECTION_ID} tabIndex={-1} className="mass-section">
      <Section
        title="Sample mass"
        description="ElementX does not silently choose a mass when sources disagree; every candidate is listed under mass provenance."
      >
        {needsConfirmation && (
          <div className="note note--warn" role="alert">
            Sample-mass resolution is <strong>{provenance.resolution_status}</strong>.
            Mass-normalized magnetization is blocked until a mass is confirmed.
          </div>
        )}

        <div className="mass-summary">
          <DataList label="Sample mass resolution" columns>
            <ResultRow
              label="Resolved mass"
              value={
                provenance.resolved_mass_mg === null
                  ? 'Not resolved'
                  : `${formatNumber(provenance.resolved_mass_mg, 4)} mg`
              }
            />
            <ResultRow
              label="Resolved source"
              value={provenance.resolved_source?.replaceAll('_', ' ') ?? '—'}
            />
            <ResultRow label="Resolution status" value={provenance.resolution_status} />
            <ResultRow
              label="Normalization allowed"
              value={provenance.normalization_allowed ? 'Yes' : 'No'}
            />
          </DataList>
        </div>

        <WarningList warnings={provenance.warnings} />

        <Disclosure
          defaultOpen={provenanceNeedsAttention}
          summary={`Mass provenance · ${candidateCount} candidate${candidateCount === 1 ? '' : 's'}`}
        >
          {candidateCount === 0 ? (
            <p className="empty-hint">No mass candidates were reported.</p>
          ) : (
            <div className="table-wrap mass-table">
              <table className="data-table">
                <caption className="sr-only">Candidate sample masses</caption>
                <thead>
                  <tr>
                    <th scope="col" className="num">
                      Mass
                    </th>
                    <th scope="col">Source</th>
                    <th scope="col">Key</th>
                    <th scope="col">Raw value</th>
                  </tr>
                </thead>
                <tbody>
                  {provenance.mass_candidates.map((candidate, index) => (
                    <tr key={`${candidate.source}-${candidate.raw_value}-${index}`}>
                      <td className="num mono">
                        {formatNumber(candidate.value_mg, 4)} {candidate.unit}
                      </td>
                      <td>{candidate.source.replaceAll('_', ' ')}</td>
                      <td className="mono cell-muted">{candidate.source_key ?? '—'}</td>
                      <td className="mono cell-muted">{candidate.raw_value}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <DataList label="Mass source agreement" columns>
            <ResultRow
              label="Sources agree"
              value={
                provenance.sources_agree === null
                  ? '—'
                  : provenance.sources_agree
                    ? 'Yes'
                    : 'No'
              }
            />
            <ResultRow
              label="Filename masses ambiguous"
              value={provenance.filename_masses_ambiguous ? 'Yes' : 'No'}
            />
          </DataList>
        </Disclosure>

        {needsConfirmation && allowConfirmation && (
          <div className="control-row mass-confirm">
            <div className="form-field form-field--md">
              <TextField
                label="Confirmed sample mass (mg)"
                type="number"
                step="any"
                min="0"
                inputMode="decimal"
                placeholder="Mass to use, in mg"
                value={confirmedMass}
                onChange={(event) => onConfirmedMassChange(event.target.value)}
              />
            </div>
            <Button variant="primary" onClick={onReanalyze} disabled={reanalyzeDisabled}>
              Reanalyze with confirmed mass
            </Button>
          </div>
        )}
      </Section>
    </div>
  )
}

function MtSegmentFigure({
  segment,
  index,
  fileName,
}: {
  segment: MeasurementSegment
  index: number
  fileName: string
}) {
  return (
    <article className="figure-block">
      <div className="figure__title">
        <h3 className="figure__heading">M-T segment {index}</h3>
        <p className="muted figure__sub">
          Identification only. No Curie temperature is calculated from this segment.
        </p>
      </div>
      <div className="figure">
        <MeasuredCurve
          data={segment.data}
          xKey="temperature_K"
          xLabel="Temperature"
          xUnit="K"
          title={`M-T segment ${index}`}
          exportName={`${fileStem(fileName)}_MT_segment_${index}`}
        />
        <div className="figure__side">
          <DataList label={`M-T segment ${index} values`}>
            <ResultRow
              label="Temperature range"
              value={formatRange(segment.temperature_range_K, 3, 'K')}
            />
            <ResultRow
              label="Mean field"
              value={`${formatNumber(segment.mean_field_Oe, 3)} Oe`}
            />
            <ResultRow label="Valid points" value={String(segment.valid_point_count)} />
            <ResultRow label="Confidence" value={formatNumber(segment.confidence, 3)} />
          </DataList>
          <WarningList warnings={segment.warnings} />
          <Disclosure summary="Segment details">
            <DataList label={`M-T segment ${index} details`}>
              <ResultRow label="Segment index" value={String(index)} />
              <ResultRow label="Point count" value={String(segment.point_count)} />
              <ResultRow
                label="Field range"
                value={formatRange(segment.field_range_Oe, 3, 'Oe')}
              />
              <ResultRow label="Duration" value={formatDuration(segment.duration_sec)} />
            </DataList>
          </Disclosure>
        </div>
      </div>
    </article>
  )
}

function HysteresisBlock({ hysteresis }: { hysteresis: HysteresisAnalysis }) {
  return (
    <Section level={3} title="Hysteresis">
      <DataList label="Hysteresis values">
        <ResultRow label="Hc negative" value={`${formatNumber(hysteresis.Hc_negative_Oe, 3)} Oe`} />
        <ResultRow label="Hc positive" value={`${formatNumber(hysteresis.Hc_positive_Oe, 3)} Oe`} />
        <ResultRow
          label="Coercive half-width"
          value={`${formatNumber(hysteresis.coercive_half_width_Oe, 3)} Oe`}
        />
        <ResultRow
          label="Coercive center shift"
          value={`${formatNumber(hysteresis.coercive_center_shift_Oe, 3)} Oe`}
        />
        <ResultRow label="Mr negative" value={`${formatNumber(hysteresis.Mr_negative_emu, 6)} emu`} />
        <ResultRow label="Mr positive" value={`${formatNumber(hysteresis.Mr_positive_emu, 6)} emu`} />
        <ResultRow label="Field range" value={formatRange(hysteresis.field_range_Oe, 1, 'Oe')} />
      </DataList>
    </Section>
  )
}

function HighFieldBlock({
  highField,
  diagnosticsOpen,
  onDiagnosticsOpenChange,
}: {
  highField: HighFieldAnalysis
  diagnosticsOpen: boolean
  onDiagnosticsOpenChange: (open: boolean) => void
}) {
  return (
    <Section level={3} title="High field">
      <p className="evidence-caption">
        High-field saturation evidence:{' '}
        <span className={`evidence-badge evidence-badge--${highField.saturation_evidence_quality}`}>
          {highField.saturation_evidence_quality}
        </span>
      </p>
      <p className="muted evidence-note">
        This is the quality of high-field evidence returned by the backend, not a
        determination that the sample is saturated.
      </p>
      <DataList label="High-field values">
        <ResultRow
          label="Maximum measured |moment|"
          value={`${formatNumber(highField.maximum_absolute_measured_moment_emu, 6)} emu`}
        />
      </DataList>
      <Disclosure
        summary="High-field diagnostics"
        open={diagnosticsOpen}
        onOpenChange={onDiagnosticsOpenChange}
      >
        <DataList label="High-field diagnostics">
          <ResultRow
            label="Maximum positive field"
            value={`${formatNumber(highField.maximum_positive_field_Oe, 1)} Oe`}
          />
          <ResultRow
            label="Maximum negative field"
            value={`${formatNumber(highField.maximum_negative_field_Oe, 1)} Oe`}
          />
          <ResultRow
            label="Moment at max positive field"
            value={`${formatNumber(highField.moment_at_max_positive_field_emu, 6)} emu`}
          />
          <ResultRow
            label="Moment at max negative field"
            value={`${formatNumber(highField.moment_at_max_negative_field_emu, 6)} emu`}
          />
          <ResultRow
            label="Positive high-field slope"
            value={`${formatNumber(highField.positive_high_field_slope_emu_per_Oe, 10)} emu/Oe`}
          />
          <ResultRow
            label="Negative high-field slope"
            value={`${formatNumber(highField.negative_high_field_slope_emu_per_Oe, 10)} emu/Oe`}
          />
          <ResultRow
            label="Positive R²"
            value={formatNumber(highField.positive_high_field_r_squared, 4)}
          />
          <ResultRow
            label="Negative R²"
            value={formatNumber(highField.negative_high_field_r_squared, 4)}
          />
        </DataList>
      </Disclosure>
    </Section>
  )
}

function NormalizedValue({
  label,
  value,
}: {
  label: string
  value: NormalizedMoment | null
}) {
  if (!value) {
    return <ResultRow label={label} value="—" />
  }

  return (
    <ResultRow
      label={label}
      value={
        <span className="unit-pair">
          <span>{formatNumber(value.specific_magnetization_emu_per_g, 4)} emu/g</span>
          <span aria-hidden="true">·</span>
          <span>{formatNumber(value.specific_magnetization_Am2_per_kg, 4)} A·m²/kg</span>
        </span>
      }
    />
  )
}

function NormalizedBlock({ normalized }: { normalized: NormalizedResults }) {
  if (!normalized.available) {
    return (
      <div className="note">
        Mass-normalized magnetization is not available
        {normalized.reason ? ` (${normalized.reason})` : ''}.
        {MASS_CONFIRMATION_STATUSES.has(normalized.reason ?? '')
          ? ' Confirm the sample mass below and reanalyze if you want specific magnetization.'
          : null}
      </div>
    )
  }

  return (
    <Section
      level={3}
      title="Mass-normalized magnetization"
      description="Specific magnetization from the backend. These values are mass-normalized measured moments, not a fitted saturation quantity."
    >
      <DataList label="Mass-normalized values">
        <NormalizedValue label="Specific remanent magnetization (−)" value={normalized.Mr_negative} />
        <NormalizedValue label="Specific remanent magnetization (+)" value={normalized.Mr_positive} />
        <NormalizedValue
          label="Maximum measured specific magnetization"
          value={normalized.maximum_measured_moment}
        />
        <NormalizedValue
          label="Specific magnetization at max +H"
          value={normalized.moment_at_max_positive_field}
        />
        <NormalizedValue
          label="Specific magnetization at max −H"
          value={normalized.moment_at_max_negative_field}
        />
      </DataList>
    </Section>
  )
}

function MhLoopFigure({
  entry,
  segment,
  fileName,
  diagnosticsOpen,
  onDiagnosticsOpenChange,
}: {
  entry: MHAnalysisEntry
  segment: MeasurementSegment | undefined
  fileName: string
  diagnosticsOpen: boolean
  onDiagnosticsOpenChange: (open: boolean) => void
}) {
  const temperature = entry.analysis.segment.mean_temperature_K
  const loopWarnings = [
    ...entry.analysis.warnings,
    ...entry.analysis.hysteresis.warnings,
    ...entry.analysis.high_field.warnings,
  ]

  return (
    <article className="figure-block">
      <div className="figure__title">
        <h3 className="figure__heading">
          M-H loop — approximately {formatNumber(temperature, 1)} K
        </h3>
        <span className="muted figure__sub">segment {entry.segment_index}</span>
      </div>

      <div className="figure">
        <MeasuredCurve
          data={segment?.data}
          xKey="field_Oe"
          xLabel="Magnetic Field"
          xUnit="Oe"
          referenceX={mhReferenceLines(entry.analysis.hysteresis)}
          title={`M-H loop, segment ${entry.segment_index} (≈ ${formatNumber(temperature, 1)} K)`}
          exportName={`${fileStem(fileName)}_MH_segment_${entry.segment_index}`}
        />
        <div className="figure__side">
          <HysteresisBlock hysteresis={entry.analysis.hysteresis} />
          <HighFieldBlock
            highField={entry.analysis.high_field}
            diagnosticsOpen={diagnosticsOpen}
            onDiagnosticsOpenChange={onDiagnosticsOpenChange}
          />
        </div>
      </div>

      {loopWarnings.length > 0 && <WarningList warnings={loopWarnings} />}
      <NormalizedBlock normalized={entry.analysis.normalized} />
    </article>
  )
}

function MhLoops({ result }: { result: MagnetometryAnalyzeResult }) {
  const [selected, setSelected] = useState(0)
  const [diagnosticsOpen, setDiagnosticsOpen] = useState(false)
  const entries = result.mh_analyses
  const index = Math.min(selected, Math.max(entries.length - 1, 0))
  const entry = entries[index]

  return (
    <Section title="M-H loops">
      {entries.length === 0 ? (
        <p className="empty-hint">No M-H analyses were returned.</p>
      ) : (
        <div className="stack">
          {entries.length > 1 && (
            <div className="loop-picker" role="group" aria-label="Choose an M-H loop by temperature">
              {entries.map((candidate, candidateIndex) => (
                <button
                  key={candidate.segment_index}
                  type="button"
                  className="loop-picker__btn"
                  aria-pressed={candidateIndex === index}
                  onClick={() => setSelected(candidateIndex)}
                >
                  {formatNumber(candidate.analysis.segment.mean_temperature_K, 1)} K
                </button>
              ))}
            </div>
          )}
          <MhLoopFigure
            key={entry.segment_index}
            entry={entry}
            segment={result.segmentation.segments[entry.segment_index]}
            fileName={result.file.filename ?? 'magnetometry'}
            diagnosticsOpen={diagnosticsOpen}
            onDiagnosticsOpenChange={setDiagnosticsOpen}
          />
        </div>
      )}
    </Section>
  )
}

export interface MagnetometryUploadProps {
  sampleId?: string
  initialResult?: MagnetometryAnalyzeResult | null
  readOnly?: boolean
  onSaved?: (saved: SavedMagnetometryExperiment) => void
}

export default function MagnetometryUpload({
  sampleId,
  initialResult = null,
  readOnly = false,
  onSaved,
}: MagnetometryUploadProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [confirmedMass, setConfirmedMass] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<MagnetometryAnalyzeResult | null>(
    initialResult ?? null,
  )

  useEffect(() => {
    if (initialResult) {
      setResult(initialResult)
      setError(null)
    }
  }, [initialResult])

  const persistMode = Boolean(sampleId) && !readOnly
  const allowConfirmation = !readOnly && !persistMode

  const runAnalysis = async (file: File, userConfirmedMassMg?: number) => {
    setLoading(true)
    setError(null)

    try {
      if (sampleId) {
        const saved = await createSampleExperiment(sampleId, file, userConfirmedMassMg)
        if (persistMode) {
          // The sample view opens the saved experiment; keep this form ready for another file.
          setSelectedFile(null)
        } else {
          setResult(saved.analysis_json)
        }
        onSaved?.(saved)
      } else {
        const analysis = await analyzeMagnetometry(file, userConfirmedMassMg)
        setResult(analysis)
      }
    } catch (err) {
      setResult(null)
      setError(errorMessage(err, 'Magnetometry analysis failed.'))
    } finally {
      setLoading(false)
    }
  }

  const handleFileChange = (file: File | null) => {
    setSelectedFile(file)
    setResult(null)
    setError(null)
    setConfirmedMass('')
  }

  const handleAnalyze = async () => {
    if (!selectedFile) {
      setError('Choose a Quantum Design .dat file to analyze.')
      return
    }

    if (!selectedFile.name.toLowerCase().endsWith('.dat')) {
      setError('Only .dat files are supported.')
      return
    }

    await runAnalysis(selectedFile)
  }

  const handleReanalyze = async () => {
    if (!selectedFile) {
      setError('Choose a Quantum Design .dat file to analyze.')
      return
    }

    const mass = Number(confirmedMass)
    if (!Number.isFinite(mass) || mass <= 0) {
      setError('Enter a finite, positive confirmed mass in mg.')
      return
    }

    await runAnalysis(selectedFile, mass)
  }

  const mtSegments = result
    ? result.segmentation.segments
        .map((segment, index) => ({ segment, index }))
        .filter(({ segment }) => segment.type === 'M-T')
    : []
  const massProvenance = result?.mh_analyses[0]?.analysis.mass_provenance ?? null
  const massNeedsConfirmation =
    massProvenance !== null && MASS_CONFIRMATION_STATUSES.has(massProvenance.resolution_status)

  const jumpToMass = () => {
    const target = document.getElementById(MASS_SECTION_ID)
    target?.scrollIntoView({ block: 'start' })
    target?.focus({ preventScroll: true })
  }

  return (
    <div className="mag-view">
      {!readOnly && !persistMode && (
        <p className="page-intro">
          Analyze a Quantum Design magnetometry file. Results are not saved from this view; to
          keep an analysis, add the file to a sample under Samples.
        </p>
      )}
      {!readOnly && (
        <div className="upload-block">
          <FileUploadBar
            label="Quantum Design .dat file"
            accept=".dat,application/octet-stream"
            file={selectedFile}
            onFileChange={handleFileChange}
            chooseLabel="Choose .dat file"
            actionLabel={
              loading
                ? persistMode
                  ? 'Saving…'
                  : 'Analyzing…'
                : persistMode
                  ? 'Upload & save'
                  : 'Analyze'
            }
            onAction={() => void handleAnalyze()}
            busy={loading}
            hint={
              persistMode
                ? 'VersaLab / MultiVu export. The existing magnetometry pipeline analyzes it, and the raw file and analysis are saved under this sample.'
                : 'VersaLab / MultiVu export, analyzed by the backend pipeline.'
            }
          />
        </div>
      )}

      {loading && (
        <Notice kind="loading">
          Analyzing the experiment. This uses the backend magnetometry pipeline; no quantities
          are calculated in the browser.
        </Notice>
      )}

      {error && <Notice kind="error">{error}</Notice>}

      {!readOnly && !persistMode && !result && !loading && (
        <div className="pre-upload">
          <p className="pre-upload__summary">
            The backend reports M-T and M-H segments, coercivity, remanence, high-field evidence
            and every candidate sample mass. It does not calculate a Curie temperature or a
            saturation magnetization.
          </p>
          <Disclosure summary="What the analysis reports, and its limits">
            <ul className="output-list">
              <li>
                Everything is computed by the backend pipeline from the measured data in the file;
                nothing is calculated in the browser.
              </li>
              <li>The M-H and M-T segments found in the file, with the file metadata.</li>
              <li>
                Every candidate sample mass in the header, with its source. Normalization stays
                blocked until the mass is unambiguous or confirmed.
              </li>
              <li>
                M-T segments: measured moment against temperature. Identification only; no Curie
                temperature is calculated.
              </li>
              <li>
                M-H loops: measured moment against field, with coercive field, remanence and the
                quality of high-field evidence. The largest measured moment is not reported as a
                saturation magnetization.
              </li>
            </ul>
          </Disclosure>
        </div>
      )}

      {result && (
        <div className="page">
          <Section title="Experiment">
            <DataList label="Experiment summary" columns>
              <ResultRow label="Filename" value={result.file.filename ?? '—'} />
              <ResultRow label="Material" value={result.metadata.SAMPLE_MATERIAL || '—'} />
              <ResultRow
                label="Sample mass (instrument metadata)"
                value={
                  result.metadata.SAMPLE_MASS
                    ? `${result.metadata.SAMPLE_MASS} (header string)`
                    : '—'
                }
              />
              <ResultRow label="M-H segments" value={String(result.summary.mh_segment_count)} />
              <ResultRow label="M-T segments" value={String(result.summary.mt_segment_count)} />
              <ResultRow
                label="Normalization available"
                value={result.summary.normalization_available ? 'Yes' : 'No'}
              />
            </DataList>
            <Disclosure summary="File and pipeline details">
              <DataList label="File and pipeline details" columns>
                <ResultRow label="Format" value={result.file.format} />
                <ResultRow
                  label="Total segments"
                  value={String(result.segmentation.segment_count)}
                />
                <ResultRow
                  label="Unknown segments"
                  value={String(result.summary.unknown_segment_count)}
                />
                <ResultRow label="Analysis version" value={result.analysis_version ?? '—'} />
              </DataList>
            </Disclosure>
            <WarningList warnings={result.warnings} />
            <WarningList warnings={result.segmentation.warnings} />
            {massNeedsConfirmation && (
              <div className="note note--warn">
                Sample mass needs confirmation, so mass-normalized values are blocked.{' '}
                <Button variant="link" onClick={jumpToMass}>
                  Go to sample mass
                </Button>
              </div>
            )}
          </Section>

          <Section title="M-T segments">
            {mtSegments.length === 0 ? (
              <p className="empty-hint">No M-T segments were identified.</p>
            ) : (
              <div className="stack">
                {mtSegments.map(({ segment, index }) => (
                  <MtSegmentFigure
                    key={index}
                    segment={segment}
                    index={index}
                    fileName={result.file.filename ?? 'magnetometry'}
                  />
                ))}
              </div>
            )}
          </Section>

          <MhLoops result={result} />

          {massProvenance && (
            <SampleMassSection
              provenance={massProvenance}
              confirmedMass={confirmedMass}
              onConfirmedMassChange={setConfirmedMass}
              onReanalyze={() => void handleReanalyze()}
              reanalyzeDisabled={loading}
              allowConfirmation={allowConfirmation}
            />
          )}
        </div>
      )}
    </div>
  )
}

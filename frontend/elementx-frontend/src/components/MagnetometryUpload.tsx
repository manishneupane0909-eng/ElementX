import { useEffect, useId, useState } from 'react'
import {
  analyzeMagnetometry,
  createSampleExperiment,
  MagnetApiError,
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

const MASS_CONFIRMATION_STATUSES = new Set([
  'conflict',
  'needs_confirmation',
  'missing',
])

function formatNumber(value: number | null | undefined, digits = 3): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '—'
  }
  return value.toLocaleString(undefined, {
    maximumFractionDigits: digits,
    minimumFractionDigits: 0,
  })
}

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
    lines.push({ x: hysteresis.Hc_negative_Oe, label: 'Hc−' })
  }
  if (hysteresis.Hc_positive_Oe !== null) {
    lines.push({ x: hysteresis.Hc_positive_Oe, label: 'Hc+' })
  }
  return lines
}

function MeasuredCurve({
  data,
  xKey,
  xLabel,
  xUnit,
  referenceX,
}: {
  data: MeasurementSegmentData | undefined
  xKey: 'field_Oe' | 'temperature_K'
  xLabel: string
  xUnit: string
  referenceX?: PlotReferenceLine[]
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
    />
  )
}

function ResultRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="result-row">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  )
}

function WarningList({ warnings }: { warnings: string[] }) {
  if (warnings.length === 0) {
    return null
  }

  return (
    <ul className="magnetometry-warnings">
      {warnings.map((warning) => (
        <li key={warning}>{warning}</li>
      ))}
    </ul>
  )
}

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
  const massInputId = useId()
  const needsConfirmation = MASS_CONFIRMATION_STATUSES.has(provenance.resolution_status)

  return (
    <section className="magnetometry-section">
      <h3>Sample Mass</h3>
      <p className="magnetometry-section__note">
        All candidate masses reported by the backend are shown. ElementX does not
        silently choose a mass when sources disagree.
      </p>

      {needsConfirmation && (
        <div className="status-banner status-banner--conflict" role="alert">
          Sample-mass resolution is <strong>{provenance.resolution_status}</strong>.
          Mass-normalized magnetization is blocked until a mass is confirmed.
        </div>
      )}

      {provenance.mass_candidates.length === 0 ? (
        <p className="magnetometry-empty">No mass candidates were reported.</p>
      ) : (
        <div className="mass-candidate-list">
          {provenance.mass_candidates.map((candidate, index) => (
            <article key={`${candidate.source}-${candidate.raw_value}-${index}`} className="mass-candidate">
              <div className="mass-candidate__value">
                {formatNumber(candidate.value_mg, 4)} {candidate.unit}
              </div>
              <div className="mass-candidate__meta">
                <span>{candidate.source.replaceAll('_', ' ')}</span>
                {candidate.source_key && <span>key: {candidate.source_key}</span>}
                <span>raw: {candidate.raw_value}</span>
              </div>
            </article>
          ))}
        </div>
      )}

      <dl className="result-list magnetometry-dl">
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
      </dl>

      <WarningList warnings={provenance.warnings} />

      {needsConfirmation && allowConfirmation && (
        <div className="mass-confirm">
          <label htmlFor={massInputId}>Confirmed sample mass (mg)</label>
          <div className="field-row">
            <input
              id={massInputId}
              className="text-input"
              type="number"
              step="any"
              min="0"
              inputMode="decimal"
              placeholder="Enter the mass to use, in mg"
              value={confirmedMass}
              onChange={(event) => onConfirmedMassChange(event.target.value)}
            />
            <button
              type="button"
              className="primary-btn"
              onClick={onReanalyze}
              disabled={reanalyzeDisabled}
            >
              Reanalyze with Confirmed Mass
            </button>
          </div>
        </div>
      )}
    </section>
  )
}

function MtSegmentCard({ segment, index }: { segment: MeasurementSegment; index: number }) {
  return (
    <article className="result-card magnetometry-card">
      <h3>M-T Segment {index}</h3>
      <p className="magnetometry-section__note">
        Identification only. No Curie temperature is calculated from this segment.
        {segment.mean_field_Oe !== null
          ? ` Mean applied field: ${formatNumber(segment.mean_field_Oe, 1)} Oe.`
          : ''}
      </p>
      <MeasuredCurve
        data={segment.data}
        xKey="temperature_K"
        xLabel="Temperature"
        xUnit="K"
      />
      <dl className="result-list">
        <ResultRow label="Segment index" value={String(index)} />
        <ResultRow label="Point count" value={String(segment.point_count)} />
        <ResultRow label="Valid points" value={String(segment.valid_point_count)} />
        <ResultRow
          label="Temperature range"
          value={formatRange(segment.temperature_range_K, 3, 'K')}
        />
        <ResultRow
          label="Field range"
          value={formatRange(segment.field_range_Oe, 3, 'Oe')}
        />
        <ResultRow
          label="Mean field"
          value={`${formatNumber(segment.mean_field_Oe, 3)} Oe`}
        />
        <ResultRow label="Duration" value={formatDuration(segment.duration_sec)} />
        <ResultRow label="Confidence" value={formatNumber(segment.confidence, 3)} />
      </dl>
      <WarningList warnings={segment.warnings} />
    </article>
  )
}

function HysteresisBlock({ hysteresis }: { hysteresis: HysteresisAnalysis }) {
  return (
    <article className="result-card magnetometry-subcard">
      <h4>Hysteresis</h4>
      <dl className="result-list">
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
      </dl>
    </article>
  )
}

function HighFieldBlock({ highField }: { highField: HighFieldAnalysis }) {
  return (
    <article className="result-card magnetometry-subcard">
      <h4>High Field</h4>
      <p className="evidence-caption">
        High-field saturation evidence:{' '}
        <span className={`evidence-badge evidence-badge--${highField.saturation_evidence_quality}`}>
          {highField.saturation_evidence_quality}
        </span>
      </p>
      <p className="magnetometry-section__note">
        This is the quality of high-field evidence returned by the backend, not a
        determination that the sample is saturated.
      </p>
      <dl className="result-list">
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
          label="Maximum measured |moment|"
          value={`${formatNumber(highField.maximum_absolute_measured_moment_emu, 6)} emu`}
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
      </dl>
    </article>
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
      value={`${formatNumber(value.specific_magnetization_emu_per_g, 4)} emu/g · ${formatNumber(value.specific_magnetization_Am2_per_kg, 4)} A·m²/kg`}
    />
  )
}

function NormalizedBlock({ normalized }: { normalized: NormalizedResults }) {
  if (!normalized.available) {
    return (
      <div className="status-banner status-banner--info">
        Mass-normalized magnetization is not available
        {normalized.reason ? ` (${normalized.reason})` : ''}.
        {MASS_CONFIRMATION_STATUSES.has(normalized.reason ?? '')
          ? ' Confirm the sample mass above and reanalyze if you want specific magnetization.'
          : null}
      </div>
    )
  }

  return (
    <article className="result-card magnetometry-subcard">
      <h4>Mass-normalized magnetization</h4>
      <p className="magnetometry-section__note">
        Specific magnetization from the backend. These values are mass-normalized
        measured moments, not a fitted saturation quantity.
      </p>
      <dl className="result-list">
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
      </dl>
    </article>
  )
}

function MhLoopCard({
  entry,
  segment,
}: {
  entry: MHAnalysisEntry
  segment: MeasurementSegment | undefined
}) {
  const temperature = entry.analysis.segment.mean_temperature_K
  const loopWarnings = [
    ...entry.analysis.warnings,
    ...entry.analysis.hysteresis.warnings,
    ...entry.analysis.high_field.warnings,
  ]

  return (
    <article className="mh-loop-card">
      <header className="mh-loop-card__header">
        <h3>
          M-H Loop — approximately {formatNumber(temperature, 1)} K
        </h3>
        <span className="mh-loop-card__index">segment {entry.segment_index}</span>
      </header>

      <MeasuredCurve
        data={segment?.data}
        xKey="field_Oe"
        xLabel="Magnetic Field"
        xUnit="Oe"
        referenceX={mhReferenceLines(entry.analysis.hysteresis)}
      />

      {loopWarnings.length > 0 && (
        <div className="status-banner status-banner--info">
          <WarningList warnings={loopWarnings} />
        </div>
      )}

      <div className="mh-loop-grid">
        <HysteresisBlock hysteresis={entry.analysis.hysteresis} />
        <HighFieldBlock highField={entry.analysis.high_field} />
      </div>

      <NormalizedBlock normalized={entry.analysis.normalized} />
    </article>
  )
}

export interface MagnetometryUploadProps {
  sampleId?: string
  initialResult?: MagnetometryAnalyzeResult | null
  readOnly?: boolean
  onSaved?: () => void
}

export default function MagnetometryUpload({
  sampleId,
  initialResult = null,
  readOnly = false,
  onSaved,
}: MagnetometryUploadProps) {
  const fileInputId = useId()
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
        const saved = await createSampleExperiment(
          sampleId,
          file,
          userConfirmedMassMg,
        )
        setResult(saved.analysis_json)
        onSaved?.()
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

  return (
    <section className="panel magnetometry-panel">
      <header className="panel-header">
        <h2>
          {readOnly
            ? 'Saved Magnetometry Experiment'
            : persistMode
              ? 'Upload Magnetometry Experiment'
              : 'Magnetometry Analysis'}
        </h2>
        <p>
          {readOnly
            ? 'This view renders the stored analysis JSON. The scientific pipeline is not re-run.'
            : persistMode
              ? 'Upload a Quantum Design VersaLab / MultiVu .dat file. ElementX analyzes it with the existing magnetometry pipeline and saves the raw file plus analysis under this sample.'
              : 'Upload a Quantum Design VersaLab / MultiVu .dat file. ElementX sends the file to the backend analysis pipeline and displays the returned experiment summary, M-T identification, and M-H results.'}
        </p>
      </header>

      {!readOnly && (
      <div className="magnetometry-upload">
        <div className="field-group">
          <label htmlFor={fileInputId}>Quantum Design .dat file</label>
          <div className="field-row">
            <input
              id={fileInputId}
              className="file-input-hidden"
              type="file"
              accept=".dat,application/octet-stream"
              onChange={(event) => {
                handleFileChange(event.target.files?.[0] ?? null)
              }}
            />
            <label htmlFor={fileInputId} className="file-btn">
              Choose .dat File
            </label>
            <span className="selected-filename">
              {selectedFile ? selectedFile.name : 'No file selected'}
            </span>
            <button
              type="button"
              className="primary-btn"
              onClick={() => void handleAnalyze()}
              disabled={loading || !selectedFile}
            >
              {loading
                ? persistMode
                  ? 'Saving…'
                  : 'Analyzing…'
                : persistMode
                  ? 'Upload & Save'
                  : 'Analyze'}
            </button>
          </div>
        </div>
      </div>
      )}

      {loading && (
        <div className="status-banner status-banner--info" role="status">
          Analyzing the experiment. This uses the backend magnetometry pipeline;
          no quantities are calculated in the browser.
        </div>
      )}

      {error && (
        <div className="status-banner status-banner--error" role="alert">
          {error}
        </div>
      )}

      {result && (
        <div className="magnetometry-results">
          <section className="magnetometry-section">
            <h3>Experiment Summary</h3>
            <dl className="result-list magnetometry-dl">
              <ResultRow label="Filename" value={result.file.filename ?? '—'} />
              <ResultRow label="Format" value={result.file.format} />
              <ResultRow
                label="Material"
                value={result.metadata.SAMPLE_MATERIAL || '—'}
              />
              <ResultRow
                label="Sample mass (instrument metadata)"
                value={
                  result.metadata.SAMPLE_MASS
                    ? `${result.metadata.SAMPLE_MASS} (header string)`
                    : '—'
                }
              />
              <ResultRow
                label="Total segments"
                value={String(result.segmentation.segment_count)}
              />
              <ResultRow
                label="M-H segments"
                value={String(result.summary.mh_segment_count)}
              />
              <ResultRow
                label="M-T segments"
                value={String(result.summary.mt_segment_count)}
              />
              <ResultRow
                label="Unknown segments"
                value={String(result.summary.unknown_segment_count)}
              />
              <ResultRow
                label="Normalization available"
                value={result.summary.normalization_available ? 'Yes' : 'No'}
              />
              {result.analysis_version && (
                <ResultRow
                  label="Analysis version"
                  value={result.analysis_version}
                />
              )}
            </dl>
            <WarningList warnings={result.warnings} />
            <WarningList warnings={result.segmentation.warnings} />
          </section>

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

          <section className="magnetometry-section">
            <h3>M-T Segments</h3>
            {mtSegments.length === 0 ? (
              <p className="magnetometry-empty">No M-T segments were identified.</p>
            ) : (
              <div className="magnetometry-stack">
                {mtSegments.map(({ segment, index }) => (
                  <MtSegmentCard key={index} segment={segment} index={index} />
                ))}
              </div>
            )}
          </section>

          <section className="magnetometry-section">
            <h3>M-H Analyses</h3>
            {result.mh_analyses.length === 0 ? (
              <p className="magnetometry-empty">No M-H analyses were returned.</p>
            ) : (
              <div className="magnetometry-stack">
                {result.mh_analyses.map((entry) => (
                  <MhLoopCard
                    key={entry.segment_index}
                    entry={entry}
                    segment={result.segmentation.segments[entry.segment_index]}
                  />
                ))}
              </div>
            )}
          </section>
        </div>
      )}
    </section>
  )
}

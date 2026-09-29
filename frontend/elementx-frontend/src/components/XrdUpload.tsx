import { useEffect, useId, useState } from 'react'
import {
  createXrdExperiment,
  MagnetApiError,
  type XrdAnalysisResult,
  type XrdCandidatePeak,
} from '../services/magnetApi'
import XrdPlot from './XrdPlot'

const ACCEPTED_XRD_EXTENSIONS = ['.txt', '.csv', '.xy', '.dat']

export interface XrdUploadProps {
  sampleId?: string
  initialResult?: XrdAnalysisResult | null
  readOnly?: boolean
  onSaved?: () => void
}

function formatNumber(value: number | null | undefined, digits = 3): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '—'
  }
  return value.toLocaleString(undefined, {
    maximumFractionDigits: digits,
    minimumFractionDigits: 0,
  })
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

function hasAcceptedXrdExtension(filename: string): boolean {
  const lower = filename.toLowerCase()
  return ACCEPTED_XRD_EXTENSIONS.some((extension) => lower.endsWith(extension))
}

function PeakTable({ peaks }: { peaks: XrdCandidatePeak[] }) {
  if (peaks.length === 0) {
    return (
      <p className="magnetometry-empty">No candidate intensity maxima were reported.</p>
    )
  }

  return (
    <div className="xrd-peak-table-wrap">
      <table className="xrd-peak-table">
        <thead>
          <tr>
            <th>2θ (°)</th>
            <th>Intensity</th>
          </tr>
        </thead>
        <tbody>
          {peaks.map((peak, index) => (
            <tr key={`${peak.two_theta_deg}-${peak.intensity}-${index}`}>
              <td>{formatNumber(peak.two_theta_deg, 4)}</td>
              <td>{formatNumber(peak.intensity, 4)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function XrdUpload({
  sampleId,
  initialResult = null,
  readOnly = false,
  onSaved,
}: XrdUploadProps) {
  const fileInputId = useId()
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<XrdAnalysisResult | null>(initialResult ?? null)

  useEffect(() => {
    if (initialResult) {
      setResult(initialResult)
      setError(null)
    }
  }, [initialResult])

  const persistMode = Boolean(sampleId) && !readOnly

  const handleFileChange = (file: File | null) => {
    setSelectedFile(file)
    setResult(null)
    setError(null)
  }

  const handleUpload = async () => {
    if (!selectedFile) {
      setError('Choose a two-column XRD .txt, .csv, .xy, or .dat file.')
      return
    }
    if (!hasAcceptedXrdExtension(selectedFile.name)) {
      setError('Only .txt, .csv, .xy, and two-column .dat XRD files are supported.')
      return
    }
    if (!sampleId) {
      setError('Open a sample before uploading XRD.')
      return
    }

    setLoading(true)
    setError(null)
    try {
      const saved = await createXrdExperiment(sampleId, selectedFile)
      setResult(saved.analysis_json)
      onSaved?.()
    } catch (err) {
      setResult(null)
      setError(errorMessage(err, 'XRD upload failed.'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="panel magnetometry-panel xrd-panel">
      <header className="panel-header">
        <h2>
          {readOnly
            ? 'Saved XRD Experiment'
            : persistMode
              ? 'Upload XRD Experiment'
              : 'XRD Experiment'}
        </h2>
        <p>
          {readOnly
            ? 'This view renders the stored XRD analysis JSON. The scientific pipeline is not re-run.'
            : 'Upload a UTF-8 two-column 2θ vs intensity file. ElementX preserves the raw bytes and plots the measured diffraction pattern. Quantum Design magnetometry .dat files are rejected.'}
        </p>
      </header>

      {!readOnly && (
        <div className="magnetometry-upload">
          <div className="field-group">
            <label htmlFor={fileInputId}>XRD 2-theta / intensity file</label>
            <div className="field-row">
              <input
                id={fileInputId}
                className="file-input-hidden"
                type="file"
                accept=".txt,.csv,.xy,.dat,text/plain,text/csv"
                onChange={(event) => {
                  handleFileChange(event.target.files?.[0] ?? null)
                }}
              />
              <label htmlFor={fileInputId} className="file-btn">
                Choose XRD File
              </label>
              <span className="selected-filename">
                {selectedFile ? selectedFile.name : 'No file selected'}
              </span>
              <button
                type="button"
                className="primary-btn"
                onClick={() => void handleUpload()}
                disabled={loading || !selectedFile}
              >
                {loading ? 'Saving…' : 'Upload & Save'}
              </button>
            </div>
          </div>
        </div>
      )}

      {loading && (
        <div className="status-banner status-banner--info" role="status">
          Parsing the measured 2θ / intensity series. No quantities are calculated in the
          browser.
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
            <h3>XRD Experiment</h3>
            <dl className="result-list magnetometry-dl">
              <ResultRow label="Filename" value={result.file.filename || '—'} />
              <ResultRow label="Experiment type" value="xrd" />
              <ResultRow label="Format" value={result.file.format} />
              <ResultRow label="Analysis version" value={result.analysis_version} />
              <ResultRow
                label="Point count"
                value={String(result.summary.point_count)}
              />
              <ResultRow
                label="2-theta range"
                value={`${formatNumber(result.summary.two_theta_min_deg, 4)} – ${formatNumber(result.summary.two_theta_max_deg, 4)} °`}
              />
              <ResultRow
                label="Intensity range"
                value={`${formatNumber(result.summary.intensity_min, 4)} – ${formatNumber(result.summary.intensity_max, 4)}`}
              />
            </dl>
            <WarningList warnings={result.warnings} />
          </section>

          <section className="magnetometry-section">
            <h3>Measured diffraction pattern</h3>
            <p className="magnetometry-section__note">
              Plotted in acquisition order from the stored 2θ and intensity arrays. Intensity
              is not normalized, smoothed, or interpolated in the browser.
            </p>
            <XrdPlot
              twoThetaDeg={result.series.two_theta_deg}
              intensity={result.series.intensity}
              peaks={result.peaks}
            />
          </section>

          <section className="magnetometry-section">
            <h3>Detected intensity maxima</h3>
            <p className="magnetometry-section__note">
              Candidate local intensity maxima from the backend peak finder. These are not
              indexed reflections, phases, or hkl assignments.
              {result.peak_detection
                ? ` Method: ${result.peak_detection.method}; prominence ${result.peak_detection.prominence_fraction_of_max} × max; minimum distance ${result.peak_detection.min_distance_points} points.`
                : ''}
            </p>
            <PeakTable peaks={result.peaks} />
          </section>
        </div>
      )}
    </section>
  )
}

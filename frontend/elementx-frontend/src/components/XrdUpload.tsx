import { useEffect, useState } from 'react'
import {
  createXrdExperiment,
  MagnetApiError,
  type SavedXrdExperiment,
  type XrdAnalysisResult,
  type XrdCandidatePeak,
} from '../services/magnetApi'
import XrdPlot from './XrdPlot'
import DataList, { ResultRow } from './ui/DataList'
import FileUploadBar from './ui/FileUploadBar'
import Notice from './ui/Notice'
import Section from './ui/Section'

const ACCEPTED_XRD_EXTENSIONS = ['.txt', '.csv', '.xy', '.dat']

export interface XrdUploadProps {
  sampleId?: string
  initialResult?: XrdAnalysisResult | null
  readOnly?: boolean
  onSaved?: (saved: SavedXrdExperiment) => void
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

function hasAcceptedXrdExtension(filename: string): boolean {
  const lower = filename.toLowerCase()
  return ACCEPTED_XRD_EXTENSIONS.some((extension) => lower.endsWith(extension))
}

function PeakTable({ peaks }: { peaks: XrdCandidatePeak[] }) {
  if (peaks.length === 0) {
    return <p className="empty-hint">No candidate intensity maxima were reported.</p>
  }

  return (
    <div className="table-wrap peak-table-wrap">
      <table className="data-table">
        <caption className="sr-only">Candidate intensity maxima</caption>
        <thead>
          <tr>
            <th scope="col" className="num">
              2θ (°)
            </th>
            <th scope="col" className="num">
              Intensity
            </th>
          </tr>
        </thead>
        <tbody>
          {peaks.map((peak, index) => (
            <tr key={`${peak.two_theta_deg}-${peak.intensity}-${index}`}>
              <td className="num mono">{formatNumber(peak.two_theta_deg, 4)}</td>
              <td className="num mono">{formatNumber(peak.intensity, 4)}</td>
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
      if (persistMode) {
        // The saved experiment is opened by the sample view; keep this form ready for another file.
        setSelectedFile(null)
      } else {
        setResult(saved.analysis_json)
      }
      onSaved?.(saved)
    } catch (err) {
      setResult(null)
      setError(errorMessage(err, 'XRD upload failed.'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="xrd-view">
      {!readOnly && (
        <div className="upload-block">
          <FileUploadBar
            label="XRD file: two columns, 2θ and intensity"
            accept=".txt,.csv,.xy,.dat,text/plain,text/csv"
            file={selectedFile}
            onFileChange={handleFileChange}
            chooseLabel="Choose XRD file"
            actionLabel={loading ? 'Saving…' : 'Upload & save'}
            onAction={() => void handleUpload()}
            busy={loading}
            hint="UTF-8 text (.txt, .csv, .xy, .dat). The raw bytes are stored with the analysis. Quantum Design magnetometry .dat files are rejected."
          />
        </div>
      )}

      {loading && (
        <Notice kind="loading">
          Parsing the measured 2θ / intensity series. No quantities are calculated in the
          browser.
        </Notice>
      )}

      {error && <Notice kind="error">{error}</Notice>}

      {result && (
        <div className="page">
          <Section title="Summary">
            <DataList label="XRD experiment summary" columns>
              <ResultRow label="Filename" value={result.file.filename || '—'} />
              <ResultRow label="Format" value={result.file.format} />
              <ResultRow label="Analysis version" value={result.analysis_version} />
              <ResultRow label="Point count" value={String(result.summary.point_count)} />
              <ResultRow
                label="2θ range"
                value={`${formatNumber(result.summary.two_theta_min_deg, 4)} – ${formatNumber(result.summary.two_theta_max_deg, 4)} °`}
              />
              <ResultRow
                label="Intensity range"
                value={`${formatNumber(result.summary.intensity_min, 4)} – ${formatNumber(result.summary.intensity_max, 4)}`}
              />
            </DataList>
            <WarningList warnings={result.warnings} />
          </Section>

          <Section
            title="Measured diffraction pattern"
            description="Plotted in acquisition order from the stored 2θ and intensity arrays. Intensity is not normalized, smoothed, or interpolated in the browser."
          >
            <div className="figure">
              <XrdPlot
                twoThetaDeg={result.series.two_theta_deg}
                intensity={result.series.intensity}
                peaks={result.peaks}
              />
              <div className="figure__side">
                <Section
                  level={3}
                  title="Candidate intensity maxima"
                  description={
                    <>
                      Local maxima from the backend peak finder. These are not indexed
                      reflections, phases, or hkl assignments.
                      {result.peak_detection
                        ? ` Method: ${result.peak_detection.method}; prominence ${result.peak_detection.prominence_fraction_of_max} × max; minimum distance ${result.peak_detection.min_distance_points} points.`
                        : ''}
                    </>
                  }
                >
                  <PeakTable peaks={result.peaks} />
                </Section>
              </div>
            </div>
          </Section>
        </div>
      )}
    </div>
  )
}

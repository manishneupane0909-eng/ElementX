import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import MagnetometryUpload from './MagnetometryUpload'
import XrdUpload from './XrdUpload'
import {
  createSample,
  getExperiment,
  getSample,
  listSamples,
  MagnetApiError,
  type ExperimentSummary,
  type SampleDetail,
  type SampleSummary,
  type SavedExperiment,
} from '../services/magnetApi'

function errorMessage(err: unknown, fallback: string): string {
  if (err instanceof MagnetApiError) {
    return err.detail
  }
  if (err instanceof Error) {
    return err.message
  }
  return fallback
}

function formatUploadedAt(value: string): string {
  // The API returns UTC timestamps without a zone suffix; without one the browser
  // would read them as local time and shift them by the UTC offset.
  const hasZone = /(?:Z|[+-]\d{2}:?\d{2})$/.test(value)
  const parsed = new Date(hasZone ? value : `${value}Z`)
  if (Number.isNaN(parsed.getTime())) {
    return value
  }
  return parsed.toLocaleString()
}

export default function SampleList() {
  const [samples, setSamples] = useState<SampleSummary[]>([])
  const [selected, setSelected] = useState<SampleDetail | null>(null)
  const [openedSaved, setOpenedSaved] = useState<SavedExperiment | null>(null)
  const [openedSummary, setOpenedSummary] = useState<ExperimentSummary | null>(null)
  const [name, setName] = useState('')
  const [formula, setFormula] = useState('')
  const [notes, setNotes] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadSamples = async () => {
    const listed = await listSamples()
    setSamples(listed)
  }

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    listSamples()
      .then((listed) => {
        if (!cancelled) {
          setSamples(listed)
          setError(null)
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(errorMessage(err, 'Failed to load samples.'))
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  const refreshSelected = async (sampleId: string) => {
    const detail = await getSample(sampleId)
    setSelected(detail)
    await loadSamples()
  }

  const handleCreate = async (event: FormEvent) => {
    event.preventDefault()
    if (!name.trim()) {
      setError('Sample name is required.')
      return
    }

    setLoading(true)
    setError(null)
    try {
      await createSample({
        name: name.trim(),
        formula: formula.trim() || undefined,
        notes: notes.trim() || undefined,
      })
      setName('')
      setFormula('')
      setNotes('')
      await loadSamples()
    } catch (err) {
      setError(errorMessage(err, 'Failed to create sample.'))
    } finally {
      setLoading(false)
    }
  }

  const handleOpenSample = async (sampleId: string) => {
    setLoading(true)
    setError(null)
    try {
      const detail = await getSample(sampleId)
      setSelected(detail)
      setOpenedSaved(null)
      setOpenedSummary(null)
    } catch (err) {
      setError(errorMessage(err, 'Failed to load sample.'))
    } finally {
      setLoading(false)
    }
  }

  const handleOpenExperiment = async (summary: ExperimentSummary) => {
    setLoading(true)
    setError(null)
    try {
      const saved = await getExperiment(summary.id)
      setOpenedSummary(summary)
      setOpenedSaved(saved)
    } catch (err) {
      setError(errorMessage(err, 'Failed to load experiment.'))
    } finally {
      setLoading(false)
    }
  }

  if (selected && openedSaved && openedSummary) {
    return (
      <div className="samples-view">
        <section className="panel samples-panel">
          <header className="panel-header">
            <button
              type="button"
              className="secondary-btn"
              onClick={() => {
                setOpenedSaved(null)
                setOpenedSummary(null)
              }}
            >
              Back to sample
            </button>
            <h2>{selected.name}</h2>
            <p>
              {openedSummary.experiment_type} · {openedSummary.original_filename} ·
              analysis version {openedSummary.analysis_version}
            </p>
          </header>
          {error && (
            <div className="status-banner status-banner--error" role="alert">
              {error}
            </div>
          )}
        </section>
        {openedSaved.experiment_type === 'xrd' ? (
          <XrdUpload readOnly initialResult={openedSaved.analysis_json} />
        ) : (
          <MagnetometryUpload readOnly initialResult={openedSaved.analysis_json} />
        )}
      </div>
    )
  }

  if (selected) {
    return (
      <div className="samples-view">
        <section className="panel samples-panel">
          <header className="panel-header">
            <button
              type="button"
              className="secondary-btn"
              onClick={() => {
                setSelected(null)
                void loadSamples()
              }}
            >
              Back to samples
            </button>
            <h2>{selected.name}</h2>
            {selected.formula && <p className="sample-formula">{selected.formula}</p>}
            {selected.notes && <p className="sample-notes">{selected.notes}</p>}
          </header>

          {error && (
            <div className="status-banner status-banner--error" role="alert">
              {error}
            </div>
          )}

          <section className="sample-experiments">
            <h3>Experiments</h3>
            {selected.experiments.length === 0 ? (
              <p className="empty-state">No saved experiments yet.</p>
            ) : (
              <ul className="experiment-list">
                {selected.experiments.map((experiment) => (
                  <li key={experiment.id}>
                    <button
                      type="button"
                      className="experiment-card"
                      onClick={() => void handleOpenExperiment(experiment)}
                    >
                      <span className="experiment-card__type">{experiment.experiment_type}</span>
                      <span className="experiment-card__filename">
                        {experiment.original_filename}
                      </span>
                      <span className="experiment-card__meta">
                        {formatUploadedAt(experiment.uploaded_at)} · analysis version{' '}
                        {experiment.analysis_version}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </section>

        <div className="sample-upload-stack">
          <MagnetometryUpload
            sampleId={selected.id}
            onSaved={() => {
              void refreshSelected(selected.id)
            }}
          />
          <XrdUpload
            sampleId={selected.id}
            onSaved={() => {
              void refreshSelected(selected.id)
            }}
          />
        </div>
      </div>
    )
  }

  return (
    <section className="panel samples-panel">
      <header className="panel-header">
        <h2>Samples</h2>
        <p>Create a sample, then upload and reopen saved magnetometry and XRD experiments.</p>
      </header>

      <form className="sample-create" onSubmit={(event) => void handleCreate(event)}>
        <h3>Create Sample</h3>
        <label className="field-label" htmlFor="sample-name">
          Name
        </label>
        <input
          id="sample-name"
          className="text-input"
          required
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Fe2CoGe annealed 48 h"
        />
        <label className="field-label" htmlFor="sample-formula">
          Formula (optional)
        </label>
        <input
          id="sample-formula"
          className="text-input"
          value={formula}
          onChange={(event) => setFormula(event.target.value)}
          placeholder="Fe2CoGe"
        />
        <label className="field-label" htmlFor="sample-notes">
          Notes (optional)
        </label>
        <textarea
          id="sample-notes"
          className="text-input sample-notes-input"
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
          placeholder="Annealed 900 C for 48 h"
          rows={3}
        />
        <button type="submit" className="primary-btn" disabled={loading}>
          Create Sample
        </button>
      </form>

      {loading && (
        <div className="status-banner status-banner--info" role="status">
          Loading samples…
        </div>
      )}

      {error && (
        <div className="status-banner status-banner--error" role="alert">
          {error}
        </div>
      )}

      {samples.length === 0 && !loading ? (
        <p className="empty-state">No samples yet. Create one to save experiments.</p>
      ) : (
        <ul className="sample-list">
          {samples.map((sample) => (
            <li key={sample.id}>
              <button
                type="button"
                className="sample-card"
                onClick={() => void handleOpenSample(sample.id)}
              >
                <span className="sample-card__name">{sample.name}</span>
                {sample.formula && (
                  <span className="sample-card__formula">{sample.formula}</span>
                )}
                <span className="sample-card__meta">
                  {(sample.experiment_count ?? 0) === 1
                    ? '1 experiment'
                    : `${sample.experiment_count ?? 0} experiments`}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

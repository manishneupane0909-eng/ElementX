import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import MagnetometryUpload from './MagnetometryUpload'
import XrdUpload from './XrdUpload'
import { DEMO_MODE } from '../demo/demoMode'
import DemoProvenance, { DataKindTag } from '../demo/DemoProvenance'
import Button from './ui/Button'
import Notice from './ui/Notice'
import Section from './ui/Section'
import TextAreaField from './ui/TextAreaField'
import TextField from './ui/TextField'
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

type UploadKind = 'magnetometry' | 'xrd'

const EXPERIMENT_TYPE_LABEL: Record<string, string> = {
  magnetometry: 'Magnetometry',
  xrd: 'XRD',
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

function parseApiTimestamp(value: string): Date | null {
  // The API returns UTC timestamps without a zone suffix; without one the browser
  // would read them as local time and shift them by the UTC offset.
  const hasZone = /(?:Z|[+-]\d{2}:?\d{2})$/.test(value)
  const parsed = new Date(hasZone ? value : `${value}Z`)
  return Number.isNaN(parsed.getTime()) ? null : parsed
}

function formatDateTime(value: string): string {
  const parsed = parseApiTimestamp(value)
  return parsed ? parsed.toLocaleString() : value
}

function formatDate(value: string): string {
  const parsed = parseApiTimestamp(value)
  return parsed ? parsed.toLocaleDateString() : value
}

function countLabel(count: number): string {
  return count === 1 ? '1 experiment' : `${count} experiments`
}

export default function SampleList() {
  const [samples, setSamples] = useState<SampleSummary[]>([])
  const [selected, setSelected] = useState<SampleDetail | null>(null)
  const [openedSaved, setOpenedSaved] = useState<SavedExperiment | null>(null)
  const [openedSummary, setOpenedSummary] = useState<ExperimentSummary | null>(null)
  const [creating, setCreating] = useState(false)
  const [adding, setAdding] = useState(false)
  const [uploadKind, setUploadKind] = useState<UploadKind>('magnetometry')
  const [name, setName] = useState('')
  const [formula, setFormula] = useState('')
  const [notes, setNotes] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const newSampleButton = useRef<HTMLButtonElement | null>(null)
  const nameInput = useRef<HTMLDivElement | null>(null)

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

  useEffect(() => {
    if (creating) {
      nameInput.current?.querySelector('input')?.focus()
    }
  }, [creating])

  const closeCreateForm = () => {
    setCreating(false)
    setName('')
    setFormula('')
    setNotes('')
    newSampleButton.current?.focus()
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
      closeCreateForm()
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
      setAdding(false)
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

  /** A new experiment was saved: refresh the sample and show the stored analysis. */
  const handleSaved = async (saved: SavedExperiment) => {
    setError(null)
    try {
      const detail = await getSample(saved.sample_id)
      setSelected(detail)
      await loadSamples()
    } catch (err) {
      setError(errorMessage(err, 'Saved, but the sample could not be refreshed.'))
    }
    setAdding(false)
    setOpenedSummary({
      id: saved.id,
      experiment_type: saved.experiment_type,
      original_filename: saved.original_filename,
      uploaded_at: saved.uploaded_at,
      analysis_version: saved.analysis_version,
    })
    setOpenedSaved(saved)
  }

  const backToSamples = () => {
    setSelected(null)
    setOpenedSaved(null)
    setOpenedSummary(null)
    setError(null)
    void loadSamples()
  }

  // ---- A saved experiment ----

  if (selected && openedSaved && openedSummary) {
    return (
      <div className="page">
        <nav className="crumbs" aria-label="Breadcrumb">
          <Button variant="link" onClick={backToSamples}>
            Samples
          </Button>
          <span aria-hidden="true">/</span>
          <Button
            variant="link"
            onClick={() => {
              setOpenedSaved(null)
              setOpenedSummary(null)
            }}
          >
            {selected.name}
          </Button>
        </nav>

        <header className="entity-head">
          <div className="entity-head__title">
            <h2>{openedSummary.original_filename}</h2>
            <span className="type-tag">
              {EXPERIMENT_TYPE_LABEL[openedSummary.experiment_type] ??
                openedSummary.experiment_type}
            </span>
            {openedSaved.demo && (
              <DataKindTag kind={openedSaved.demo.data_kind} label={openedSaved.demo.label} />
            )}
          </div>
          <p className="meta-line">
            <span>
              Sample <strong>{selected.name}</strong>
            </span>
            <span>
              {DEMO_MODE
                ? `Record created ${formatDate(openedSummary.uploaded_at)}`
                : `Uploaded ${formatDateTime(openedSummary.uploaded_at)}`}
            </span>
            <span>Analysis version {openedSummary.analysis_version}</span>
            <span>Stored analysis; the scientific pipeline is not re-run.</span>
          </p>
        </header>

        {error && <Notice kind="error">{error}</Notice>}

        <DemoProvenance provenance={openedSaved.demo} />

        {openedSaved.experiment_type === 'xrd' ? (
          <XrdUpload readOnly initialResult={openedSaved.analysis_json} />
        ) : (
          <MagnetometryUpload readOnly initialResult={openedSaved.analysis_json} />
        )}
      </div>
    )
  }

  // ---- One sample ----

  if (selected) {
    return (
      <div className="page">
        <nav className="crumbs" aria-label="Breadcrumb">
          <Button variant="link" onClick={backToSamples}>
            Samples
          </Button>
          <span aria-hidden="true">/</span>
          <span aria-current="page">{selected.name}</span>
        </nav>

        <header className="entity-head">
          <div className="entity-head__title">
            <h2>{selected.name}</h2>
            {selected.formula && <span className="entity-head__formula">{selected.formula}</span>}
            {selected.demo && (
              <DataKindTag kind={selected.demo.data_kind} label={selected.demo.label} />
            )}
          </div>
          {selected.notes && <p className="entity-head__notes">{selected.notes}</p>}
          <p className="meta-line">
            <span>
              {DEMO_MODE ? 'Record created' : 'Created'} {formatDate(selected.created_at)}
            </span>
            <span>{countLabel(selected.experiments.length)}</span>
          </p>
        </header>

        {error && <Notice kind="error">{error}</Notice>}

        <Section
          title="Experiments"
          actions={
            DEMO_MODE ? undefined : (
              <Button
                variant={adding ? 'secondary' : 'primary'}
                aria-expanded={adding}
                aria-controls="add-experiment"
                onClick={() => setAdding((open) => !open)}
              >
                {adding ? 'Cancel' : 'Add experiment'}
              </Button>
            )
          }
        >
          {adding && (
            <div className="inline-form" id="add-experiment">
              <div className="span-all">
                <div className="segmented" role="group" aria-label="Experiment type">
                  <button
                    type="button"
                    className="segmented__btn"
                    aria-pressed={uploadKind === 'magnetometry'}
                    onClick={() => setUploadKind('magnetometry')}
                  >
                    Magnetometry
                  </button>
                  <button
                    type="button"
                    className="segmented__btn"
                    aria-pressed={uploadKind === 'xrd'}
                    onClick={() => setUploadKind('xrd')}
                  >
                    XRD
                  </button>
                </div>
              </div>
              <div className="span-all">
                {uploadKind === 'magnetometry' ? (
                  <MagnetometryUpload
                    key="mag"
                    sampleId={selected.id}
                    onSaved={(saved) => void handleSaved(saved)}
                  />
                ) : (
                  <XrdUpload
                    key="xrd"
                    sampleId={selected.id}
                    onSaved={(saved) => void handleSaved(saved)}
                  />
                )}
              </div>
            </div>
          )}

          {selected.experiments.length === 0 ? (
            !adding && (
              <p className="empty-hint">
                {DEMO_MODE
                  ? 'No experiments are stored for this example sample.'
                  : 'No experiments saved for this sample. Use Add experiment to upload a Quantum Design magnetometry file or an XRD pattern.'}
              </p>
            )
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <caption className="sr-only">Saved experiments for {selected.name}</caption>
                <thead>
                  <tr>
                    <th scope="col">Type</th>
                    <th scope="col">File</th>
                    <th scope="col">{DEMO_MODE ? 'Record created' : 'Uploaded'}</th>
                    <th scope="col" className="hide-narrow">
                      Analysis version
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {selected.experiments.map((experiment) => (
                    <tr key={experiment.id}>
                      <td>
                        <span className="type-tag">
                          {EXPERIMENT_TYPE_LABEL[experiment.experiment_type] ??
                            experiment.experiment_type}
                        </span>
                        {experiment.demo && (
                          <>
                            {' '}
                            <DataKindTag
                              kind={experiment.demo.data_kind}
                              label={
                                experiment.demo.data_kind === 'synthetic'
                                  ? 'Synthetic'
                                  : 'Real measurement'
                              }
                            />
                          </>
                        )}
                      </td>
                      <td>
                        <button
                          type="button"
                          className="row-link"
                          onClick={() => void handleOpenExperiment(experiment)}
                        >
                          {experiment.original_filename}
                        </button>
                      </td>
                      <td className="cell-muted">
                        {DEMO_MODE
                          ? formatDate(experiment.uploaded_at)
                          : formatDateTime(experiment.uploaded_at)}
                      </td>
                      <td className="cell-muted hide-narrow">{experiment.analysis_version}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Section>
      </div>
    )
  }

  // ---- Sample list ----

  return (
    <div className="page">
      <div className="page-bar">
        <p className="page-intro">
          {DEMO_MODE
            ? 'Two example samples: a real Fe2CoGe magnetometry measurement and a synthetic XRD test pattern. Open one to explore its stored analysis.'
            : 'Samples group your saved magnetometry and XRD experiments. Open a sample to add or review them.'}
        </p>
        {!DEMO_MODE && (
          <Button
            ref={newSampleButton}
            variant={creating ? 'secondary' : 'primary'}
            aria-expanded={creating}
            aria-controls="new-sample-form"
            onClick={() => (creating ? closeCreateForm() : setCreating(true))}
          >
            {creating ? 'Cancel' : 'New sample'}
          </Button>
        )}
      </div>

      {creating && (
        <form
          id="new-sample-form"
          className="inline-form"
          onSubmit={(event) => void handleCreate(event)}
          aria-label="New sample"
        >
          <div ref={nameInput}>
            <TextField
              label="Name"
              required
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Fe2CoGe annealed 48 h"
            />
          </div>
          <TextField
            label="Formula (optional)"
            value={formula}
            onChange={(event) => setFormula(event.target.value)}
            placeholder="Fe2CoGe"
          />
          <div className="span-all">
            <TextAreaField
              label="Notes (optional)"
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              placeholder="Annealed 900 C for 48 h"
              rows={2}
            />
          </div>
          <div className="span-all inline-form__actions">
            <Button type="submit" variant="primary" disabled={loading}>
              Create sample
            </Button>
            <Button onClick={closeCreateForm}>Cancel</Button>
          </div>
        </form>
      )}

      {error && <Notice kind="error">{error}</Notice>}
      {loading && samples.length === 0 && <Notice kind="loading">Loading samples…</Notice>}

      {samples.length === 0 && !loading
        ? !creating && (
            <p className="empty-hint">
              No samples yet. Choose New sample, then upload a magnetometry or XRD file to keep its
              analysis with the sample.
            </p>
          )
        : samples.length > 0 && (
            <div className="table-wrap">
              <table className="data-table">
                <caption className="sr-only">
                  {DEMO_MODE ? 'Example samples' : 'Your samples'}
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Sample</th>
                    <th scope="col">Formula</th>
                    <th scope="col" className="num">
                      Experiments
                    </th>
                    <th scope="col" className="hide-narrow">
                      Notes
                    </th>
                    <th scope="col" className="hide-narrow">
                      {DEMO_MODE ? 'Record date' : 'Updated'}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {samples.map((sample) => (
                    <tr key={sample.id}>
                      <td>
                        <button
                          type="button"
                          className="row-link"
                          onClick={() => void handleOpenSample(sample.id)}
                        >
                          {sample.name}
                        </button>
                        {sample.demo && (
                          <>
                            {' '}
                            <DataKindTag
                              kind={sample.demo.data_kind}
                              label={
                                sample.demo.data_kind === 'synthetic'
                                  ? 'Synthetic'
                                  : 'Real measurement'
                              }
                            />
                          </>
                        )}
                      </td>
                      <td className="mono">{sample.formula ?? '—'}</td>
                      <td className="num">{sample.experiment_count ?? 0}</td>
                      <td className="cell-muted cell-clip hide-narrow">{sample.notes ?? ''}</td>
                      <td className="cell-muted hide-narrow">{formatDate(sample.updated_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
    </div>
  )
}

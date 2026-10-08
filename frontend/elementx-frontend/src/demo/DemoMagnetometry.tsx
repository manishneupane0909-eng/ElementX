import { useEffect, useState } from 'react'
import MagnetometryUpload from '../components/MagnetometryUpload'
import Notice from '../components/ui/Notice'
import { getExperiment } from '../services/magnetApi'
import type { SavedExperiment } from '../services/magnetApi'
import { getManifest } from './demoData'
import DemoProvenance, { DataKindTag } from './DemoProvenance'

/** Demo version of the Magnetometry page: the real example measurement, already analysed. */
export default function DemoMagnetometry() {
  const [saved, setSaved] = useState<SavedExperiment | null>(null)
  const [sampleName, setSampleName] = useState('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    getManifest()
      .then(async (manifest) => {
        const featured = manifest.samples.find((s) => s.id === manifest.featured.sample_id)
        const experiment = await getExperiment(manifest.featured.experiment_id)
        if (cancelled) return
        setSampleName(featured?.name ?? '')
        setSaved(experiment)
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : 'The example measurement could not be loaded.',
          )
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  if (error) return <Notice kind="error">{error}</Notice>
  if (!saved) return <Notice kind="loading">Loading the example measurement…</Notice>
  if (saved.experiment_type !== 'magnetometry') {
    return <Notice kind="error">The featured example is not a magnetometry record.</Notice>
  }

  return (
    <div className="page">
      <header className="entity-head">
        <div className="entity-head__title">
          <h2>{saved.original_filename}</h2>
          {saved.demo && <DataKindTag kind={saved.demo.data_kind} label={saved.demo.label} />}
        </div>
        <p className="meta-line">
          <span>
            Sample <strong>{sampleName}</strong>
          </span>
          <span>Stored analysis; the scientific pipeline is not re-run here.</span>
        </p>
      </header>
      <DemoProvenance provenance={saved.demo} />
      <MagnetometryUpload readOnly initialResult={saved.analysis_json} />
    </div>
  )
}

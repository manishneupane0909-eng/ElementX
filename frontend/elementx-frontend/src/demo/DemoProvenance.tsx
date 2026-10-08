import Disclosure from '../components/ui/Disclosure'
import type { DemoDataKind, DemoProvenance as Provenance } from '../services/magnetApi'

/** Small chip stating what kind of data a record holds. Always text, never colour alone. */
export function DataKindTag({ kind, label }: { kind: DemoDataKind; label?: string }) {
  const synthetic = kind === 'synthetic'
  return (
    <span className={`demo-kind demo-kind--${synthetic ? 'synthetic' : 'real'}`}>
      {label ?? (synthetic ? 'Synthetic, not a laboratory measurement' : 'Real measurement')}
    </span>
  )
}

function shortHash(hash: string): string {
  return `${hash.slice(0, 12)}…${hash.slice(-6)}`
}

function formatBytes(bytes: number): string {
  return bytes >= 1024 * 1024
    ? `${(bytes / (1024 * 1024)).toFixed(2)} MB`
    : bytes >= 1024
      ? `${(bytes / 1024).toFixed(1)} kB`
      : `${bytes} B`
}

/** Where an example record comes from and exactly what was changed for the public copy. */
export default function DemoProvenance({ provenance }: { provenance?: Provenance }) {
  if (!provenance) return null
  const synthetic = provenance.data_kind === 'synthetic'
  return (
    <aside
      className={`demo-prov demo-prov--${synthetic ? 'synthetic' : 'real'}`}
      aria-label="Data provenance"
    >
      <p className="demo-prov__head">
        <DataKindTag kind={provenance.data_kind} label={provenance.label} />
      </p>
      <p className="demo-prov__text">{provenance.description}</p>
      <Disclosure summary="Provenance details" className="demo-prov__details">
        <dl className="demo-prov__list">
          <div>
            <dt>Source file</dt>
            <dd className="mono">
              {provenance.source_file} ({formatBytes(provenance.source_bytes)})
            </dd>
          </div>
          <div>
            <dt>SHA-256 of the original</dt>
            <dd className="mono" title={provenance.source_sha256}>
              {shortHash(provenance.source_sha256)}
            </dd>
          </div>
          <div>
            <dt>Analysis</dt>
            <dd>
              ElementX {provenance.analysis_pipeline}, run on the backend and stored as a snapshot
            </dd>
          </div>
          <div>
            <dt>Changes in this public copy</dt>
            <dd>
              {provenance.modifications.length === 0
                ? 'None.'
                : provenance.modifications.map((text) => <span key={text}>{text}</span>)}
            </dd>
          </div>
          <div>
            <dt>Record dates</dt>
            <dd>
              The “uploaded” date is a fixed demo constant, not the measurement date. The
              measurement date is in the instrument metadata.
            </dd>
          </div>
        </dl>
      </Disclosure>
    </aside>
  )
}

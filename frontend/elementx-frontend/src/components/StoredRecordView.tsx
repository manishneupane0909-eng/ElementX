import { createContext, useContext, type ReactNode } from 'react'
import {
  LARGEST_MOMENT_LIMIT,
  MAXIMA_LIMIT,
  type ExperimentRecord,
  type MagnetometryRecord,
  type SampleReadout,
  type StoredRecord,
  type XrdRecord,
} from './storedRecord'
import DataList, { ResultRow } from './ui/DataList'
import Disclosure from './ui/Disclosure'

/** Distinguishes the tables of one reply from another's, so each scroll region has a unique name. */
const ReplyNumber = createContext<number | null>(null)

/** A horizontally scrollable table that can be reached and scrolled with the keyboard. */
function ScrollTable({ label, children }: { label: string; children: ReactNode }) {
  const reply = useContext(ReplyNumber)
  return (
    <div
      className="table-wrap"
      tabIndex={0}
      role="region"
      aria-label={reply === null ? label : `${label} (reply ${reply})`}
    >
      {children}
    </div>
  )
}

function RecordSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="record__section">
      <h2 className="record__heading">{title}</h2>
      {children}
    </section>
  )
}

function Warnings({ warnings, label }: { warnings: string[]; label: string }) {
  if (warnings.length === 0) return null
  return (
    <div className="note note--warn">
      <ul aria-label={label}>
        {warnings.map((warning, index) => (
          <li key={index}>{warning}</li>
        ))}
      </ul>
    </div>
  )
}

function experimentContents(experiment: ExperimentRecord): string {
  switch (experiment.kind) {
    case 'magnetometry':
      return `M-H segments: ${experiment.mhSegments}, M-T segments: ${experiment.mtSegments}`
    case 'xrd':
      return `${experiment.points} points`
    default:
      return 'no summary available'
  }
}

function experimentType(experiment: ExperimentRecord): string {
  switch (experiment.kind) {
    case 'magnetometry':
      return 'Magnetometry'
    case 'xrd':
      return 'XRD'
    default:
      return experiment.type
  }
}

function MagnetometryResults({ record }: { record: MagnetometryRecord }) {
  const warned = record.segments.filter((row) => row.warnings.length > 0)
  // When every segment reports the same mass source (or the same reason), say it once under the
  // table instead of repeating it in each row. A mix is shown per row.
  const notes = new Set(
    record.segments.map((row) =>
      row.normalized?.kind === 'value'
        ? `mass source: ${row.normalized.massSource}`
        : row.normalized?.kind === 'unavailable'
          ? `reason: ${row.normalized.reason}`
          : '',
    ),
  )
  const sharedNote = notes.size === 1 && !notes.has('') ? [...notes][0] : null
  return (
    <div className="record__block">
      <h3 className="record__sub">
        <span className="mono">{record.file}</span>
      </h3>
      <DataList label={`Magnetometry summary for ${record.file}`} columns>
        <ResultRow label="M-H segments" value={record.mhSegments} />
        <ResultRow label="M-T segments" value={record.mtSegments} />
        <ResultRow label="normalization_available" value={record.normalizationAvailable} />
      </DataList>

      {record.segments.length > 0 && (
        <>
          <ScrollTable label={`M-H segment results stored for ${record.file}`}>
            <table className="data-table record__table">
              <caption className="sr-only">M-H segment results stored for {record.file}</caption>
              <thead>
                <tr>
                  <th scope="col" className="num">
                    Segment
                  </th>
                  <th scope="col" className="num">
                    Mean T (K)
                  </th>
                  <th scope="col" className="num">
                    Hc(−) (Oe)
                  </th>
                  <th scope="col" className="num">
                    Hc(+) (Oe)
                  </th>
                  <th scope="col" className="num">
                    Mr(−) (emu)
                  </th>
                  <th scope="col" className="num">
                    Mr(+) (emu)
                  </th>
                  <th scope="col">High-field saturation evidence</th>
                  <th scope="col" className="num">
                    Largest measured |moment| (emu)
                  </th>
                  <th scope="col" className="num">
                    Mass-normalized Mr(+) (emu/g)
                  </th>
                </tr>
              </thead>
              <tbody>
                {record.segments.map((row, index) => (
                  <tr key={`${row.segment}-${index}`}>
                    <th scope="row" className="num record__rowhead">
                      {row.segment}
                    </th>
                    <td className="num mono">{row.meanT}</td>
                    <td className="num mono">{row.hcNegative}</td>
                    <td className="num mono">{row.hcPositive}</td>
                    <td className="num mono">{row.mrNegative}</td>
                    <td className="num mono">{row.mrPositive}</td>
                    <td>{row.evidence}</td>
                    <td className="num mono">{row.largestMoment}</td>
                    <td className="num mono">
                      {row.normalized?.kind === 'value' ? (
                        <>
                          {row.normalized.value}
                          {!sharedNote && (
                            <span className="record__cellnote">
                              mass source: {row.normalized.massSource}
                            </span>
                          )}
                        </>
                      ) : row.normalized?.kind === 'unavailable' ? (
                        <>
                          not available
                          {!sharedNote && (
                            <span className="record__cellnote">
                              reason: {row.normalized.reason}
                            </span>
                          )}
                        </>
                      ) : (
                        '—'
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </ScrollTable>
          <p className="record__note">
            Largest measured |moment|: {LARGEST_MOMENT_LIMIT}.
            {sharedNote ? ` Mass-normalized Mr(+), ${sharedNote}.` : ''} Values are exactly as
            stored, in the units shown.
          </p>
        </>
      )}

      {warned.length > 0 && (
        <Disclosure
          summary={`Segment warnings · ${warned.reduce((total, row) => total + row.warnings.length, 0)}`}
        >
          {warned.map((row, index) => (
            <Warnings
              key={`${row.segment}-${index}`}
              label={`Warnings for M-H segment ${row.segment}`}
              warnings={row.warnings.map((warning) => `M-H segment ${row.segment}: ${warning}`)}
            />
          ))}
        </Disclosure>
      )}
      {record.omitted && <p className="record__note">{record.omitted}</p>}
      <Warnings warnings={record.fileWarnings} label={`File warnings for ${record.file}`} />
    </div>
  )
}

function XrdResults({ record }: { record: XrdRecord }) {
  return (
    <div className="record__block">
      <h3 className="record__sub">
        <span className="mono">{record.file}</span>
      </h3>
      <DataList label={`Measured pattern for ${record.file}`} columns>
        <ResultRow label="Points" value={record.points} />
        <ResultRow label="2θ range" value={`${record.twoThetaMin} to ${record.twoThetaMax} deg`} />
        <ResultRow
          label="Intensity range"
          value={`${record.intensityMin} to ${record.intensityMax}`}
        />
      </DataList>
      {record.maxima ? (
        <>
          <ScrollTable label={`Candidate intensity maxima stored for ${record.file}`}>
            <table className="data-table record__table record__table--narrow">
              <caption className="sr-only">
                Candidate intensity maxima stored for {record.file}
              </caption>
              <thead>
                <tr>
                  <th scope="col" className="num">
                    2θ (deg)
                  </th>
                  <th scope="col" className="num">
                    Intensity (I)
                  </th>
                </tr>
              </thead>
              <tbody>
                {record.maxima.map((maximum, index) => (
                  <tr key={index}>
                    <td className="num mono">{maximum.twoTheta}</td>
                    <td className="num mono">{maximum.intensity}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </ScrollTable>
          <p className="record__note">Candidate intensity maxima ({MAXIMA_LIMIT}).</p>
        </>
      ) : (
        <p className="record__note">Candidate intensity maxima: none detected</p>
      )}
      <Warnings warnings={record.fileWarnings} label={`File warnings for ${record.file}`} />
    </div>
  )
}

function Provenance({ record }: { record: SampleReadout }) {
  const rows = record.experiments
  if (rows.length === 0) return null
  return (
    <RecordSection title="Data provenance">
      <p className="record__note">
        Source: stored records; values are read from saved analyses. Nothing was recalculated.
      </p>
      <Disclosure summary={`Pipeline, upload time and sample mass · ${rows.length}`} defaultOpen>
        <ScrollTable label="Provenance of each saved experiment">
          <table className="data-table record__table">
            <caption className="sr-only">Provenance of each saved experiment</caption>
            <thead>
              <tr>
                <th scope="col">File</th>
                <th scope="col">Pipeline</th>
                <th scope="col">Uploaded</th>
                <th scope="col">Mass status</th>
                <th scope="col" className="num">
                  Resolved mass (mg)
                </th>
                <th scope="col">Mass source</th>
                <th scope="col">normalization_allowed</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((experiment, index) => (
                <tr key={index}>
                  <th scope="row" className="record__rowhead mono">
                    {experiment.file}
                  </th>
                  {experiment.kind === 'other' ? (
                    <td colSpan={6} className="cell-muted">
                      type {experiment.type}: no summary available
                    </td>
                  ) : (
                    <>
                      <td className="mono">v{experiment.pipeline}</td>
                      <td className="mono">{experiment.uploaded}</td>
                      {experiment.kind === 'magnetometry' ? (
                        experiment.mass ? (
                          <>
                            <td>{experiment.mass.status}</td>
                            <td className="num mono">{experiment.mass.resolvedMassMg}</td>
                            <td>{experiment.mass.source}</td>
                            <td>{experiment.mass.normalizationAllowed}</td>
                          </>
                        ) : (
                          <td colSpan={4} className="cell-muted">
                            Mass provenance: not available
                          </td>
                        )
                      ) : (
                        <td colSpan={4} className="cell-muted">
                          not applicable to XRD
                        </td>
                      )}
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </ScrollTable>
        {rows.map((experiment, index) =>
          experiment.kind === 'magnetometry' && experiment.confirmedMassMg !== null ? (
            <p key={index} className="record__note">
              User-confirmed mass (mg) for {experiment.file}: {experiment.confirmedMassMg}
            </p>
          ) : null,
        )}
      </Disclosure>
    </RecordSection>
  )
}

function SampleView({ record }: { record: SampleReadout }) {
  const magnetometry = record.experiments.filter(
    (experiment): experiment is MagnetometryRecord => experiment.kind === 'magnetometry',
  )
  const xrd = record.experiments.filter(
    (experiment): experiment is XrdRecord => experiment.kind === 'xrd',
  )

  return (
    <>
      <RecordSection title="Sample summary">
        <DataList label="Sample summary" columns>
          <ResultRow label="Name" value={record.name} />
          <ResultRow label="Formula" value={record.formula} />
          <ResultRow label="Notes" value={record.notes} />
          <ResultRow label="Saved experiments" value={record.savedExperiments} />
        </DataList>
        {record.noExperiments && (
          <p className="record__note">No experiments have been saved for this sample yet.</p>
        )}
      </RecordSection>

      {record.experiments.length > 0 && (
        <RecordSection title="Saved experiments">
          <ScrollTable label="Saved experiments">
            <table className="data-table record__table">
              <caption className="sr-only">Saved experiments</caption>
              <thead>
                <tr>
                  <th scope="col">Type</th>
                  <th scope="col">File</th>
                  <th scope="col">Contents</th>
                </tr>
              </thead>
              <tbody>
                {record.experiments.map((experiment, index) => (
                  <tr key={index}>
                    <td>{experimentType(experiment)}</td>
                    <td className="mono">{experiment.file}</td>
                    <td className="cell-muted">{experimentContents(experiment)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </ScrollTable>
        </RecordSection>
      )}

      {magnetometry.length > 0 && (
        <RecordSection title="Magnetometry results">
          {magnetometry.map((experiment, index) => (
            <MagnetometryResults key={index} record={experiment} />
          ))}
        </RecordSection>
      )}

      {xrd.length > 0 && (
        <RecordSection title="XRD results">
          {xrd.map((experiment, index) => (
            <XrdResults key={index} record={experiment} />
          ))}
        </RecordSection>
      )}

      <Provenance record={record} />
    </>
  )
}

/**
 * Presents the backend's stored-record readout as sections and tables. Every cell is the exact
 * string the backend wrote; nothing is re-formatted, converted or interpreted.
 */
export default function StoredRecordView({
  record,
  reply = null,
}: {
  record: StoredRecord
  /** Position of this reply in the conversation, used only to name its scroll regions. */
  reply?: number | null
}) {
  return (
    <ReplyNumber.Provider value={reply}>
      <div className="record">
        <p className="record__lead">{record.lead}</p>
        {record.kind === 'sample' && <SampleView record={record} />}
        {record.kind === 'overview' && (
          <RecordSection title="Research samples">
            <p className="record__note">Names only; select one for stored measurement values.</p>
            {record.samples.length === 0 ? (
              <p className="empty-hint">No samples listed.</p>
            ) : (
              <ScrollTable label="Research samples">
                <table className="data-table record__table">
                  <caption className="sr-only">Research samples</caption>
                  <thead>
                    <tr>
                      <th scope="col">Sample</th>
                      <th scope="col">Formula</th>
                      <th scope="col" className="num">
                        Saved experiments
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {record.samples.map((sample, index) => (
                      <tr key={index}>
                        <th scope="row" className="record__rowhead">
                          {sample.name}
                        </th>
                        <td className="mono">{sample.formula}</td>
                        <td className="num">{sample.experiments}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </ScrollTable>
            )}
          </RecordSection>
        )}
        {record.kind === 'empty-overview' && <p className="record__note">{record.text}</p>}
      </div>
    </ReplyNumber.Provider>
  )
}

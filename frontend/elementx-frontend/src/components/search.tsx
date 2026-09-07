import { useId, useState } from 'react'
import {
  queryFormula,
  parseCif,
  MagnetApiError,
  type FormulaQueryResult,
  type CifParseResult,
} from '../services/magnetApi'

type SearchMode = 'simple' | 'advanced'

interface SearchProps {
  elements: Record<string, number>
  normalizeSymbol: (input: string) => string
}

function formatNumber(value: number | null | undefined, digits = 4): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '—'
  }
  return value.toFixed(digits)
}

export default function Search({ elements, normalizeSymbol }: SearchProps) {
  const formulaInputId = useId()
  const elementInputId = useId()
  const cifInputId = useId()

  const [searchMode, setSearchMode] = useState<SearchMode>('simple')
  const [elementQuery, setElementQuery] = useState('')
  const [formulaQuery, setFormulaQuery] = useState('Nd2Fe14B')
  const [selectedCifName, setSelectedCifName] = useState('')

  const [formulaLoading, setFormulaLoading] = useState(false)
  const [cifLoading, setCifLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [info, setInfo] = useState<string | null>(null)

  const [formulaResult, setFormulaResult] = useState<FormulaQueryResult | null>(null)
  const [cifResult, setCifResult] = useState<CifParseResult | null>(null)

  const normalizedElement = normalizeSymbol(elementQuery)
  const simpleElementMass = normalizedElement ? elements[normalizedElement] : undefined

  const handleFormulaLookup = async () => {
    const formula = formulaQuery.trim()
    if (!formula) {
      setError('Enter a chemical formula to query Materials Project.')
      setFormulaResult(null)
      return
    }

    setFormulaLoading(true)
    setError(null)
    setInfo(null)

    try {
      const result = await queryFormula(formula)
      setFormulaResult(result)
      setInfo(
        result.num_matches > 1
          ? `Found ${result.num_matches} matches; showing the most stable entry (${result.material_id}).`
          : `Loaded Materials Project entry ${result.material_id}.`,
      )
    } catch (err) {
      setFormulaResult(null)
      if (err instanceof MagnetApiError) {
        setError(err.detail)
      } else if (err instanceof Error) {
        setError(err.message)
      } else {
        setError('Formula lookup failed.')
      }
    } finally {
      setFormulaLoading(false)
    }
  }

  const handleCifUpload = async (file: File | null) => {
    if (!file) return

    if (!file.name.toLowerCase().endsWith('.cif')) {
      setError('Please upload a .cif crystallographic information file.')
      return
    }

    setCifLoading(true)
    setError(null)
    setInfo(null)
    setSelectedCifName(file.name)

    try {
      const result = await parseCif(file)
      setCifResult(result)
      setInfo(`Parsed ${result.filename ?? file.name} successfully.`)
    } catch (err) {
      setCifResult(null)
      if (err instanceof MagnetApiError) {
        setError(err.detail)
      } else if (err instanceof Error) {
        setError(err.message)
      } else {
        setError('CIF parsing failed.')
      }
    } finally {
      setCifLoading(false)
    }
  }

  return (
    <section className="panel search-panel">
      <header className="panel-header search-toolbar">
        <div>
          <h2>Magnet Analytics Search</h2>
          <p>Look up elements, query Materials Project formulas, or parse local CIF structures.</p>
        </div>

        <div className="search-mode-switcher" role="tablist" aria-label="Search mode">
          <button
            type="button"
            role="tab"
            aria-selected={searchMode === 'simple'}
            className={`search-mode-switcher__btn${searchMode === 'simple' ? ' search-mode-switcher__btn--active' : ''}`}
            onClick={() => setSearchMode('simple')}
          >
            Simple Element
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={searchMode === 'advanced'}
            className={`search-mode-switcher__btn${searchMode === 'advanced' ? ' search-mode-switcher__btn--active' : ''}`}
            onClick={() => setSearchMode('advanced')}
          >
            Advanced Analytics
          </button>
        </div>
      </header>

      {searchMode === 'simple' ? (
        <div className="search-form">
          <div className="field-group">
            <label htmlFor={elementInputId}>Element symbol</label>
            <input
              id={elementInputId}
              className="text-input"
              type="text"
              placeholder="e.g. Fe, Nd, B"
              value={elementQuery}
              onChange={(event) => setElementQuery(event.target.value)}
            />
          </div>

          {elementQuery.trim() && (
            <article className="result-card">
              <h3>Element Properties</h3>
              <dl className="result-list">
                <div className="result-row">
                  <dt>Symbol</dt>
                  <dd>{normalizedElement || '—'}</dd>
                </div>
                <div className="result-row">
                  <dt>Atomic mass</dt>
                  <dd>
                    {simpleElementMass !== undefined
                      ? `${simpleElementMass.toFixed(4)} u`
                      : 'Unknown element'}
                  </dd>
                </div>
              </dl>
            </article>
          )}
        </div>
      ) : (
        <div className="search-form">
          <div className="field-group">
            <label htmlFor={formulaInputId}>Formula lookup (Materials Project)</label>
            <div className="field-row">
              <input
                id={formulaInputId}
                className="text-input"
                type="text"
                placeholder="e.g. Nd2Fe14B"
                value={formulaQuery}
                onChange={(event) => setFormulaQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    event.preventDefault()
                    void handleFormulaLookup()
                  }
                }}
              />
              <button
                type="button"
                className="primary-btn"
                onClick={() => void handleFormulaLookup()}
                disabled={formulaLoading}
              >
                {formulaLoading ? 'Querying…' : 'Query Formula'}
              </button>
            </div>
          </div>

          <div className="field-group">
            <label htmlFor={cifInputId}>CIF structure upload</label>
            <div className="field-row">
              <input
                id={cifInputId}
                className="file-input-hidden"
                type="file"
                accept=".cif,application/cif,chemical/x-cif"
                onChange={(event) => {
                  const file = event.target.files?.[0] ?? null
                  void handleCifUpload(file)
                }}
              />
              <label htmlFor={cifInputId} className="file-btn">
                {cifLoading ? 'Parsing CIF…' : 'Choose CIF File'}
              </label>
              {selectedCifName && <span>{selectedCifName}</span>}
            </div>
          </div>

          {(error || info) && (
            <div className={`status-banner ${error ? 'status-banner--error' : 'status-banner--info'}`}>
              {error ?? info}
            </div>
          )}

          <div className={`results-grid${formulaResult && cifResult ? ' results-grid--split' : ''}`}>
            {formulaResult && (
              <article className="result-card">
                <h3>Magnetic &amp; Structural Summary</h3>
                <dl className="result-list">
                  <div className="result-row">
                    <dt>Material ID</dt>
                    <dd>{formulaResult.material_id}</dd>
                  </div>
                  <div className="result-row">
                    <dt>Formula</dt>
                    <dd>{formulaResult.formula}</dd>
                  </div>
                  <div className="result-row">
                    <dt>Magnetic moment</dt>
                    <dd>{formatNumber(formulaResult.total_magnetic_moment)} μB/f.u.</dd>
                  </div>
                  <div className="result-row">
                    <dt>Magnetic ordering</dt>
                    <dd>
                      {formulaResult.magnetic_ordering ??
                        formulaResult.magnetic_ordering_code ??
                        '—'}
                    </dd>
                  </div>
                  <div className="result-row">
                    <dt>Crystal system</dt>
                    <dd>{formulaResult.symmetry.crystal_system ?? '—'}</dd>
                  </div>
                  <div className="result-row">
                    <dt>Space group</dt>
                    <dd>
                      {formulaResult.symmetry.space_group_symbol
                        ? `${formulaResult.symmetry.space_group_symbol} (${formulaResult.symmetry.space_group_number ?? '—'})`
                        : '—'}
                    </dd>
                  </div>
                  <div className="result-row">
                    <dt>Energy above hull</dt>
                    <dd>{formatNumber(formulaResult.energy_above_hull, 6)} eV/atom</dd>
                  </div>
                </dl>
              </article>
            )}

            {cifResult && (
              <article className="result-card">
                <h3>CIF Lattice &amp; Density</h3>
                <dl className="result-list">
                  <div className="result-row">
                    <dt>Formula</dt>
                    <dd>{cifResult.formula}</dd>
                  </div>
                  <div className="result-row">
                    <dt>Crystal system</dt>
                    <dd>{cifResult.crystal_system}</dd>
                  </div>
                  <div className="result-row">
                    <dt>Space group</dt>
                    <dd>
                      {cifResult.space_group_symbol
                        ? `${cifResult.space_group_symbol} (${cifResult.space_group_number ?? '—'})`
                        : '—'}
                    </dd>
                  </div>
                  <div className="result-row">
                    <dt>Unit-cell volume</dt>
                    <dd>{formatNumber(cifResult.volume, 3)} Å³</dd>
                  </div>
                  <div className="result-row">
                    <dt>Theoretical density</dt>
                    <dd>{formatNumber(cifResult.density, 4)} g/cm³</dd>
                  </div>
                  <div className="result-row">
                    <dt>Number of sites</dt>
                    <dd>{cifResult.num_sites}</dd>
                  </div>
                </dl>

                <div className="lattice-grid" aria-label="Lattice parameters">
                  <div className="lattice-cell">
                    <span>a (Å)</span>
                    <strong>{formatNumber(cifResult.lattice.a, 4)}</strong>
                  </div>
                  <div className="lattice-cell">
                    <span>b (Å)</span>
                    <strong>{formatNumber(cifResult.lattice.b, 4)}</strong>
                  </div>
                  <div className="lattice-cell">
                    <span>c (Å)</span>
                    <strong>{formatNumber(cifResult.lattice.c, 4)}</strong>
                  </div>
                  <div className="lattice-cell">
                    <span>α (°)</span>
                    <strong>{formatNumber(cifResult.lattice.alpha, 3)}</strong>
                  </div>
                  <div className="lattice-cell">
                    <span>β (°)</span>
                    <strong>{formatNumber(cifResult.lattice.beta, 3)}</strong>
                  </div>
                  <div className="lattice-cell">
                    <span>γ (°)</span>
                    <strong>{formatNumber(cifResult.lattice.gamma, 3)}</strong>
                  </div>
                </div>
              </article>
            )}
          </div>
        </div>
      )}
    </section>
  )
}

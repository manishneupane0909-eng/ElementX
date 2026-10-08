import { useState } from 'react'
import {
  queryFormula,
  parseCif,
  MagnetApiError,
  type FormulaQueryResult,
  type CifParseResult,
} from '../services/magnetApi'
import Button from './ui/Button'
import DataList, { ResultRow } from './ui/DataList'
import FileUploadBar from './ui/FileUploadBar'
import Notice from './ui/Notice'
import Section from './ui/Section'
import TextField from './ui/TextField'

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

function failureMessage(err: unknown, fallback: string): string {
  if (err instanceof MagnetApiError) {
    return err.detail
  }
  if (err instanceof Error) {
    return err.message
  }
  return fallback
}

export default function Search({ elements, normalizeSymbol }: SearchProps) {
  const [elementQuery, setElementQuery] = useState('')
  const [formulaQuery, setFormulaQuery] = useState('Nd2Fe14B')
  const [cifFile, setCifFile] = useState<File | null>(null)

  const [formulaLoading, setFormulaLoading] = useState(false)
  const [cifLoading, setCifLoading] = useState(false)
  const [formulaError, setFormulaError] = useState<string | null>(null)
  const [formulaInfo, setFormulaInfo] = useState<string | null>(null)
  const [cifError, setCifError] = useState<string | null>(null)
  const [cifInfo, setCifInfo] = useState<string | null>(null)

  const [formulaResult, setFormulaResult] = useState<FormulaQueryResult | null>(null)
  const [cifResult, setCifResult] = useState<CifParseResult | null>(null)

  const normalizedElement = normalizeSymbol(elementQuery)
  const simpleElementMass = normalizedElement ? elements[normalizedElement] : undefined

  const handleFormulaLookup = async () => {
    const formula = formulaQuery.trim()
    if (!formula) {
      setFormulaError('Enter a chemical formula to query Materials Project.')
      setFormulaInfo(null)
      setFormulaResult(null)
      return
    }

    setFormulaLoading(true)
    setFormulaError(null)
    setFormulaInfo(null)

    try {
      const result = await queryFormula(formula)
      setFormulaResult(result)
      setFormulaInfo(
        result.num_matches > 1
          ? `Found ${result.num_matches} matches; showing the most stable entry (${result.material_id}).`
          : `Loaded Materials Project entry ${result.material_id}.`,
      )
    } catch (err) {
      setFormulaResult(null)
      setFormulaError(failureMessage(err, 'Formula lookup failed.'))
    } finally {
      setFormulaLoading(false)
    }
  }

  const handleCifUpload = async (file: File | null) => {
    setCifFile(file)
    if (!file) return

    if (!file.name.toLowerCase().endsWith('.cif')) {
      setCifError('Please upload a .cif crystallographic information file.')
      setCifInfo(null)
      return
    }

    setCifLoading(true)
    setCifError(null)
    setCifInfo(null)

    try {
      const result = await parseCif(file)
      setCifResult(result)
      setCifInfo(`Parsed ${result.filename ?? file.name} successfully.`)
    } catch (err) {
      setCifResult(null)
      setCifError(failureMessage(err, 'CIF parsing failed.'))
    } finally {
      setCifLoading(false)
    }
  }

  return (
    <div className="page">
      <p className="page-intro">
        Look up element masses, query Materials Project by formula, or analyze a local CIF
        structure file.
      </p>

      <Section
        title="Element lookup"
        description="Standard atomic mass from the periodic table built into ElementX."
      >
        <div className="control-row">
          <div className="form-field form-field--sm">
            <TextField
              label="Element symbol"
              type="text"
              placeholder="e.g. Fe"
              autoComplete="off"
              spellCheck={false}
              value={elementQuery}
              onChange={(event) => setElementQuery(event.target.value)}
            />
          </div>
        </div>

        {elementQuery.trim() && (
          <div className="result-block result-block--narrow">
            <DataList label="Element properties">
              <ResultRow label="Symbol" value={normalizedElement || '—'} />
              <ResultRow
                label="Atomic mass"
                value={
                  simpleElementMass !== undefined
                    ? `${simpleElementMass.toFixed(4)} u`
                    : 'Unknown element'
                }
              />
            </DataList>
          </div>
        )}
      </Section>

      <Section
        title="Materials Project search"
        description="Queries Materials Project through the ElementX backend by chemical formula."
      >
        <form
          className="control-row"
          onSubmit={(event) => {
            event.preventDefault()
            void handleFormulaLookup()
          }}
        >
          <div className="form-field form-field--md">
            <TextField
              label="Formula"
              type="text"
              placeholder="e.g. Nd2Fe14B"
              autoComplete="off"
              spellCheck={false}
              value={formulaQuery}
              onChange={(event) => setFormulaQuery(event.target.value)}
            />
          </div>
          <Button type="submit" variant="primary" disabled={formulaLoading}>
            {formulaLoading ? 'Querying…' : 'Query formula'}
          </Button>
        </form>

        {formulaError && <Notice kind="error">{formulaError}</Notice>}
        {formulaInfo && !formulaError && <p className="note" role="status">{formulaInfo}</p>}

        {formulaResult && (
          <div className="result-block">
            <Section level={3} title="Magnetic & structural summary">
              <DataList label="Materials Project summary" columns>
                <ResultRow label="Material ID" value={formulaResult.material_id} />
                <ResultRow label="Formula" value={formulaResult.formula} />
                <ResultRow
                  label="Magnetic moment"
                  value={`${formatNumber(formulaResult.total_magnetic_moment)} μB/f.u.`}
                />
                <ResultRow
                  label="Magnetic ordering"
                  value={
                    formulaResult.magnetic_ordering ??
                    formulaResult.magnetic_ordering_code ??
                    '—'
                  }
                />
                <ResultRow
                  label="Crystal system"
                  value={formulaResult.symmetry.crystal_system ?? '—'}
                />
                <ResultRow
                  label="Space group"
                  value={
                    formulaResult.symmetry.space_group_symbol
                      ? `${formulaResult.symmetry.space_group_symbol} (${formulaResult.symmetry.space_group_number ?? '—'})`
                      : '—'
                  }
                />
                <ResultRow
                  label="Energy above hull"
                  value={`${formatNumber(formulaResult.energy_above_hull, 6)} eV/atom`}
                />
              </DataList>
            </Section>
          </div>
        )}
      </Section>

      <Section
        title="CIF analysis"
        description="Parses a local .cif file on the backend for lattice parameters, symmetry and theoretical density."
      >
        <div className="upload-block">
          <FileUploadBar
            label="CIF structure file"
            accept=".cif,application/cif,chemical/x-cif"
            file={cifFile}
            onFileChange={(file) => void handleCifUpload(file)}
            chooseLabel={cifLoading ? 'Parsing CIF…' : 'Choose CIF file'}
            busy={cifLoading}
            emptyText="No file selected. The file is parsed as soon as you choose it."
          />
        </div>

        {cifError && <Notice kind="error">{cifError}</Notice>}
        {cifInfo && !cifError && <p className="note" role="status">{cifInfo}</p>}

        {cifResult && (
          <div className="result-block">
            <Section level={3} title="Lattice & density">
              <DataList label="CIF structure summary" columns>
                <ResultRow label="Formula" value={cifResult.formula} />
                <ResultRow label="Crystal system" value={cifResult.crystal_system} />
                <ResultRow
                  label="Space group"
                  value={
                    cifResult.space_group_symbol
                      ? `${cifResult.space_group_symbol} (${cifResult.space_group_number ?? '—'})`
                      : '—'
                  }
                />
                <ResultRow
                  label="Unit-cell volume"
                  value={`${formatNumber(cifResult.volume, 3)} Å³`}
                />
                <ResultRow
                  label="Theoretical density"
                  value={`${formatNumber(cifResult.density, 4)} g/cm³`}
                />
                <ResultRow label="Number of sites" value={String(cifResult.num_sites)} />
              </DataList>
              <dl className="lattice-line" aria-label="Lattice parameters">
                <div>
                  <dt>a (Å)</dt>
                  <dd>{formatNumber(cifResult.lattice.a, 4)}</dd>
                </div>
                <div>
                  <dt>b (Å)</dt>
                  <dd>{formatNumber(cifResult.lattice.b, 4)}</dd>
                </div>
                <div>
                  <dt>c (Å)</dt>
                  <dd>{formatNumber(cifResult.lattice.c, 4)}</dd>
                </div>
                <div>
                  <dt>α (°)</dt>
                  <dd>{formatNumber(cifResult.lattice.alpha, 3)}</dd>
                </div>
                <div>
                  <dt>β (°)</dt>
                  <dd>{formatNumber(cifResult.lattice.beta, 3)}</dd>
                </div>
                <div>
                  <dt>γ (°)</dt>
                  <dd>{formatNumber(cifResult.lattice.gamma, 3)}</dd>
                </div>
              </dl>
            </Section>
          </div>
        )}
      </Section>
    </div>
  )
}

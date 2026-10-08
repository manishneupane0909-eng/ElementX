/**
 * Read-only access to the portfolio-demo snapshots in `public/demo/` (served as static files).
 *
 * The snapshots are produced by `backend/scripts/build_demo_data.py` from the real backend
 * pipeline. This module only fetches and returns them; it performs no scientific calculation.
 */
import type {
  CopilotReply,
  CopilotStatus,
  FormulaQueryResult,
  SampleDetail,
  SampleSummary,
  SavedExperiment,
} from '../services/magnetApi'

const SUPPORTED_SCHEMA = 1

export interface DemoManifest {
  schema_version: number
  record_time_note: string
  featured: { sample_id: string; experiment_id: string }
  samples: { id: string; name: string; data_kind: string; experiment_id: string }[]
  redactions: { removed_metadata_keys: string[]; scope: string; original_unmodified_at: string }
  pipelines: { magnetometry: string; xrd: string }
  raw_instrument_files_published: boolean
}

export interface DemoMaterials {
  source: {
    name: string
    url: string
    license: string
    license_url: string
    retrieved: string
    note: string
  }
  formulas: string[]
  entries: Record<string, FormulaQueryResult>
}

interface DemoCopilot {
  status: CopilotStatus
  note: string
  replies: Record<string, CopilotReply & { prompt: string }>
}

export class DemoDataError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'DemoDataError'
  }
}

const cache = new Map<string, Promise<unknown>>()

function load<T>(path: string): Promise<T> {
  const cached = cache.get(path)
  if (cached) return cached as Promise<T>
  const url = `${import.meta.env.BASE_URL}demo/${path}`
  const request = fetch(url)
    .then(async (response) => {
      if (!response.ok) {
        throw new DemoDataError(`The example data file “${path}” could not be loaded.`)
      }
      return (await response.json()) as T
    })
    .catch((err: unknown) => {
      cache.delete(path)
      throw err instanceof DemoDataError
        ? err
        : new DemoDataError(`The example data file “${path}” could not be loaded.`)
    })
  cache.set(path, request)
  return request as Promise<T>
}

function safeId(id: string): string {
  // Ids are fixed UUIDs; refuse anything else so a request can never leave demo/.
  if (!/^[0-9a-f-]{36}$/i.test(id)) throw new DemoDataError('That example record does not exist.')
  return id
}

export async function getManifest(): Promise<DemoManifest> {
  const manifest = await load<DemoManifest>('manifest.json')
  if (manifest.schema_version !== SUPPORTED_SCHEMA) {
    throw new DemoDataError('The example data was built for a different version of this app.')
  }
  return manifest
}

export async function demoListSamples(): Promise<SampleSummary[]> {
  await getManifest()
  return load<SampleSummary[]>('samples.json')
}

export async function demoGetSample(sampleId: string): Promise<SampleDetail> {
  return load<SampleDetail>(`samples/${safeId(sampleId)}.json`)
}

export async function demoGetExperiment(experimentId: string): Promise<SavedExperiment> {
  return load<SavedExperiment>(`experiments/${safeId(experimentId)}.json`)
}

export async function demoGetCopilotStatus(): Promise<CopilotStatus> {
  return (await load<DemoCopilot>('copilot.json')).status
}

/** The recorded reply for the chosen sample (or the overview). The wording of the question is not used. */
export async function demoSendCopilotMessage(sampleId: string | null): Promise<CopilotReply> {
  const copilot = await load<DemoCopilot>('copilot.json')
  const reply = copilot.replies[sampleId ?? 'overview']
  if (!reply) throw new DemoDataError('No recorded reply exists for that sample.')
  const { prompt: _prompt, ...rest } = reply
  void _prompt
  return rest
}

export function getDemoMaterials(): Promise<DemoMaterials> {
  return load<DemoMaterials>('materials.json')
}

export async function demoQueryFormula(formula: string): Promise<FormulaQueryResult> {
  const materials = await getDemoMaterials()
  const wanted = formula.trim().toLowerCase()
  const key = materials.formulas.find((candidate) => candidate.toLowerCase() === wanted)
  const entry = key ? materials.entries[key] : undefined
  if (!entry) {
    throw new DemoDataError(
      `The demo only includes these example formulas: ${materials.formulas.join(', ')}.`,
    )
  }
  return entry
}

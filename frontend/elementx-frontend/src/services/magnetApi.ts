/**
 * TypeScript client for the ElementX Material Science Magnet Analytics API.
 */

import { API_BASE_URL, authFetch } from './apiClient';
import { DEMO_MODE, DemoDisabledError } from '../demo/demoMode';
import {
  demoGetCopilotStatus,
  demoGetExperiment,
  demoGetSample,
  demoListSamples,
  demoQueryFormula,
  demoSendCopilotMessage,
} from '../demo/demoData';

export interface SymmetryInfo {
  crystal_system: string | null;
  space_group_symbol: string | null;
  space_group_number: number | null;
}

export interface FormulaQueryResult {
  material_id: string;
  formula: string;
  symmetry: SymmetryInfo;
  /** Total magnetization in μB per formula unit (Materials Project convention). */
  total_magnetic_moment: number | null;
  /** Human-readable ordering, e.g. ferromagnetic, ferrimagnetic. */
  magnetic_ordering: string | null;
  /** MP ordering code, e.g. FM, FiM, AFM, NM. */
  magnetic_ordering_code: string | null;
  energy_above_hull: number | null;
  /** Crystallographic unit-cell volume in Å³ */
  unit_cell_volume: number | null;
  num_matches: number;
}

export interface LatticeParameters {
  a: number;
  b: number;
  c: number;
  alpha: number;
  beta: number;
  gamma: number;
}

export interface CifParseResult {
  formula: string;
  num_sites: number;
  lattice: LatticeParameters;
  /** Unit-cell volume in Å³ */
  volume: number;
  crystal_system: string;
  space_group_symbol: string | null;
  space_group_number: number | null;
  /** Theoretical density in g/cm³ */
  density: number;
  filename: string | null;
}

export interface CriticalityBreakdownItem {
  element: string;
  stoichiometry: number;
  mole_fraction: number;
  element_criticality: number;
  contribution: number;
}

export interface HighRiskComponent {
  element: string;
  mole_fraction: number;
  element_criticality: number;
  contribution: number;
}

export interface CriticalityResult {
  formula: string;
  /** Supply Chain Criticality Score, 0 (sustainable) to 100 (critical). */
  total_score: number;
  risk_level: 'low' | 'moderate' | 'elevated' | 'critical';
  high_risk_components: HighRiskComponent[];
  element_breakdown: CriticalityBreakdownItem[];
}

export interface TheoreticalLimitsAssumptions {
  moment_units: string;
  volume_units: string;
  bhmax_model: string;
  note: string;
}

export interface TheoreticalLimitsResult {
  magnetic_moment_mu_b_per_fu: number;
  unit_cell_volume_angstrom3: number;
  formula_units_per_cell: number;
  magnetization_a_per_m: number;
  /** Saturation magnetization Ms in tesla. */
  saturation_magnetization_tesla: number;
  bhmax_j_m3: number;
  /** Maximum energy product upper bound in kJ/m³. */
  bhmax_kj_m3: number;
  /** Maximum energy product upper bound in MGOe. */
  bhmax_mgoe: number;
  assumptions: TheoreticalLimitsAssumptions;
}

export interface AnalyzeMagnetDataSources {
  materials_project: boolean;
  material_id?: string;
  magnetic_moment_source?: 'materials_project' | 'request' | null;
  volume_source?: 'materials_project' | 'request' | null;
}

export interface AnalyzeMagnetRequest {
  formula: string;
  /** μB per formula unit; omit to fetch from Materials Project. */
  magnetic_moment?: number;
  /** Unit-cell volume in Å³; omit to fetch from Materials Project. */
  volume?: number;
  /** Formula units Z per unit cell (default 1; use 8 for Nd2Fe14B). */
  formula_units_per_cell?: number;
  /** When true, missing moment/volume are fetched from MP (default true). */
  fetch_from_materials_project?: boolean;
}

export interface AnalyzeMagnetResult {
  formula: string;
  material_id: string | null;
  magnetic_ordering: string | null;
  criticality: CriticalityResult;
  theoretical_limits: TheoreticalLimitsResult | null;
  data_sources: AnalyzeMagnetDataSources;
}

export interface ApiErrorBody {
  detail: string | { msg: string; type?: string }[];
}

export class MagnetApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = 'MagnetApiError';
    this.status = status;
    this.detail = detail;
  }
}

function formatApiError(body: ApiErrorBody, fallback: string): string {
  if (typeof body.detail === 'string') {
    return body.detail;
  }
  if (Array.isArray(body.detail) && body.detail.length > 0) {
    return body.detail.map((item) => item.msg).join('; ');
  }
  return fallback;
}

async function handleResponse<T>(response: Response, fallbackMessage: string): Promise<T> {
  if (response.ok) {
    return (await response.json()) as T;
  }

  let detail = fallbackMessage;
  try {
    const body = (await response.json()) as ApiErrorBody;
    detail = formatApiError(body, fallbackMessage);
  } catch {
    detail = response.statusText || fallbackMessage;
  }

  throw new MagnetApiError(response.status, detail);
}

/**
 * Query Materials Project for structural symmetry and magnetic properties.
 */
export async function queryFormula(formula: string): Promise<FormulaQueryResult> {
  if (DEMO_MODE) return demoQueryFormula(formula);
  const response = await authFetch(`${API_BASE_URL}/api/query-formula`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ formula }),
  });

  return handleResponse<FormulaQueryResult>(
    response,
    'Failed to query formula from Materials Project.',
  );
}

/**
 * Upload and parse a local CIF file.
 */
export async function parseCif(file: File): Promise<CifParseResult> {
  if (DEMO_MODE) throw new DemoDisabledError('CIF upload');
  const formData = new FormData();
  formData.append('file', file);

  const response = await authFetch(`${API_BASE_URL}/api/parse-cif`, {
    method: 'POST',
    body: formData,
  });

  return handleResponse<CifParseResult>(response, 'Failed to parse CIF file.');
}

/**
 * Analyze permanent-magnet supply-chain criticality and theoretical (BH)max limits.
 */
export async function analyzeMagnet(
  payload: AnalyzeMagnetRequest,
): Promise<AnalyzeMagnetResult> {
  if (DEMO_MODE) throw new DemoDisabledError('Live analysis');
  const response = await authFetch(`${API_BASE_URL}/api/analyze-magnet`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      formula_units_per_cell: 1,
      fetch_from_materials_project: true,
      ...payload,
    }),
  });

  return handleResponse<AnalyzeMagnetResult>(
    response,
    'Failed to analyze permanent magnet properties.',
  );
}

export interface MagnetometryFileInfo {
  filename: string | null;
  format: string;
}

export interface MagnetometrySummary {
  mh_segment_count: number;
  mt_segment_count: number;
  unknown_segment_count: number;
  normalization_available: boolean;
}

export interface MeasurementSegmentData {
  temperature_K: number[];
  field_Oe: number[];
  moment_emu: number[];
  source_index: number[];
}

export interface MeasurementSegment {
  type: string;
  start_index: number;
  end_index: number;
  point_count: number;
  valid_point_count: number;
  temperature_range_K: number[];
  field_range_Oe: number[];
  mean_temperature_K: number | null;
  mean_field_Oe: number | null;
  duration_sec: number | null;
  confidence: number;
  warnings: string[];
  data: MeasurementSegmentData;
}

export interface MagnetometrySegmentation {
  segment_count: number;
  warnings: string[];
  segments: MeasurementSegment[];
}

export interface HysteresisAnalysis {
  Hc_negative_Oe: number | null;
  Hc_positive_Oe: number | null;
  Mr_negative_emu: number | null;
  Mr_positive_emu: number | null;
  coercive_center_shift_Oe: number | null;
  coercive_half_width_Oe: number | null;
  temperature_range_K: number[];
  field_range_Oe: number[];
  mean_temperature_K: number | null;
  warnings: string[];
}

export interface HighFieldAnalysis {
  maximum_positive_field_Oe: number | null;
  maximum_negative_field_Oe: number | null;
  moment_at_max_positive_field_emu: number | null;
  moment_at_max_negative_field_emu: number | null;
  maximum_absolute_measured_moment_emu: number | null;
  /** |H| at or above which the backend selects the high-field region of the full loop. */
  high_field_threshold_Oe?: number | null;
  positive_high_field_slope_emu_per_Oe: number | null;
  negative_high_field_slope_emu_per_Oe: number | null;
  positive_high_field_r_squared: number | null;
  negative_high_field_r_squared: number | null;
  positive_relative_high_field_slope: number | null;
  negative_relative_high_field_slope: number | null;
  relative_slope_disagreement: number | null;
  high_field_magnitude_asymmetry: number | null;
  saturation_evidence_quality: string;
  warnings: string[];
}

export interface MassCandidate {
  value_mg: number;
  unit: string;
  raw_value: string;
  source: string;
  source_key?: string;
  matched_tokens?: string[];
}

export interface MassProvenance {
  mass_candidates: MassCandidate[];
  rejected_candidates: MassCandidate[];
  resolved_mass_mg: number | null;
  resolved_source: string | null;
  resolution_status: string;
  normalization_allowed: boolean;
  sources_agree: boolean | null;
  filename_masses_ambiguous: boolean;
  warnings: string[];
}

export interface NormalizedMoment {
  input_moment_emu: number;
  resolved_mass_mg: number;
  mass_source: string;
  specific_magnetization_emu_per_g: number;
  specific_magnetization_Am2_per_kg: number;
  units: {
    input_moment: string;
    mass: string;
    specific_magnetization_cgs: string;
    specific_magnetization_si: string;
  };
}

export interface NormalizedResults {
  available: boolean;
  reason: string | null;
  Mr_negative: NormalizedMoment | null;
  Mr_positive: NormalizedMoment | null;
  maximum_measured_moment: NormalizedMoment | null;
  moment_at_max_positive_field: NormalizedMoment | null;
  moment_at_max_negative_field: NormalizedMoment | null;
}

export interface MHSegmentRef {
  start_index: number | null;
  end_index: number | null;
  mean_temperature_K: number | null;
}

export interface MHAnalysisBody {
  segment: MHSegmentRef;
  hysteresis: HysteresisAnalysis;
  high_field: HighFieldAnalysis;
  mass_provenance: MassProvenance;
  normalized: NormalizedResults;
  warnings: string[];
}

export interface MHAnalysisEntry {
  segment_index: number;
  analysis: MHAnalysisBody;
}

export interface MagnetometryAnalyzeResult {
  file: MagnetometryFileInfo;
  metadata: Record<string, string>;
  segmentation: MagnetometrySegmentation;
  mh_analyses: MHAnalysisEntry[];
  summary: MagnetometrySummary;
  warnings: string[];
  analysis_version?: string;
}

export interface XrdFileInfo {
  filename: string;
  format: string;
}

export interface XrdSeries {
  two_theta_deg: number[];
  intensity: number[];
}

export interface XrdSummary {
  point_count: number;
  two_theta_min_deg: number;
  two_theta_max_deg: number;
  intensity_min: number;
  intensity_max: number;
}

export interface XrdCandidatePeak {
  two_theta_deg: number;
  intensity: number;
}

export interface XrdPeakDetection {
  method: string;
  label: string;
  prominence_fraction_of_max: number;
  min_distance_points: number;
}

export interface XrdAnalysisResult {
  analysis_version: string;
  file: XrdFileInfo;
  series: XrdSeries;
  summary: XrdSummary;
  peaks: XrdCandidatePeak[];
  peak_detection?: XrdPeakDetection;
  warnings: string[];
}

export type ExperimentAnalysis = MagnetometryAnalyzeResult | XrdAnalysisResult;

/**
 * Upload and analyze a Quantum Design / VersaLab .DAT magnetometry file.
 */
export async function analyzeMagnetometry(
  file: File,
  userConfirmedMassMg?: number,
): Promise<MagnetometryAnalyzeResult> {
  if (DEMO_MODE) throw new DemoDisabledError('File upload');
  const formData = new FormData();
  formData.append('file', file);
  if (userConfirmedMassMg !== undefined) {
    formData.append('user_confirmed_mass_mg', String(userConfirmedMassMg));
  }

  const response = await authFetch(`${API_BASE_URL}/api/magnetometry/analyze`, {
    method: 'POST',
    body: formData,
  });

  return handleResponse<MagnetometryAnalyzeResult>(
    response,
    'Failed to analyze magnetometry file.',
  );
}

/** Present only in the portfolio demo: what kind of data a record holds. */
export type DemoDataKind = 'real-measurement' | 'synthetic';

export interface DemoLabel {
  data_kind: DemoDataKind;
  label: string;
}

/** Provenance recorded for a public demo copy of an example file (demo snapshots only). */
export interface DemoProvenance extends DemoLabel {
  description: string;
  source_file: string;
  source_sha256: string;
  source_bytes: number;
  analysis_pipeline: string;
  modifications: string[];
}

export interface SampleSummary {
  demo?: DemoLabel;
  id: string;
  name: string;
  formula: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
  experiment_count?: number;
}

export interface ExperimentSummary {
  demo?: DemoLabel;
  id: string;
  experiment_type: string;
  original_filename: string;
  uploaded_at: string;
  analysis_version: string;
}

export interface SampleDetail extends SampleSummary {
  experiments: ExperimentSummary[];
}

interface SavedExperimentBase {
  demo?: DemoProvenance;
  id: string;
  sample_id: string;
  original_filename: string;
  uploaded_at: string;
  analysis_version: string;
  user_confirmed_mass_mg: number | null;
}

export interface SavedMagnetometryExperiment extends SavedExperimentBase {
  experiment_type: 'magnetometry';
  analysis_json: MagnetometryAnalyzeResult;
}

export interface SavedXrdExperiment extends SavedExperimentBase {
  experiment_type: 'xrd';
  analysis_json: XrdAnalysisResult;
}

export type SavedExperiment = SavedMagnetometryExperiment | SavedXrdExperiment;

export function isXrdAnalysisResult(
  analysis: ExperimentAnalysis,
): analysis is XrdAnalysisResult {
  return (
    'series' in analysis &&
    analysis.series != null &&
    Array.isArray(analysis.series.two_theta_deg)
  );
}

const RESEARCH_SAMPLES = `${API_BASE_URL}/api/research/samples`;
const RESEARCH_EXPERIMENTS = `${API_BASE_URL}/api/research/experiments`;

export async function createSample(body: {
  name: string;
  formula?: string;
  notes?: string;
}): Promise<SampleSummary> {
  if (DEMO_MODE) throw new DemoDisabledError('Creating samples');
  const response = await authFetch(RESEARCH_SAMPLES, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return handleResponse<SampleSummary>(response, 'Failed to create sample.');
}

export async function listSamples(): Promise<SampleSummary[]> {
  if (DEMO_MODE) return demoListSamples();
  const response = await authFetch(RESEARCH_SAMPLES);
  return handleResponse<SampleSummary[]>(response, 'Failed to load samples.');
}

export async function getSample(sampleId: string): Promise<SampleDetail> {
  if (DEMO_MODE) return demoGetSample(sampleId);
  const response = await authFetch(`${RESEARCH_SAMPLES}/${sampleId}`);
  return handleResponse<SampleDetail>(response, 'Failed to load sample.');
}

export async function createSampleExperiment(
  sampleId: string,
  file: File,
  userConfirmedMassMg?: number,
): Promise<SavedMagnetometryExperiment> {
  if (DEMO_MODE) throw new DemoDisabledError('Saving experiments');
  const formData = new FormData();
  formData.append('file', file);
  if (userConfirmedMassMg !== undefined) {
    formData.append('user_confirmed_mass_mg', String(userConfirmedMassMg));
  }

  const response = await authFetch(`${RESEARCH_SAMPLES}/${sampleId}/experiments`, {
    method: 'POST',
    body: formData,
  });

  return handleResponse<SavedMagnetometryExperiment>(
    response,
    'Failed to save magnetometry experiment.',
  );
}

export async function createXrdExperiment(
  sampleId: string,
  file: File,
): Promise<SavedXrdExperiment> {
  if (DEMO_MODE) throw new DemoDisabledError('Saving experiments');
  const formData = new FormData();
  formData.append('file', file);

  const response = await authFetch(`${RESEARCH_SAMPLES}/${sampleId}/xrd-experiments`, {
    method: 'POST',
    body: formData,
  });

  return handleResponse<SavedXrdExperiment>(
    response,
    'Failed to save XRD experiment.',
  );
}

export async function getExperiment(experimentId: string): Promise<SavedExperiment> {
  if (DEMO_MODE) return demoGetExperiment(experimentId);
  const response = await authFetch(`${RESEARCH_EXPERIMENTS}/${experimentId}`);
  return handleResponse<SavedExperiment>(response, 'Failed to load experiment.');
}

export interface CopilotHistoryMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface CopilotStatus {
  llmAvailable: boolean;
  model: string;
  researchContext: boolean;
}

export interface CopilotReply {
  answer: string;
  /** 'stored-records' when no language model produced the text. */
  source: string;
  sampleId: string | null;
  sampleName: string | null;
  researchContext: boolean;
  llmAvailable: boolean;
}

export async function getCopilotStatus(): Promise<CopilotStatus> {
  if (DEMO_MODE) return demoGetCopilotStatus();
  const response = await authFetch(`${API_BASE_URL}/api/research-copilot/status`);
  return handleResponse<CopilotStatus>(response, 'Failed to load Copilot status.');
}

export async function sendCopilotMessage(
  message: string,
  sampleId: string | null,
  history: CopilotHistoryMessage[],
): Promise<CopilotReply> {
  if (DEMO_MODE) return demoSendCopilotMessage(sampleId);
  const response = await authFetch(`${API_BASE_URL}/api/research-copilot/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message,
      sample_id: sampleId,
      history: history.slice(-6),
    }),
  });
  return handleResponse<CopilotReply>(response, 'The Copilot request failed.');
}

export const magnetApi = {
  queryFormula,
  parseCif,
  analyzeMagnet,
  analyzeMagnetometry,
  createSample,
  listSamples,
  getSample,
  createSampleExperiment,
  createXrdExperiment,
  getExperiment,
  getCopilotStatus,
  sendCopilotMessage,
};

export default magnetApi;

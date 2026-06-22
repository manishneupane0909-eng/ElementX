import React, { useState, useEffect } from 'react';
import { Calculator, Database, LineChart, Magnet, Download, Copy, LogOut, Upload, Save, MessageSquare, FileText, Send } from 'lucide-react';
import api from './api/api';
import { XRDPlot, MagneticPlot } from './components/Plots';

const ELEMENTS = {
  'H': 1.008, 'He': 4.003, 'Li': 6.941, 'Be': 9.012, 'B': 10.81, 'C': 12.01,
  'N': 14.01, 'O': 16.00, 'F': 19.00, 'Ne': 20.18, 'Na': 22.99, 'Mg': 24.31,
  'Al': 26.98, 'Si': 28.09, 'P': 30.97, 'S': 32.07, 'Cl': 35.45, 'Ar': 39.95,
  'K': 39.10, 'Ca': 40.08, 'Sc': 44.96, 'Ti': 47.87, 'V': 50.94, 'Cr': 52.00,
  'Mn': 54.94, 'Fe': 55.845, 'Co': 58.933, 'Ni': 58.693, 'Cu': 63.546, 'Zn': 65.38,
  'Ga': 69.72, 'Ge': 72.630, 'As': 74.92, 'Se': 78.96, 'Br': 79.90, 'Kr': 83.80,
  'Rb': 85.47, 'Sr': 87.62, 'Y': 88.91, 'Zr': 91.22, 'Nb': 92.91, 'Mo': 95.95,
  'Tc': 98.00, 'Ru': 101.07, 'Rh': 102.91, 'Pd': 106.42, 'Ag': 107.87, 'Cd': 112.41,
  'In': 114.82, 'Sn': 118.71, 'Sb': 121.76, 'Te': 127.60, 'I': 126.90, 'Xe': 131.29,
  'Cs': 132.91, 'Ba': 137.33, 'La': 138.91, 'Ce': 140.12, 'Pr': 140.91, 'Nd': 144.24,
  'Pm': 145.00, 'Sm': 150.36, 'Eu': 151.96, 'Gd': 157.25, 'Tb': 158.93, 'Dy': 162.50,
  'Ho': 164.93, 'Er': 167.26, 'Tm': 168.93, 'Yb': 173.05, 'Lu': 174.97, 'Hf': 178.49,
  'Ta': 180.95, 'W': 183.84, 'Re': 186.21, 'Os': 190.23, 'Ir': 192.22, 'Pt': 195.08,
  'Au': 196.97, 'Hg': 200.59, 'Tl': 204.38, 'Pb': 207.2, 'Bi': 208.98, 'Po': 209.00,
  'At': 210.00, 'Rn': 222.00
};

function parseFormula(formula) {
  // Supports integer or decimal stoichiometry, e.g. Mn1.5In0.5Sb
  const regex = /([A-Z][a-z]?)(\d+(?:\.\d+)?|\.\d+)?/g;
  const composition = {};
  let match;
  if (!formula.trim()) throw new Error("Formula cannot be empty.");

  while ((match = regex.exec(formula))) {
    const element = match[1];
    const count = match[2] ? parseFloat(match[2]) : 1;
    if (!ELEMENTS[element]) throw new Error(`Unknown element: ${element}`);
    if (!Number.isFinite(count) || count <= 0) {
      throw new Error(`Invalid stoichiometry for ${element}: "${match[2]}"`);
    }
    composition[element] = (composition[element] || 0) + count;
  }
  if (Object.keys(composition).length === 0) {
    throw new Error("Invalid formula structure or no recognized elements.");
  }
  return composition;
}

const ELEMENT_NAME_ALIASES = {
  // Common full-name inputs (and one common misspelling)
  indium: 'In',
  indeium: 'In',
};

function normalizeElementSymbol(input) {
  const raw = String(input || '').trim();
  if (!raw) return '';

  // If user typed a full element name, map it.
  const byName = ELEMENT_NAME_ALIASES[raw.toLowerCase()];
  if (byName) return byName;

  // If user typed symbol with wrong casing (e.g., "in" or "IN"), normalize.
  if (raw.length === 1) return raw.toUpperCase();
  if (raw.length === 2) return raw[0].toUpperCase() + raw[1].toLowerCase();

  return raw;
}

function LoginForm({ onLogin, onDemo }) {
  const [isRegister, setIsRegister] = useState(false);
  const [formData, setFormData] = useState({ email: '', password: '', name: '', institution: '' });
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [demoLoading, setDemoLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSubmitting(true);

    try {
      let result;
      if (isRegister) {
        result = await api.auth.register(formData);
      } else {
        result = await api.auth.login(formData);
      }
      onLogin(result.user);
    } catch (err) {
      setError(err.message || "Authentication failed.");
    } finally {
      setSubmitting(false);
    }
  };

  const inputStyle = {
    width: '100%',
    padding: '12px 16px',
    border: '2px solid #e2e8f0',
    borderRadius: '8px',
    fontSize: '15px',
    outline: 'none'
  };

  return (
    <div style={{
      minHeight: '100vh',
      background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '20px'
    }}>
      <div style={{
        background: 'white',
        borderRadius: '16px',
        boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
        padding: '40px',
        width: '100%',
        maxWidth: '450px'
      }}>
        <div style={{ textAlign: 'center', marginBottom: '30px' }}>
          <div style={{
            width: '60px',
            height: '60px',
            background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
            borderRadius: '12px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            margin: '0 auto 15px'
          }}>
            <Calculator size={32} color="white" />
          </div>
          <h1 style={{ fontSize: '28px', fontWeight: '700', color: '#1a202c', margin: '0 0 5px 0' }}>
            ElementX
          </h1>
          <p style={{ fontSize: '14px', color: '#718096', margin: 0 }}>
            MnAl lab tools — stoichiometry, XRD, magnetometry
          </p>
          <p style={{ fontSize: '12px', color: '#a0aec0', margin: '8px 0 0' }}>
            RE-free magnets · sample tracking
          </p>
        </div>

        <form onSubmit={handleSubmit}>
          {isRegister && (
            <>
              <div style={{ marginBottom: '20px' }}>
                <label style={{
                  display: 'block',
                  fontSize: '13px',
                  fontWeight: '600',
                  color: '#4a5568',
                  marginBottom: '8px'
                }}>
                  Name
                </label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={e => setFormData({ ...formData, name: e.target.value })}
                  required
                  style={inputStyle}
                  disabled={submitting}
                />
              </div>
              <div style={{ marginBottom: '20px' }}>
                <label style={{
                  display: 'block',
                  fontSize: '13px',
                  fontWeight: '600',
                  color: '#4a5568',
                  marginBottom: '8px'
                }}>
                  Institution
                </label>
                <input
                  type="text"
                  value={formData.institution}
                  onChange={e => setFormData({ ...formData, institution: e.target.value })}
                  style={inputStyle}
                  disabled={submitting}
                />
              </div>
            </>
          )}
          <div style={{ marginBottom: '20px' }}>
            <label style={{
              display: 'block',
              fontSize: '13px',
              fontWeight: '600',
              color: '#4a5568',
              marginBottom: '8px'
            }}>
              Email
            </label>
            <input
              type="email"
              value={formData.email}
              onChange={e => setFormData({ ...formData, email: e.target.value })}
              required
              style={inputStyle}
              disabled={submitting}
            />
          </div>
          <div style={{ marginBottom: '20px' }}>
            <label style={{
              display: 'block',
              fontSize: '13px',
              fontWeight: '600',
              color: '#4a5568',
              marginBottom: '8px'
            }}>
              Password
            </label>
            <input
              type="password"
              value={formData.password}
              onChange={e => setFormData({ ...formData, password: e.target.value })}
              required
              style={inputStyle}
              disabled={submitting}
            />
          </div>

          {error && (
            <div style={{
              background: '#fee2e2',
              border: '1px solid #fca5a5',
              color: '#dc2626',
              padding: '10px',
              borderRadius: '6px',
              marginBottom: '20px',
              fontSize: '14px'
            }}>
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={submitting || demoLoading}
            style={{
              width: '100%',
              padding: '14px',
              background: submitting ? '#ccc' : 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
              color: 'white',
              border: 'none',
              borderRadius: '8px',
              fontSize: '16px',
              fontWeight: '600',
              cursor: submitting || demoLoading ? 'not-allowed' : 'pointer',
              marginBottom: '12px'
            }}
          >
            {submitting ? 'Processing...' : (isRegister ? 'Create Account' : 'Sign In')}
          </button>

          {!isRegister && onDemo && (
            <button
              type="button"
              disabled={submitting || demoLoading}
              onClick={async () => {
                setError('');
                setDemoLoading(true);
                try {
                  await onDemo();
                } catch (err) {
                  setError(err.message || 'Demo failed — is the backend running on :8000?');
                } finally {
                  setDemoLoading(false);
                }
              }}
              style={{
                width: '100%',
                padding: '14px',
                background: demoLoading ? '#e2e8f0' : '#0f766e',
                color: demoLoading ? '#94a3b8' : 'white',
                border: 'none',
                borderRadius: '8px',
                fontSize: '15px',
                fontWeight: '600',
                cursor: demoLoading ? 'wait' : 'pointer',
                marginBottom: '15px',
              }}
            >
              {demoLoading ? 'Loading…' : 'Try demo'}
            </button>
          )}

          <div style={{ textAlign: 'center', marginBottom: '15px' }}>
            <button
              type="button"
              onClick={() => { setIsRegister(!isRegister); setError(''); }}
              disabled={submitting}
              style={{
                background: 'none',
                border: 'none',
                color: '#667eea',
                fontSize: '14px',
                cursor: submitting ? 'not-allowed' : 'pointer',
                textDecoration: 'underline'
              }}
            >
              {isRegister ? 'Already have an account? Sign in' : "Don't have an account? Register"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function SamplePicker({ samples, value, onChange, disabled }) {
  return (
    <div style={{ flex: 1, minWidth: '220px' }}>
      <label style={{ display: 'block', fontSize: '13px', fontWeight: '600', color: '#4a5568', marginBottom: '8px' }}>
        Link to sample
      </label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        style={{
          width: '100%',
          padding: '12px 16px',
          border: '2px solid #e2e8f0',
          borderRadius: '8px',
          fontSize: '15px',
          background: 'white',
        }}
      >
        <option value="">— Select a sample —</option>
        {samples.map((s) => (
          <option key={s.id} value={s.id}>
            {s.name || s.formula} ({s.status || 'planned'})
          </option>
        ))}
      </select>
    </div>
  );
}

function SampleDetailPanel({
  sample,
  onClose,
  onRefresh,
  onSetOutcome,
  onRecommend,
  onExperimentBrief,
  aiLoading,
  experimentBrief,
}) {
  if (!sample) return null;

  const xrd = sample.characterization?.xrd;
  const mag = sample.characterization?.magnetic;
  const phase = sample.phaseAnalysis;
  const recommendations = sample.aiRecommendations || [];

  const outcomeBtn = (label, value, color) => (
    <button
      key={value}
      disabled={aiLoading}
      onClick={() => onSetOutcome && onSetOutcome(sample.id, value)}
      style={{
        padding: '6px 10px',
        background: sample.outcomeLabel === value ? color : '#f1f5f9',
        color: sample.outcomeLabel === value ? 'white' : '#475569',
        border: `1px solid ${sample.outcomeLabel === value ? color : '#e2e8f0'}`,
        borderRadius: '6px',
        cursor: aiLoading ? 'wait' : 'pointer',
        fontSize: '12px',
        fontWeight: '600',
      }}
    >
      {label}
    </button>
  );

  return (
    <div style={{
      marginTop: '20px',
      border: '2px solid #667eea',
      borderRadius: '12px',
      padding: '20px',
      background: '#f8fafc',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '16px' }}>
        <div>
          <h3 style={{ margin: '0 0 4px', fontSize: '20px', color: '#1a202c' }}>{sample.name}</h3>
          <div style={{ color: '#64748b', fontSize: '14px' }}>{sample.formula} · {sample.materialFamily} · {sample.status}</div>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            onClick={onRefresh}
            style={{ padding: '6px 12px', background: '#667eea', color: 'white', border: 'none', borderRadius: '6px', cursor: 'pointer', fontSize: '13px' }}
          >
            Refresh
          </button>
          <button
            onClick={onClose}
            style={{ padding: '6px 12px', background: '#e2e8f0', color: '#334155', border: 'none', borderRadius: '6px', cursor: 'pointer', fontSize: '13px' }}
          >
            Close
          </button>
        </div>
      </div>

      {sample.synthesis && (
        <div style={{ marginBottom: '14px', fontSize: '14px', color: '#475569' }}>
          <strong>Synthesis:</strong> {sample.synthesis.method}
          {sample.synthesis.anneal_temp_c != null && ` · ${sample.synthesis.anneal_temp_c}°C`}
          {sample.synthesis.anneal_time_h != null && ` · ${sample.synthesis.anneal_time_h} h`}
          {sample.synthesis.notes && ` · ${sample.synthesis.notes}`}
        </div>
      )}

      {sample.dopants?.length > 0 && (
        <div style={{ marginBottom: '14px', fontSize: '14px', color: '#475569' }}>
          <strong>Dopants:</strong> {sample.dopants.map((d) => `${d.element} ${(d.fraction * 100).toFixed(1)}%`).join(', ')}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '12px' }}>
        <div style={{ background: 'white', borderRadius: '8px', padding: '14px', border: '1px solid #e2e8f0' }}>
          <div style={{ fontWeight: '600', marginBottom: '8px', color: '#1e293b' }}>XRD</div>
          {xrd ? (
            <>
              <div style={{ fontSize: '13px', color: '#64748b' }}>{xrd.filename}</div>
              <div style={{ fontSize: '13px', marginTop: '6px' }}>Peaks: {xrd.peaks?.length ?? '—'} · Points: {xrd.pointCount ?? '—'}</div>
              {phase && (
                <div style={{
                  marginTop: '8px',
                  padding: '8px',
                  borderRadius: '6px',
                  background: phase.tauDetected ? '#dcfce7' : '#fef3c7',
                  color: phase.tauDetected ? '#166534' : '#92400e',
                  fontSize: '13px',
                }}>
                  τ-MnAl: {phase.tauDetected ? `detected (${phase.matchedPeakCount}/3 peaks, ${(phase.confidence * 100).toFixed(0)}%)` : 'not detected'}
                </div>
              )}
            </>
          ) : (
            <div style={{ color: '#94a3b8', fontSize: '13px' }}>No XRD uploaded</div>
          )}
        </div>

        <div style={{ background: 'white', borderRadius: '8px', padding: '14px', border: '1px solid #e2e8f0' }}>
          <div style={{ fontWeight: '600', marginBottom: '8px', color: '#1e293b' }}>Magnetometry</div>
          {mag ? (
            <>
              <div style={{ fontSize: '13px', color: '#64748b' }}>{mag.filename} ({mag.measurementType})</div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px', marginTop: '8px' }}>
                <div><span style={{ color: '#64748b', fontSize: '12px' }}>Ms</span><div style={{ fontWeight: '600' }}>{mag.properties?.Ms?.toFixed(2) ?? '—'}</div></div>
                <div><span style={{ color: '#64748b', fontSize: '12px' }}>Mr</span><div style={{ fontWeight: '600' }}>{mag.properties?.Mr?.toFixed(2) ?? '—'}</div></div>
                <div><span style={{ color: '#64748b', fontSize: '12px' }}>Hc</span><div style={{ fontWeight: '600' }}>{mag.properties?.Hc?.toFixed(2) ?? '—'}</div></div>
              </div>
            </>
          ) : (
            <div style={{ color: '#94a3b8', fontSize: '13px' }}>No magnetic data uploaded</div>
          )}
        </div>
      </div>

      {sample.xrdRecords?.[0]?.data?.length > 0 && (
        <div style={{ marginTop: '16px', border: '1px solid #e2e8f0', borderRadius: '10px', background: 'white' }}>
          <XRDPlot record={sample.xrdRecords[0]} title={`XRD pattern — ${sample.name}`} />
        </div>
      )}

      {sample.magneticRecords?.[0]?.data?.length > 0 && (
        <div style={{ marginTop: '16px', border: '1px solid #e2e8f0', borderRadius: '10px', background: 'white' }}>
          <MagneticPlot record={sample.magneticRecords[0]} title={`M-H loop — ${sample.name}`} />
        </div>
      )}

      <div style={{ marginTop: '16px', marginBottom: '14px' }}>
        <div style={{ fontSize: '13px', fontWeight: '600', color: '#334155', marginBottom: '8px' }}>
          Outcome (feeds the dopant ranker)
        </div>
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          {outcomeBtn('Success', 'success', '#16a34a')}
          {outcomeBtn('Partial', 'partial', '#d97706')}
          {outcomeBtn('Fail', 'fail', '#dc2626')}
          {sample.outcomeLabel && (
            <span style={{ fontSize: '12px', color: '#64748b', alignSelf: 'center' }}>
              Current: {sample.outcomeLabel}
            </span>
          )}
        </div>
      </div>

      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '16px' }}>
        <button
          disabled={aiLoading}
          onClick={() => onRecommend && onRecommend(sample.id)}
          style={{ padding: '8px 12px', background: '#7c3aed', color: 'white', border: 'none', borderRadius: '8px', cursor: 'pointer', fontSize: '13px' }}
        >
          {aiLoading ? 'Running…' : 'Suggest next alloy'}
        </button>
        <button
          disabled={aiLoading}
          onClick={() => onExperimentBrief && onExperimentBrief(sample.id)}
          style={{ padding: '8px 12px', background: '#0f766e', color: 'white', border: 'none', borderRadius: '8px', cursor: 'pointer', fontSize: '13px' }}
        >
          {aiLoading ? 'Running…' : 'Generate experiment brief'}
        </button>
      </div>

      {recommendations.length > 0 && (
        <div style={{ marginBottom: '16px', background: 'white', borderRadius: '8px', padding: '14px', border: '1px solid #e2e8f0' }}>
          <div style={{ fontWeight: '600', marginBottom: '10px', color: '#1e293b' }}>Suggested next runs</div>
          {recommendations.map((rec, i) => (
            <div key={i} style={{ marginBottom: '10px', padding: '10px', background: '#f8fafc', borderRadius: '6px', fontSize: '13px' }}>
              <div style={{ fontWeight: '600', color: '#4338ca' }}>{rec.suggestedFormula}</div>
              <div style={{ color: '#64748b', marginTop: '4px' }}>Confidence: {(rec.confidence * 100).toFixed(0)}% · {rec.modelVersion}</div>
              <div style={{ marginTop: '6px', color: '#475569' }}>{rec.rationale}</div>
            </div>
          ))}
        </div>
      )}

      {experimentBrief && (
        <div style={{ marginBottom: '16px', background: 'white', borderRadius: '8px', padding: '14px', border: '1px solid #e2e8f0' }}>
          <div style={{ fontWeight: '600', marginBottom: '8px', color: '#1e293b' }}>Experiment brief</div>
          <pre style={{ whiteSpace: 'pre-wrap', fontSize: '13px', color: '#334155', margin: 0, fontFamily: 'inherit' }}>
            {experimentBrief}
          </pre>
        </div>
      )}
    </div>
  );
}

function AnalysisCard({ analysis }) {
  if (!analysis) return null;
  const phase = analysis.phase;
  const lat = analysis.lattice;
  const cs = analysis.crystallite;
  const mag = analysis.magnetics;

  const stat = (label, value, unit = '') => (
    <div style={{ background: '#f8fafc', borderRadius: '8px', padding: '10px 12px', minWidth: '120px' }}>
      <div style={{ fontSize: '11px', color: '#64748b' }}>{label}</div>
      <div style={{ fontSize: '15px', fontWeight: 700, color: '#0f172a' }}>
        {value ?? '—'}{value != null && unit ? ` ${unit}` : ''}
      </div>
    </div>
  );

  return (
    <div style={{ marginTop: '10px', display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
      {phase && stat('τ-MnAl phase', phase.tauDetected ? 'Detected' : 'Not detected')}
      {lat?.ok && stat('Lattice a (cubic est.)', lat.lattice_a_cubic, 'Å')}
      {cs?.ok && stat('Crystallite size', cs.crystallite_size_nm, 'nm')}
      {mag?.ok && stat('Ms', mag.Ms_emu_g, 'emu/g')}
      {mag?.ok && stat('Hc', mag.Hc_Oe, 'Oe')}
      {mag?.ok && stat('Squareness', mag.squareness_Mr_Ms)}
      {mag?.ok && stat('(BH)max est.', mag.bhmax_estimate_MGOe, 'MGOe')}
    </div>
  );
}

function LabChatTab({ samples, selectedSampleId, setSelectedSampleId, cardStyle, inputStyle, onLoadDemo }) {
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      text:
        'Pick a sample and ask about phase, lattice, coercivity, or what to try next. You can upload XRD/VSM files here too.',
    },
  ]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState(null);

  useEffect(() => {
    api.agent.status().then(setStatus).catch(() => {});
  }, []);

  const send = async (textArg) => {
    const msg = (textArg ?? input).trim();
    if (!msg || busy) return;
    const base = [...messages, { role: 'user', text: msg }];
    setMessages(base);
    setInput('');
    setBusy(true);
    try {
      const history = messages
        .map((m) => ({ role: m.role === 'assistant' ? 'assistant' : 'user', content: m.text }))
        .filter((m) => m.content);
      const res = await api.agent.chat(msg, selectedSampleId, history);
      setMessages([...base, { role: 'assistant', text: res.answer, payload: res }]);
    } catch (e) {
      setMessages([...base, { role: 'assistant', text: 'Error: ' + (e.message || 'request failed') }]);
    } finally {
      setBusy(false);
    }
  };

  const handleFile = async (e, kind) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = null;
    if (!selectedSampleId) {
      setMessages((m) => [...m, { role: 'assistant', text: 'Please select a sample first, then upload.' }]);
      return;
    }
    setBusy(true);
    setMessages((m) => [...m, { role: 'user', text: `Uploaded ${kind.toUpperCase()} file: ${file.name}` }]);
    try {
      if (kind === 'xrd') await api.xrd.upload(file, selectedSampleId);
      else await api.magnetic.upload(file, 'M-H', selectedSampleId);
      await send(`Analyze the ${kind === 'xrd' ? 'XRD pattern' : 'M-H loop'} I just uploaded and tell me what I got.`);
    } catch (err) {
      setMessages((m) => [...m, { role: 'assistant', text: 'Upload failed: ' + (err.message || 'error') }]);
    } finally {
      setBusy(false);
    }
  };

  const quick = (label, prompt) => (
    <button
      disabled={busy}
      onClick={() => send(prompt)}
      style={{ padding: '8px 12px', background: '#eef2ff', color: '#4338ca', border: '1px solid #c7d2fe', borderRadius: '8px', cursor: busy ? 'wait' : 'pointer', fontSize: '13px' }}
    >
      {label}
    </button>
  );

  return (
    <div style={cardStyle}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '10px', marginBottom: '12px' }}>
        <h2 style={{ fontSize: '20px', fontWeight: 600, color: '#1a202c', margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
          <MessageSquare size={22} /> Lab chat
        </h2>
        {status && (
          <span style={{ fontSize: '12px', padding: '4px 10px', borderRadius: '999px', background: status.llmAvailable ? '#ecfdf5' : '#fffbeb', color: status.llmAvailable ? '#065f46' : '#92400e', border: `1px solid ${status.llmAvailable ? '#6ee7b7' : '#fcd34d'}` }}>
            {status.llmAvailable ? 'Online' : 'Offline — set GEMINI_API_KEY (local: backend/.env, Render: service env)'}
          </span>
        )}
      </div>

      {samples.length === 0 && (
        <div style={{ padding: '16px', textAlign: 'center', background: '#f8fafc', borderRadius: '12px', border: '1px dashed #cbd5e1', marginBottom: '12px' }}>
          <p style={{ color: '#64748b', margin: '0 0 10px' }}>No samples to analyze yet. Load the demo lab to get 3 MnAl samples with XRD + magnetic data.</p>
          <button
            type="button"
            disabled={busy || !onLoadDemo}
            onClick={onLoadDemo}
            style={{ padding: '10px 18px', background: '#0f766e', color: 'white', border: 'none', borderRadius: '8px', cursor: busy ? 'wait' : 'pointer', fontWeight: 600 }}
          >
            Load demo lab (3 MnAl samples)
          </button>
        </div>
      )}

      <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', alignItems: 'flex-end', marginBottom: '12px' }}>
        <SamplePicker samples={samples} value={selectedSampleId} onChange={setSelectedSampleId} disabled={busy} />
        <label style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', padding: '10px 14px', border: '1px solid #e2e8f0', borderRadius: '8px', cursor: busy ? 'wait' : 'pointer', background: 'white' }}>
          <Upload size={15} /> XRD
          <input type="file" accept=".txt,.csv,.ras,.dat,.DAT" onChange={(e) => handleFile(e, 'xrd')} disabled={busy} style={{ display: 'none' }} />
        </label>
        <label style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', padding: '10px 14px', border: '1px solid #e2e8f0', borderRadius: '8px', cursor: busy ? 'wait' : 'pointer', background: 'white' }}>
          <Upload size={15} /> VSM
          <input type="file" accept=".txt,.csv,.dat,.DAT" onChange={(e) => handleFile(e, 'mag')} disabled={busy} style={{ display: 'none' }} />
        </label>
      </div>

      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '14px' }}>
        {quick('Analyze sample', 'Analyze this sample: phase, lattice parameter, crystallite size, and magnetic properties.')}
        {quick('What next?', 'What experiment should I run next to improve coercivity?')}
        {quick('Write brief', 'Write an experiment brief for this sample.')}
      </div>

      <div style={{ border: '1px solid #e2e8f0', borderRadius: '12px', padding: '16px', background: '#fbfcfe', maxHeight: '560px', overflowY: 'auto' }}>
        {messages.map((m, i) => (
          <div key={i} style={{ marginBottom: '16px', display: 'flex', flexDirection: 'column', alignItems: m.role === 'user' ? 'flex-end' : 'flex-start' }}>
            <div style={{ fontSize: '11px', color: '#94a3b8', marginBottom: '4px' }}>{m.role === 'user' ? 'You' : 'Reply'}</div>
            <div style={{ maxWidth: '85%', background: m.role === 'user' ? '#667eea' : 'white', color: m.role === 'user' ? 'white' : '#1f2937', border: m.role === 'user' ? 'none' : '1px solid #e2e8f0', borderRadius: '12px', padding: '12px 14px' }}>
              <pre style={{ whiteSpace: 'pre-wrap', margin: 0, fontFamily: 'inherit', fontSize: '14px', lineHeight: 1.5 }}>{m.text}</pre>
              {m.payload?.displayVisuals && m.payload?.analysis && <AnalysisCard analysis={m.payload.analysis} />}
              {m.payload?.displayVisuals && m.payload?.xrdRecord?.data?.length > 0 && (
                <div style={{ marginTop: '12px', border: '1px solid #e2e8f0', borderRadius: '8px' }}>
                  <XRDPlot record={m.payload.xrdRecord} title="XRD pattern" />
                </div>
              )}
              {m.payload?.displayVisuals && m.payload?.magneticRecord?.data?.length > 0 && (
                <div style={{ marginTop: '12px', border: '1px solid #e2e8f0', borderRadius: '8px' }}>
                  <MagneticPlot record={m.payload.magneticRecord} title="M-H loop" />
                </div>
              )}
              {m.payload?.recommendations?.length > 0 && (
                <div style={{ marginTop: '12px' }}>
                  {m.payload.recommendations.map((r, j) => (
                    <div key={j} style={{ background: '#f8fafc', borderRadius: '8px', padding: '10px', marginBottom: '6px', fontSize: '13px' }}>
                      <strong style={{ color: '#4338ca' }}>{r.suggestedFormula}</strong> · {(r.confidence * 100).toFixed(0)}%
                      <div style={{ color: '#475569', marginTop: '2px' }}>{r.rationale}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
        {busy && <div style={{ color: '#94a3b8', fontSize: '13px' }}>Working on it…</div>}
      </div>

      <div style={{ display: 'flex', gap: '10px', marginTop: '12px' }}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') send(); }}
          placeholder="Ask anything — e.g. 'What phase did I get and how do I raise Hc?'"
          disabled={busy}
          style={{ ...inputStyle, flex: 1 }}
        />
        <button
          onClick={() => send()}
          disabled={busy || !input.trim()}
          style={{ padding: '12px 18px', background: '#667eea', color: 'white', border: 'none', borderRadius: '8px', cursor: busy ? 'wait' : 'pointer', display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 600 }}
        >
          <Send size={16} /> Send
        </button>
      </div>
    </div>
  );
}

function App() {
  const [user, setUser] = useState(null);
  const [activeTab, setActiveTab] = useState('calc');
  const [formula, setFormula] = useState('Fe2MoGe');
  const [targetEl, setTargetEl] = useState('Ge');
  const [targetMass, setTargetMass] = useState('1');
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [history, setHistory] = useState([]);
  const [sampleName, setSampleName] = useState('');
  const [xrdData, setXrdData] = useState(null);
  const [magData, setMagData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [selectedSampleId, setSelectedSampleId] = useState('');
  const [measurementType, setMeasurementType] = useState('M-H');
  const [detailSample, setDetailSample] = useState(null);
  const [uploadMessage, setUploadMessage] = useState('');
  const [aiLoading, setAiLoading] = useState(false);
  const [aiStatus, setAiStatus] = useState(null);
  const [copilotQuestion, setCopilotQuestion] = useState('');
  const [copilotAnswer, setCopilotAnswer] = useState('');
  const [copilotSource, setCopilotSource] = useState('');
  const [synthesisNotes, setSynthesisNotes] = useState('');
  const [parsedSynthesis, setParsedSynthesis] = useState(null);
  const [applySampleId, setApplySampleId] = useState('');
  const [detailBrief, setDetailBrief] = useState('');
  const [lastRecommendations, setLastRecommendations] = useState(null);
  const [demoBanner, setDemoBanner] = useState('');
  const [xrdRecord, setXrdRecord] = useState(null);
  const [magRecords, setMagRecords] = useState([]);

  const applySampleCharacterization = (full) => {
    if (!full) {
      setXrdRecord(null);
      setXrdData(null);
      setMagRecords([]);
      setMagData(null);
      return;
    }

    const xr = (full.xrdRecords || []).find((r) => r.data?.length) || null;
    if (xr) {
      setXrdRecord(xr);
      setXrdData({
        filename: xr.filename,
        points: xr.data.length,
        peaks: xr.peaks,
        peakCount: xr.peaks?.length ?? 0,
        phaseAnalysis: full.phaseAnalysis,
        recordId: xr.id,
        processedDate: xr.createdAt ? new Date(xr.createdAt).toLocaleString() : new Date().toLocaleString(),
        saved: true,
      });
    } else {
      setXrdRecord(null);
      setXrdData(null);
    }

    const mags = (full.magneticRecords || [])
      .filter((r) => r.data?.length)
      .sort((a, b) => {
        const rank = (t) => (t === 'M-H' ? 0 : t === 'M-T' ? 1 : 2);
        return rank(a.measurementType) - rank(b.measurementType);
      });
    setMagRecords(mags);
    if (mags.length > 0) {
      const latest = mags[0];
      const props = latest.properties || {};
      setMagData({
        filename: latest.filename,
        points: latest.data.length,
        Ms: props.Ms != null ? Number(props.Ms).toFixed(3) : '—',
        Mr: props.Mr != null ? Number(props.Mr).toFixed(3) : '—',
        Hc: props.Hc != null ? Number(props.Hc).toFixed(3) : '—',
        measurementType: latest.measurementType || 'M-H',
        recordId: latest.id,
        processedDate: latest.createdAt ? new Date(latest.createdAt).toLocaleString() : new Date().toLocaleString(),
        saved: true,
      });
    } else {
      setMagData(null);
    }
  };

  useEffect(() => {
    const currentUser = api.auth.getCurrentUser();
    if (currentUser) {
      setUser(currentUser);
      loadHistory();
    }
  }, []);

  useEffect(() => {
    const onUnauthorized = () => {
      setUser(null);
      setHistory([]);
      setDetailSample(null);
      setError('Your session expired. Please log in again, or use “Try live demo”.');
    };
    window.addEventListener('elementx:unauthorized', onUnauthorized);
    return () => window.removeEventListener('elementx:unauthorized', onUnauthorized);
  }, []);

  useEffect(() => {
    if (user && (activeTab === 'xrd' || activeTab === 'mag' || activeTab === 'history' || activeTab === 'ai' || activeTab === 'copilot')) {
      loadHistory();
    }
    if (user && activeTab === 'ai') {
      loadAiStatus();
    }
  }, [activeTab, user]);

  useEffect(() => {
    if (!user || !selectedSampleId) {
      if (!selectedSampleId) {
        setXrdRecord(null);
        setXrdData(null);
        setMagRecords([]);
        setMagData(null);
      }
      return;
    }
    if (activeTab !== 'xrd' && activeTab !== 'mag') return;

    let cancelled = false;
    (async () => {
      try {
        const full = await api.samples.getById(selectedSampleId);
        if (!cancelled) applySampleCharacterization(full);
      } catch (err) {
        console.error('Failed to load sample charts:', err);
      }
    })();
    return () => { cancelled = true; };
  }, [selectedSampleId, activeTab, user]);

  const loadAiStatus = async () => {
    try {
      const status = await api.ai.status();
      setAiStatus(status);
    } catch (err) {
      console.error('AI status:', err);
    }
  };

  const loadHistory = async () => {
    setLoading(true);
    try {
      const data = await api.samples.getAll();
      setHistory(data);
      if (detailSample?.id) {
        const fresh = await api.samples.getById(detailSample.id);
        setDetailSample(fresh);
      }
    } catch (err) {
      console.error('Failed to load history:', err);
    } finally {
      setLoading(false);
    }
  };

  const openSampleDetail = async (id) => {
    setLoading(true);
    setError('');
    setDetailBrief('');
    try {
      const sample = await api.samples.getById(id);
      setDetailSample(sample);
      setSelectedSampleId(id);
    } catch (err) {
      setError('Failed to load sample: ' + (err.message || 'Unknown error'));
    } finally {
      setLoading(false);
    }
  };

  const handleSetOutcome = async (sampleId, outcomeLabel) => {
    setAiLoading(true);
    setError('');
    try {
      await api.samples.update(sampleId, { outcome_label: outcomeLabel });
      await openSampleDetail(sampleId);
      await loadHistory();
    } catch (err) {
      setError(err.message || 'Failed to set outcome');
    } finally {
      setAiLoading(false);
    }
  };

  const handleRecommend = async (sampleId) => {
    setAiLoading(true);
    setError('');
    try {
      const result = await api.samples.recommend(sampleId);
      setLastRecommendations(result);
      setUploadMessage(result.summary || 'Recommendations generated.');
      await openSampleDetail(sampleId);
      await loadHistory();
    } catch (err) {
      setError(err.message || 'Recommendation failed');
    } finally {
      setAiLoading(false);
    }
  };

  const handleExperimentBrief = async (sampleId) => {
    setAiLoading(true);
    setError('');
    try {
      const result = await api.samples.experimentBrief(sampleId);
      setDetailBrief(result.markdown || '');
    } catch (err) {
      setError(err.message || 'Brief generation failed');
    } finally {
      setAiLoading(false);
    }
  };

  const handleCopilot = async () => {
    if (!copilotQuestion.trim()) return;
    setAiLoading(true);
    setError('');
    try {
      const result = await api.ai.copilot(
        copilotQuestion.trim(),
        selectedSampleId || null,
        null
      );
      setCopilotAnswer(result.answer || '');
      setCopilotSource(result.source || '');
    } catch (err) {
      setError(err.message || 'Request failed');
    } finally {
      setAiLoading(false);
    }
  };

  const handleParseSynthesis = async () => {
    if (!synthesisNotes.trim()) return;
    setAiLoading(true);
    setError('');
    try {
      const result = await api.ai.parseSynthesis(synthesisNotes.trim());
      setParsedSynthesis(result);
    } catch (err) {
      setError(err.message || 'Parse failed');
    } finally {
      setAiLoading(false);
    }
  };

  const handleApplySynthesis = async () => {
    if (!applySampleId || !parsedSynthesis?.synthesis) return;
    setAiLoading(true);
    setError('');
    try {
      const updates = { synthesis: parsedSynthesis.synthesis };
      if (parsedSynthesis.dopants?.length) {
        updates.dopants = parsedSynthesis.dopants;
      }
      await api.samples.update(applySampleId, updates);
      setUploadMessage('Synthesis fields applied to sample.');
      if (detailSample?.id === applySampleId) {
        await openSampleDetail(applySampleId);
      }
      await loadHistory();
    } catch (err) {
      setError(err.message || 'Apply failed');
    } finally {
      setAiLoading(false);
    }
  };

  const handleLogin = (userData, options = {}) => {
    setUser(userData);
    loadHistory();
    if (options.tab) setActiveTab(options.tab);
    if (options.message) setDemoBanner(options.message);
  };

  const handleDemoLogin = async () => {
    const boot = await api.demo.bootstrap();
    const loginResult = await api.auth.login({
      email: boot.email,
      password: boot.password,
    });
    handleLogin(loginResult.user, {
      tab: 'copilot',
      message: boot.message || 'Demo lab loaded — pick a sample in Lab chat.',
    });
    if (boot.recommendations?.length) {
      setLastRecommendations({
        recommendations: boot.recommendations,
        summary: boot.pitchHint || boot.message,
      });
    }
  };

  const handleLogout = () => {
    api.auth.logout();
    setUser(null);
    setHistory([]);
    setResult(null);
  };

  const calculate = () => {
    setError('');
    setResult(null);

    const mass = parseFloat(targetMass);
    if (isNaN(mass) || mass <= 0) {
      setError('Please enter a valid target mass.');
      return;
    }

    let composition;
    try {
      composition = parseFormula(formula.trim());
    } catch (e) {
      setError(e.message);
      return;
    }

    const targetSymbol = normalizeElementSymbol(targetEl);
    if (!ELEMENTS[targetSymbol]) {
      setError(`Target element "${targetEl}" is not recognized. Use a symbol like "In" (Indium).`);
      return;
    }

    if (!composition[targetSymbol]) {
      setError(`Target element ${targetSymbol} not found in formula ${formula}.`);
      return;
    }

    const elementAtomicMass = ELEMENTS[targetSymbol];
    const elementStoich = composition[targetSymbol];
    const scaleFactor = mass / (elementAtomicMass * elementStoich);

    const elements = Object.entries(composition).map(([el, count]) => {
      const atomicMass = ELEMENTS[el];
      const requiredMass = scaleFactor * count * atomicMass;
      return {
        element: el,
        stoich: count,
        mass: requiredMass,
        atomic: atomicMass
      };
    });

    const total = elements.reduce((sum, e) => sum + e.mass, 0);

    setResult({
      name: sampleName || formula,
      formula,
      targetEl: targetSymbol,
      targetMass: mass,
      elements,
      total,
      date: new Date().toISOString()
    });
  };

  const saveSample = async () => {
    if (!result) return;
    setLoading(true);
    setError('');
    try {
      const created = await api.samples.create({
        name: sampleName || result.formula,
        formula: result.formula,
        stoichiometry: result,
      });
      await loadHistory();
      setSelectedSampleId(created.id);
      setSampleName('');
      alert(`Sample "${created.name}" saved. You can now upload XRD and magnetic data for it.`);
    } catch (err) {
      alert('Failed to save sample: ' + (err.message || 'Unknown error'));
    } finally {
      setLoading(false);
    }
  };

  const loadSample = (sample) => {
    const stoich = sample.stoichiometry;
    if (stoich && Array.isArray(stoich.elements) && typeof stoich.total === 'number') {
      setFormula(stoich.formula || sample.formula || '');
      setTargetEl(stoich.targetEl || '');
      setTargetMass(String(stoich.targetMass || ''));
      setResult(stoich);
      setError('');
    } else {
      setFormula(sample.formula || '');
      setTargetEl('');
      setTargetMass('1');
      setResult(null);
      setError('This sample has no saved stoichiometry calculation. Enter a target element and mass, then Calculate.');
    }
    setActiveTab('calc');
  };

  const deleteSample = async (id) => {
    if (!window.confirm('Are you sure you want to delete this sample?')) return;
    setLoading(true);
    try {
      await api.samples.delete(id);
      if (detailSample?.id === id) setDetailSample(null);
      if (selectedSampleId === id) setSelectedSampleId('');
      await loadHistory();
    } catch (err) {
      alert('Failed to delete sample: ' + (err.message || 'Unknown error'));
    } finally {
      setLoading(false);
    }
  };

  const exportToExcel = () => {
    if (!result) return;
    let csv = 'Element,Stoichiometry,Atomic Mass,Required Mass (g),Weight %\n';
    result.elements.forEach(e => {
      const wt = (e.mass / result.total * 100).toFixed(2);
      csv += `${e.element},${e.stoich},${e.atomic.toFixed(3)},${e.mass.toFixed(6)},${wt}\n`;
    });
    csv += `\nTotal Mass,,,${result.total.toFixed(6)},100.00\n`;
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${(result.name || result.formula).replace(/\s/g, '_')}_calculation.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const copyResults = () => {
    if (!result) return;
    let text = `${result.formula} Stoichiometric Calculation\nTarget: ${result.targetMass} g ${result.targetEl}\n\n`;
    result.elements.forEach(e => {
      text += `${e.element}: ${e.mass.toFixed(6)} g (${(e.mass/result.total*100).toFixed(2)}%)\n`;
    });
    text += `\nTotal: ${result.total.toFixed(6)} g`;
    navigator.clipboard.writeText(text);
    alert('Results copied to clipboard!');
  };

  const handleXRDUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    if (!selectedSampleId) {
      setError('Select a sample before uploading XRD data.');
      e.target.value = null;
      return;
    }

    setLoading(true);
    setError('');
    setUploadMessage('');
    try {
      const response = await api.xrd.upload(file, selectedSampleId);
      setXrdData({
        filename: file.name,
        points: response.points,
        peaks: response.peaks,
        peakCount: response.peakCount,
        phaseAnalysis: response.phaseAnalysis,
        recordId: response.id,
        processedDate: new Date().toLocaleString(),
        saved: true,
      });
      if (response.data?.length) {
        setXrdRecord({
          id: response.id,
          filename: response.filename || file.name,
          data: response.data,
          peaks: response.peaks,
        });
      }
      setUploadMessage(`Saved and linked to sample. Pattern plotted below.`);
      try {
        const full = await api.samples.getById(selectedSampleId);
        applySampleCharacterization(full);
      } catch (_) {
        // plotting is best-effort; ignore fetch errors
      }
      await loadHistory();
      if (detailSample?.id === selectedSampleId) {
        await openSampleDetail(selectedSampleId);
      }
    } catch (err) {
      setError(`XRD upload failed: ${err.message}`);
      setXrdData(null);
    } finally {
      setLoading(false);
      e.target.value = null;
    }
  };

  const handleMagUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    if (!selectedSampleId) {
      setError('Select a sample before uploading magnetic data.');
      e.target.value = null;
      return;
    }

    setLoading(true);
    setError('');
    setUploadMessage('');
    try {
      const response = await api.magnetic.upload(file, measurementType, selectedSampleId);
      const props = response.properties || {};
      setMagData({
        filename: file.name,
        points: response.points,
        Ms: props.Ms?.toFixed(3) ?? '—',
        Mr: props.Mr?.toFixed(3) ?? '—',
        Hc: props.Hc?.toFixed(3) ?? '—',
        measurementType: response.measurementType || measurementType,
        recordId: response.id,
        processedDate: new Date().toLocaleString(),
        saved: true,
      });
      if (response.data?.length) {
        const uploaded = {
          id: response.id,
          filename: response.filename || file.name,
          measurementType: response.measurementType || measurementType,
          data: response.data,
          properties: props,
        };
        setMagRecords((prev) => {
          const rest = prev.filter((r) => r.id !== uploaded.id);
          return [uploaded, ...rest];
        });
      }
      setUploadMessage(`Saved and linked to sample. Curve plotted below.`);
      try {
        const full = await api.samples.getById(selectedSampleId);
        applySampleCharacterization(full);
      } catch (_) {
        // plotting is best-effort; ignore fetch errors
      }
      await loadHistory();
      if (detailSample?.id === selectedSampleId) {
        await openSampleDetail(selectedSampleId);
      }
    } catch (err) {
      setError(`Magnetic upload failed: ${err.message}`);
      setMagData(null);
    } finally {
      setLoading(false);
      e.target.value = null;
    }
  };

  if (!user) {
    return <LoginForm onLogin={handleLogin} onDemo={handleDemoLogin} />;
  }

  const cardStyle = {
    background: 'white',
    borderRadius: '12px',
    boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
    padding: '30px',
    marginBottom: '25px'
  };

  const inputStyle = {
    width: '100%',
    padding: '12px 16px',
    border: '2px solid #e2e8f0',
    borderRadius: '8px',
    fontSize: '15px',
    outline: 'none'
  };

  const buttonStyle = {
    padding: '14px',
    background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    color: 'white',
    border: 'none',
    borderRadius: '8px',
    fontSize: '16px',
    fontWeight: '600',
    cursor: 'pointer'
  };

  return (
    <div style={{ minHeight: '100vh', background: 'linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%)' }}>
      <header style={{
        background: 'white',
        borderBottom: '1px solid #e2e8f0',
        boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
        padding: '20px 40px'
      }}>
        <div style={{ maxWidth: '1400px', margin: '0 auto', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '15px' }}>
            <div style={{
              width: '45px',
              height: '45px',
              background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
              borderRadius: '10px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center'
            }}>
              <Calculator size={24} color="white" />
            </div>
            <div>
              <h1 style={{ fontSize: '28px', fontWeight: '700', color: '#1a202c', margin: 0 }}>ElementX</h1>
              <p style={{ fontSize: '12px', color: '#718096', margin: 0 }}>MnAl · XRD · VSM · lab notebook</p>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '20px' }}>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: '14px', fontWeight: '600', color: '#1a202c' }}>{user.name}</div>
              <div style={{ fontSize: '12px', color: '#718096' }}>{user.email}</div>
            </div>
            <button
              onClick={handleLogout}
              style={{
                padding: '8px 16px',
                background: '#ef4444',
                color: 'white',
                border: 'none',
                borderRadius: '6px',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                fontSize: '14px'
              }}
            >
              <LogOut size={16} />
              Logout
            </button>
          </div>
        </div>
      </header>

      <div style={{ maxWidth: '1400px', margin: '0 auto', padding: '30px 40px' }}>
        <div style={{
          background: 'white',
          borderRadius: '12px',
          boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
          padding: '8px',
          marginBottom: '30px',
          display: 'flex',
          gap: '8px'
        }}>
          {[
            { id: 'copilot', label: 'Lab chat', icon: MessageSquare },
            { id: 'calc', label: 'Stoichiometry Calculator', icon: Calculator },
            { id: 'history', label: 'Sample Database', icon: Database },
            { id: 'xrd', label: 'XRD Analysis', icon: LineChart },
            { id: 'mag', label: 'Magnetic Properties', icon: Magnet },
            { id: 'ai', label: 'Notes & parsing', icon: FileText }
          ].map(tab => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => { setActiveTab(tab.id); setError(''); setUploadMessage(''); }}
                disabled={loading}
                style={{
                  flex: 1,
                  padding: '14px 20px',
                  border: 'none',
                  background: activeTab === tab.id ? 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)' : 'transparent',
                  color: activeTab === tab.id ? 'white' : '#64748b',
                  borderRadius: '8px',
                  cursor: loading ? 'wait' : 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '10px',
                  fontSize: '14px',
                  fontWeight: '500',
                  transition: 'all 0.2s',
                  boxShadow: activeTab === tab.id ? '0 4px 12px rgba(102, 126, 234, 0.4)' : 'none'
                }}
              >
                <Icon size={18} />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </div>

        {demoBanner && (
          <div style={{
            marginBottom: '20px',
            padding: '14px 18px',
            borderRadius: '10px',
            background: 'linear-gradient(135deg, #ecfdf5 0%, #dbeafe 100%)',
            border: '1px solid #6ee7b7',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: '12px',
            flexWrap: 'wrap',
          }}>
            <span style={{ fontSize: '14px', color: '#065f46', fontWeight: '500' }}>{demoBanner}</span>
            <button
              type="button"
              onClick={() => setDemoBanner('')}
              style={{ padding: '6px 12px', background: 'white', border: '1px solid #6ee7b7', borderRadius: '6px', cursor: 'pointer', fontSize: '12px' }}
            >
              Dismiss
            </button>
          </div>
        )}

        {activeTab === 'copilot' && (
          <LabChatTab
            samples={history}
            selectedSampleId={selectedSampleId}
            setSelectedSampleId={setSelectedSampleId}
            cardStyle={cardStyle}
            inputStyle={inputStyle}
            onLoadDemo={async () => {
              setLoading(true);
              try {
                const boot = await api.demo.load(false);
                setDemoBanner(boot.message);
                await loadHistory();
              } catch (err) {
                setError(err.message);
              } finally {
                setLoading(false);
              }
            }}
          />
        )}

        {activeTab === 'calc' && (
          <div>
            <div style={cardStyle}>
              <h2 style={{ fontSize: '20px', fontWeight: '600', color: '#1a202c', marginBottom: '20px' }}>
                Input Parameters
              </h2>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '20px', marginBottom: '20px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '13px', fontWeight: '600', color: '#4a5568', marginBottom: '8px' }}>
                    Chemical Formula
                  </label>
                  <input
                    type="text"
                    value={formula}
                    onChange={e => setFormula(e.target.value)}
                    placeholder="e.g., Fe2MoGe"
                    style={inputStyle}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '13px', fontWeight: '600', color: '#4a5568', marginBottom: '8px' }}>
                    Target Element
                  </label>
                  <input
                    type="text"
                    value={targetEl}
                    onChange={e => setTargetEl(e.target.value)}
                    placeholder="e.g., Ge"
                    style={inputStyle}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '13px', fontWeight: '600', color: '#4a5568', marginBottom: '8px' }}>
                    Target Mass (g)
                  </label>
                  <input
                    type="number"
                    step="0.000001"
                    value={targetMass}
                    onChange={e => setTargetMass(e.target.value)}
                    placeholder="1.000000"
                    style={inputStyle}
                  />
                </div>
              </div>
              <button onClick={calculate} style={{ ...buttonStyle, width: '100%', boxShadow: '0 4px 12px rgba(102, 126, 234, 0.3)' }}>
                Calculate Stoichiometry
              </button>
            </div>

            {error && (
              <div style={{
                background: '#fee2e2',
                border: '1px solid #fca5a5',
                color: '#dc2626',
                padding: '12px 16px',
                borderRadius: '8px',
                marginBottom: '20px'
              }}>
                {error}
              </div>
            )}

            {result && Array.isArray(result.elements) && typeof result.total === 'number' && (
              <div style={cardStyle}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '20px' }}>
                  <div>
                    <h3 style={{ fontSize: '24px', fontWeight: '700', color: '#1a202c', margin: '0 0 5px 0' }}>
                      {result.formula}
                    </h3>
                    <input
                      type="text"
                      value={sampleName || result.formula}
                      onChange={e => setSampleName(e.target.value)}
                      placeholder="Enter Sample Name"
                      style={{ border: '1px solid #ccc', padding: '5px 10px', borderRadius: '4px', fontSize: '14px', width: '200px' }}
                    />
                    <p style={{ fontSize: '13px', color: '#718096', margin: '5px 0 0' }}>
                      Calculated: {new Date(result.date).toLocaleString()}
                    </p>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: '32px', fontWeight: '700', color: '#667eea' }}>
                      {result.total.toFixed(6)} g
                    </div>
                    <div style={{ fontSize: '12px', color: '#718096' }}>Total Mass Required</div>
                    <div style={{ display: 'flex', gap: '10px', marginTop: '10px' }}>
                      <button
                        onClick={saveSample}
                        disabled={loading}
                        style={{ padding: '8px 12px', background: '#3b82f6', color: 'white', border: 'none', borderRadius: '6px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}
                      >
                        {loading ? 'Saving...' : <><Save size={16} /> Save</>}
                      </button>
                      <button
                        onClick={copyResults}
                        style={{ padding: '8px 12px', background: '#4b5563', color: 'white', border: 'none', borderRadius: '6px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}
                      >
                        <Copy size={16} />
                        Copy
                      </button>
                      <button
                        onClick={exportToExcel}
                        style={{ padding: '8px 12px', background: '#10b981', color: 'white', border: 'none', borderRadius: '6px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}
                      >
                        <Download size={16} />
                        Export CSV
                      </button>
                    </div>
                  </div>
                </div>

                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                      <tr style={{ background: '#f8fafc' }}>
                        <th style={{ textAlign: 'left', padding: '10px', borderBottom: '1px solid #e2e8f0' }}>Element</th>
                        <th style={{ textAlign: 'right', padding: '10px', borderBottom: '1px solid #e2e8f0' }}>Stoichiometry</th>
                        <th style={{ textAlign: 'right', padding: '10px', borderBottom: '1px solid #e2e8f0' }}>Atomic Mass</th>
                        <th style={{ textAlign: 'right', padding: '10px', borderBottom: '1px solid #e2e8f0' }}>Required Mass (g)</th>
                        <th style={{ textAlign: 'right', padding: '10px', borderBottom: '1px solid #e2e8f0' }}>Weight %</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.elements.map((e) => (
                        <tr key={e.element}>
                          <td style={{ padding: '10px', borderBottom: '1px solid #eef2f7' }}>{e.element}</td>
                          <td style={{ padding: '10px', textAlign: 'right', borderBottom: '1px solid #eef2f7' }}>{e.stoich}</td>
                          <td style={{ padding: '10px', textAlign: 'right', borderBottom: '1px solid #eef2f7' }}>{e.atomic.toFixed(3)}</td>
                          <td style={{ padding: '10px', textAlign: 'right', borderBottom: '1px solid #eef2f7' }}>{e.mass.toFixed(6)}</td>
                          <td style={{ padding: '10px', textAlign: 'right', borderBottom: '1px solid #eef2f7' }}>{((e.mass / result.total) * 100).toFixed(2)}%</td>
                        </tr>
                      ))}
                      <tr>
                        <td style={{ padding: '10px', fontWeight: '700' }}>Total</td>
                        <td style={{ padding: '10px' }} />
                        <td style={{ padding: '10px' }} />
                        <td style={{ padding: '10px', textAlign: 'right', fontWeight: '700' }}>{result.total.toFixed(6)}</td>
                        <td style={{ padding: '10px', textAlign: 'right', fontWeight: '700' }}>100.00%</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}

        {activeTab === 'history' && (
          <div style={cardStyle}>
            <h2 style={{ fontSize: '20px', fontWeight: '600', color: '#1a202c', marginBottom: '10px' }}>
              Saved Samples
            </h2>
            <p style={{ color: '#64748b', marginTop: 0 }}>
              Samples are stored in MongoDB and linked to XRD and magnetometry uploads.
            </p>

            {error && activeTab === 'history' && (
              <div style={{ background: '#fee2e2', border: '1px solid #fca5a5', color: '#dc2626', padding: '12px 16px', borderRadius: '8px', marginBottom: '16px' }}>
                {error}
              </div>
            )}

            {loading ? (
              <div style={{ padding: '10px 0' }}>Loading…</div>
            ) : history.length === 0 ? (
              <div style={{ padding: '24px', textAlign: 'center', background: '#f8fafc', borderRadius: '12px', border: '1px dashed #cbd5e1' }}>
                <p style={{ color: '#64748b', marginTop: 0 }}>No samples yet.</p>
                <button
                  type="button"
                  disabled={loading}
                  onClick={async () => {
                    setLoading(true);
                    try {
                      const boot = await api.demo.load(false);
                      setDemoBanner(boot.message);
                      await loadHistory();
                      setActiveTab('ai');
                    } catch (err) {
                      setError(err.message);
                    } finally {
                      setLoading(false);
                    }
                  }}
                  style={{ padding: '12px 20px', background: '#0f766e', color: 'white', border: 'none', borderRadius: '8px', cursor: 'pointer', fontWeight: '600' }}
                >
                  Load demo lab (3 MnAl samples)
                </button>
              </div>
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '12px' }}>
                {history.map((s) => (
                  <div key={s.id} style={{ border: '1px solid #e2e8f0', borderRadius: '10px', padding: '14px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '10px' }}>
                      <div>
                        <div style={{ fontWeight: '700', color: '#0f172a' }}>{s.name || s.formula}</div>
                        <div style={{ fontSize: '13px', color: '#64748b' }}>{s.formula}</div>
                        <div style={{ fontSize: '12px', color: '#64748b', marginTop: '4px' }}>
                          {s.materialFamily || 'mnal_tau'} · {s.status || 'planned'}
                        </div>
                        <div style={{ fontSize: '12px', color: '#94a3b8', marginTop: '4px' }}>
                          {s.createdAt ? new Date(s.createdAt).toLocaleString() : ''}
                        </div>
                      </div>
                      <div style={{ fontSize: '12px', color: '#64748b', textAlign: 'right' }}>
                        {s.characterization?.xrd ? 'XRD ✓' : ''}
                        {s.characterization?.magnetic ? ' Mag ✓' : ''}
                        {s.phaseAnalysis?.tauDetected ? ' · τ' : ''}
                        {s.outcomeLabel ? ` · ${s.outcomeLabel}` : ''}
                      </div>
                    </div>

                    <div style={{ display: 'flex', gap: '8px', marginTop: '12px', flexWrap: 'wrap' }}>
                      <button
                        onClick={() => openSampleDetail(s.id)}
                        style={{ padding: '8px 10px', background: '#667eea', color: 'white', border: 'none', borderRadius: '8px', cursor: 'pointer', flex: 1 }}
                      >
                        Details
                      </button>
                      <button
                        onClick={() => loadSample(s)}
                        style={{ padding: '8px 10px', background: '#111827', color: 'white', border: 'none', borderRadius: '8px', cursor: 'pointer', flex: 1 }}
                      >
                        Load
                      </button>
                      <button
                        onClick={() => { setSelectedSampleId(s.id); setActiveTab('xrd'); }}
                        style={{ padding: '8px 10px', background: '#0ea5e9', color: 'white', border: 'none', borderRadius: '8px', cursor: 'pointer' }}
                      >
                        XRD
                      </button>
                      <button
                        onClick={() => { setSelectedSampleId(s.id); setActiveTab('mag'); }}
                        style={{ padding: '8px 10px', background: '#8b5cf6', color: 'white', border: 'none', borderRadius: '8px', cursor: 'pointer' }}
                      >
                        Mag
                      </button>
                      <button
                        onClick={() => deleteSample(s.id)}
                        style={{ padding: '8px 10px', background: '#ef4444', color: 'white', border: 'none', borderRadius: '8px', cursor: 'pointer' }}
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}

            <SampleDetailPanel
              sample={detailSample}
              onClose={() => { setDetailSample(null); setDetailBrief(''); }}
              onRefresh={() => detailSample && openSampleDetail(detailSample.id)}
              onSetOutcome={handleSetOutcome}
              onRecommend={handleRecommend}
              onExperimentBrief={handleExperimentBrief}
              aiLoading={aiLoading}
              experimentBrief={detailBrief}
            />
          </div>
        )}

        {activeTab === 'xrd' && (
          <div style={cardStyle}>
            <h2 style={{ fontSize: '20px', fontWeight: '600', color: '#1a202c', marginBottom: '10px' }}>
              XRD Analysis
            </h2>
            <p style={{ color: '#64748b', marginTop: 0 }}>
              Upload a 2-column file (angle vs intensity). Data is parsed on the server, peaks detected, and saved to MongoDB.
            </p>

            {error && (
              <div style={{ background: '#fee2e2', border: '1px solid #fca5a5', color: '#dc2626', padding: '12px 16px', borderRadius: '8px', marginBottom: '16px' }}>
                {error}
              </div>
            )}

            {uploadMessage && (
              <div style={{ background: '#dcfce7', border: '1px solid #86efac', color: '#166534', padding: '12px 16px', borderRadius: '8px', marginBottom: '16px' }}>
                {uploadMessage}
              </div>
            )}

            <div style={{ display: 'flex', gap: '16px', alignItems: 'flex-end', marginBottom: '16px', flexWrap: 'wrap' }}>
              <SamplePicker
                samples={history}
                value={selectedSampleId}
                onChange={setSelectedSampleId}
                disabled={loading}
              />
              <label style={{ display: 'inline-flex', alignItems: 'center', gap: '10px', padding: '12px 16px', border: '1px solid #e2e8f0', borderRadius: '10px', cursor: loading ? 'wait' : 'pointer', background: 'white' }}>
                <Upload size={16} />
                <span>{loading ? 'Uploading…' : 'Choose file'}</span>
                <input type="file" accept=".txt,.csv,.ras,.dat,.DAT" onChange={handleXRDUpload} disabled={loading} style={{ display: 'none' }} />
              </label>
            </div>

            {xrdData ? (
              <div style={{ border: '1px solid #e2e8f0', borderRadius: '10px', padding: '14px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '10px', flexWrap: 'wrap' }}>
                  <div><strong>File:</strong> {xrdData.filename}</div>
                  <div><strong>Points:</strong> {xrdData.points}</div>
                  <div><strong>Peaks found:</strong> {xrdData.peakCount}</div>
                  <div><strong>Processed:</strong> {xrdData.processedDate}</div>
                  {xrdData.saved && <div style={{ color: '#16a34a', fontWeight: '600' }}>✓ Saved to database</div>}
                </div>

                {xrdData.phaseAnalysis && (
                  <div style={{
                    marginTop: '12px',
                    padding: '10px',
                    borderRadius: '8px',
                    background: xrdData.phaseAnalysis.tauDetected ? '#dcfce7' : '#fef3c7',
                    color: xrdData.phaseAnalysis.tauDetected ? '#166534' : '#92400e',
                  }}>
                    <strong>Phase analysis (τ-MnAl):</strong>{' '}
                    {xrdData.phaseAnalysis.tauDetected
                      ? `Detected — ${xrdData.phaseAnalysis.matchedPeakCount} reference peaks matched (${(xrdData.phaseAnalysis.confidence * 100).toFixed(0)}% confidence)`
                      : 'τ-phase not detected in this pattern'}
                  </div>
                )}

                {xrdRecord?.data?.length > 0 ? (
                  <div style={{ marginTop: '14px', border: '1px solid #e2e8f0', borderRadius: '8px', overflow: 'hidden' }}>
                    <XRDPlot record={xrdRecord} title={`XRD pattern — ${xrdRecord.filename || xrdData.filename}`} />
                  </div>
                ) : (
                  <div style={{ marginTop: '14px', color: '#64748b', fontSize: '13px' }}>
                    No curve data to plot yet. Re-upload the file if the chart does not appear.
                  </div>
                )}

                <div style={{ marginTop: '12px', fontSize: '13px', color: '#64748b' }}>
                  Detected peaks (first 10):
                  <pre style={{ background: '#0b1220', color: '#e5e7eb', padding: '10px', borderRadius: '8px', overflowX: 'auto', marginTop: '8px' }}>
                    {(xrdData.peaks || []).slice(0, 10).map((p) => `${p.angle.toFixed(2)}\t${p.intensity.toFixed(0)}`).join('\n') || 'No peaks'}
                  </pre>
                </div>
              </div>
            ) : (
              <div style={{ color: '#64748b' }}>
                {history.length === 0
                  ? 'Create a sample in the Sample Database tab first, then select it here.'
                  : 'Select a sample and upload an XRD file (.ras, .txt, .csv, .dat).'}
              </div>
            )}
          </div>
        )}

        {activeTab === 'mag' && (
          <div style={cardStyle}>
            <h2 style={{ fontSize: '20px', fontWeight: '600', color: '#1a202c', marginBottom: '10px' }}>
              Magnetic Properties
            </h2>
            <p style={{ color: '#64748b', marginTop: 0 }}>
              Upload a 2-column file (field/temperature vs moment). Ms, Mr, and Hc are computed on the server and saved to MongoDB.
            </p>

            {error && (
              <div style={{ background: '#fee2e2', border: '1px solid #fca5a5', color: '#dc2626', padding: '12px 16px', borderRadius: '8px', marginBottom: '16px' }}>
                {error}
              </div>
            )}

            {uploadMessage && (
              <div style={{ background: '#dcfce7', border: '1px solid #86efac', color: '#166534', padding: '12px 16px', borderRadius: '8px', marginBottom: '16px' }}>
                {uploadMessage}
              </div>
            )}

            <div style={{ display: 'flex', gap: '16px', alignItems: 'flex-end', marginBottom: '16px', flexWrap: 'wrap' }}>
              <SamplePicker
                samples={history}
                value={selectedSampleId}
                onChange={setSelectedSampleId}
                disabled={loading}
              />
              <div style={{ minWidth: '160px' }}>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: '600', color: '#4a5568', marginBottom: '8px' }}>
                  Measurement type
                </label>
                <select
                  value={measurementType}
                  onChange={(e) => setMeasurementType(e.target.value)}
                  disabled={loading}
                  style={{ width: '100%', padding: '12px 16px', border: '2px solid #e2e8f0', borderRadius: '8px', fontSize: '15px' }}
                >
                  <option value="M-H">M-H (hysteresis loop)</option>
                  <option value="M-T">M-T (temperature scan)</option>
                </select>
              </div>
              <label style={{ display: 'inline-flex', alignItems: 'center', gap: '10px', padding: '12px 16px', border: '1px solid #e2e8f0', borderRadius: '10px', cursor: loading ? 'wait' : 'pointer', background: 'white' }}>
                <Upload size={16} />
                <span>{loading ? 'Uploading…' : 'Choose file'}</span>
                <input type="file" accept=".txt,.csv,.dat,.DAT" onChange={handleMagUpload} disabled={loading} style={{ display: 'none' }} />
              </label>
            </div>

            {magData ? (
              <div style={{ border: '1px solid #e2e8f0', borderRadius: '10px', padding: '14px' }}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '10px' }}>
                  <div><strong>File:</strong> {magData.filename}</div>
                  <div><strong>Type:</strong> {magData.measurementType}</div>
                  <div><strong>Points:</strong> {magData.points}</div>
                  <div><strong>Ms:</strong> {magData.Ms}</div>
                  <div><strong>Mr:</strong> {magData.Mr}</div>
                  <div><strong>Hc:</strong> {magData.Hc}</div>
                  <div><strong>Processed:</strong> {magData.processedDate}</div>
                  {magData.saved && <div style={{ color: '#16a34a', fontWeight: '600' }}>✓ Saved to database</div>}
                </div>

                {magRecords.length > 0 ? (
                  <div style={{ marginTop: '14px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
                    {magRecords.map((rec) => (
                      <div key={rec.id || `${rec.measurementType}-${rec.filename}`} style={{ border: '1px solid #e2e8f0', borderRadius: '8px', overflow: 'hidden' }}>
                        <MagneticPlot
                          record={rec}
                          measurementType={rec.measurementType}
                          title={`${rec.measurementType || 'M-H'} — ${rec.filename}`}
                        />
                      </div>
                    ))}
                  </div>
                ) : (
                  <div style={{ marginTop: '14px', color: '#64748b', fontSize: '13px' }}>
                    No curve data to plot yet. Upload M-H or M-T data above.
                  </div>
                )}
              </div>
            ) : (
              <div style={{ color: '#64748b' }}>
                {history.length === 0
                  ? 'Create a sample in the Sample Database tab first, then select it here.'
                  : 'Select a sample, choose M-H or M-T, and upload your .DAT file.'}
              </div>
            )}
          </div>
        )}

        {activeTab === 'ai' && (
          <div style={cardStyle}>
            <h2 style={{ fontSize: '20px', fontWeight: '600', color: '#1a202c', marginBottom: '8px' }}>
              Notes & parsing
            </h2>
            <p style={{ color: '#64748b', marginTop: 0, marginBottom: '16px' }}>
              Parse notebook text, rank dopants from past outcomes, ask questions about your samples, export a brief.
            </p>

            {aiStatus && (
              <div style={{
                marginBottom: '20px',
                padding: '12px 16px',
                borderRadius: '8px',
                background: aiStatus.llmAvailable ? '#ecfdf5' : '#fffbeb',
                border: `1px solid ${aiStatus.llmAvailable ? '#6ee7b7' : '#fcd34d'}`,
                fontSize: '13px',
                color: aiStatus.llmAvailable ? '#065f46' : '#92400e',
              }}>
                <strong>Text generation:</strong>{' '}
                {aiStatus.llmAvailable
                  ? `On (${aiStatus.model})`
                  : 'Off — set GEMINI_API_KEY (local: backend/.env, Render: service env). Ranker and regex parser still work.'}
              </div>
            )}

            {error && activeTab === 'ai' && (
              <div style={{ background: '#fee2e2', border: '1px solid #fca5a5', color: '#dc2626', padding: '12px 16px', borderRadius: '8px', marginBottom: '16px' }}>
                {error}
              </div>
            )}

            {uploadMessage && activeTab === 'ai' && (
              <div style={{ background: '#dcfce7', border: '1px solid #86efac', color: '#166534', padding: '12px 16px', borderRadius: '8px', marginBottom: '16px' }}>
                {uploadMessage}
              </div>
            )}

            <div style={{ display: 'flex', gap: '16px', marginBottom: '20px', flexWrap: 'wrap' }}>
              <SamplePicker
                samples={history}
                value={selectedSampleId}
                onChange={setSelectedSampleId}
                disabled={loading || aiLoading}
              />
              <button
                disabled={!selectedSampleId || aiLoading}
                onClick={() => handleRecommend(selectedSampleId)}
                style={{ padding: '12px 16px', background: '#7c3aed', color: 'white', border: 'none', borderRadius: '8px', cursor: 'pointer', fontWeight: '600' }}
              >
                Rank next experiments
              </button>
              <button
                disabled={!selectedSampleId || aiLoading}
                onClick={() => handleExperimentBrief(selectedSampleId)}
                style={{ padding: '12px 16px', background: '#0f766e', color: 'white', border: 'none', borderRadius: '8px', cursor: 'pointer', fontWeight: '600' }}
              >
                Experiment brief
              </button>
            </div>

            {lastRecommendations?.recommendations?.length > 0 && (
              <div style={{ marginBottom: '20px', border: '1px solid #e2e8f0', borderRadius: '10px', padding: '16px' }}>
                <h3 style={{ margin: '0 0 12px', fontSize: '16px', color: '#1e293b' }}>Latest recommendations</h3>
                <p style={{ fontSize: '13px', color: '#64748b', marginTop: 0 }}>{lastRecommendations.summary}</p>
                {lastRecommendations.recommendations.map((rec, i) => (
                  <div key={i} style={{ marginBottom: '10px', padding: '12px', background: '#f8fafc', borderRadius: '8px', fontSize: '13px' }}>
                    <div style={{ fontWeight: '600', color: '#4338ca' }}>{rec.suggestedFormula}</div>
                    <div style={{ color: '#64748b', marginTop: '4px' }}>Confidence: {(rec.confidence * 100).toFixed(0)}%</div>
                    <div style={{ marginTop: '6px', color: '#475569' }}>{rec.rationale}</div>
                  </div>
                ))}
              </div>
            )}

            <div style={{ border: '1px solid #e2e8f0', borderRadius: '10px', padding: '16px', marginBottom: '20px' }}>
              <h3 style={{ margin: '0 0 12px', fontSize: '16px', color: '#1e293b' }}>Ask about your samples</h3>
              <textarea
                value={copilotQuestion}
                onChange={(e) => setCopilotQuestion(e.target.value)}
                placeholder="e.g. Which samples show τ-phase? What dopant should we try next?"
                rows={3}
                style={{ ...inputStyle, width: '100%', marginBottom: '10px', resize: 'vertical' }}
              />
              <button
                disabled={aiLoading || !copilotQuestion.trim()}
                onClick={handleCopilot}
                style={{ padding: '10px 16px', background: '#667eea', color: 'white', border: 'none', borderRadius: '8px', cursor: 'pointer' }}
              >
                {aiLoading ? 'Working…' : 'Ask'}
              </button>
              {copilotAnswer && (
                <div style={{ marginTop: '14px', padding: '14px', background: '#f8fafc', borderRadius: '8px', fontSize: '14px', color: '#334155' }}>
                  <pre style={{ whiteSpace: 'pre-wrap', margin: 0, fontFamily: 'inherit' }}>{copilotAnswer}</pre>
                </div>
              )}
            </div>

            <div style={{ border: '1px solid #e2e8f0', borderRadius: '10px', padding: '16px' }}>
              <h3 style={{ margin: '0 0 12px', fontSize: '16px', color: '#1e293b' }}>Parse synthesis notes</h3>
              <textarea
                value={synthesisNotes}
                onChange={(e) => setSynthesisNotes(e.target.value)}
                placeholder="Paste lab notebook text, e.g. Arc melted MnAl, annealed 450°C for 2h, 5% C doping..."
                rows={4}
                style={{ ...inputStyle, width: '100%', marginBottom: '10px', resize: 'vertical' }}
              />
              <button
                disabled={aiLoading || !synthesisNotes.trim()}
                onClick={handleParseSynthesis}
                style={{ padding: '10px 16px', background: '#4338ca', color: 'white', border: 'none', borderRadius: '8px', cursor: 'pointer', marginRight: '10px' }}
              >
                Parse notes
              </button>
              {parsedSynthesis && (
                <div style={{ marginTop: '14px' }}>
                  <pre style={{ background: '#0b1220', color: '#e5e7eb', padding: '12px', borderRadius: '8px', fontSize: '13px', overflow: 'auto' }}>
                    {JSON.stringify(parsedSynthesis, null, 2)}
                  </pre>
                  <div style={{ display: 'flex', gap: '12px', marginTop: '12px', flexWrap: 'wrap', alignItems: 'flex-end' }}>
                    <div style={{ flex: 1, minWidth: '200px' }}>
                      <label style={{ display: 'block', fontSize: '13px', fontWeight: '600', color: '#4a5568', marginBottom: '8px' }}>
                        Apply to sample
                      </label>
                      <select
                        value={applySampleId}
                        onChange={(e) => setApplySampleId(e.target.value)}
                        style={{ width: '100%', padding: '10px', border: '2px solid #e2e8f0', borderRadius: '8px' }}
                      >
                        <option value="">Select sample…</option>
                        {history.map((s) => (
                          <option key={s.id} value={s.id}>{s.name || s.formula}</option>
                        ))}
                      </select>
                    </div>
                    <button
                      disabled={!applySampleId || aiLoading}
                      onClick={handleApplySynthesis}
                      style={{ padding: '10px 16px', background: '#16a34a', color: 'white', border: 'none', borderRadius: '8px', cursor: 'pointer' }}
                    >
                      Apply to sample
                    </button>
                  </div>
                </div>
              )}
            </div>

            {detailBrief && (
              <div style={{ marginTop: '20px', border: '1px solid #e2e8f0', borderRadius: '10px', padding: '16px' }}>
                <h3 style={{ margin: '0 0 12px', fontSize: '16px' }}>Latest experiment brief</h3>
                <pre style={{ whiteSpace: 'pre-wrap', fontSize: '14px', margin: 0, fontFamily: 'inherit', color: '#334155' }}>{detailBrief}</pre>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
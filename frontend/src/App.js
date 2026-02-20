import React, { useState, useEffect } from 'react';
import { Calculator, Database, LineChart, Magnet, Download, Copy, LogOut, Upload, Save } from 'lucide-react';
import api from './api/api';

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

function LoginForm({ onLogin }) {
  const [isRegister, setIsRegister] = useState(false);
  const [formData, setFormData] = useState({ email: '', password: '', name: '', institution: '' });
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

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
            Materials Characterization Platform
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
            disabled={submitting}
            style={{
              width: '100%',
              padding: '14px',
              background: submitting ? '#ccc' : 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
              color: 'white',
              border: 'none',
              borderRadius: '8px',
              fontSize: '16px',
              fontWeight: '600',
              cursor: submitting ? 'not-allowed' : 'pointer',
              marginBottom: '15px'
            }}
          >
            {submitting ? 'Processing...' : (isRegister ? 'Create Account' : 'Sign In')}
          </button>

          <div style={{ textAlign: 'center' }}>
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

  useEffect(() => {
    const currentUser = api.auth.getCurrentUser();
    if (currentUser) {
      setUser(currentUser);
      loadHistory();
    }
  }, []);

  const loadHistory = async () => {
    setLoading(true);
    try {
      const data = await api.samples.getAll();
      setHistory(data);
    } catch (err) {
      console.error('Failed to load history:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleLogin = (userData) => {
    setUser(userData);
    loadHistory();
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
    try {
      await api.samples.create({ ...result, name: sampleName || result.formula });
      await loadHistory();
      setSampleName('');
      alert('Sample saved successfully!');
    } catch (err) {
      alert('Failed to save sample: ' + (err.message || 'Unknown error'));
    } finally {
      setLoading(false);
    }
  };

  const loadSample = (sample) => {
    setFormula(sample.formula);
    setTargetEl(sample.targetEl);
    setTargetMass(sample.targetMass.toString());
    setResult(sample);
    setActiveTab('calc');
  };

  const deleteSample = async (id) => {
    if (!window.confirm('Are you sure you want to delete this sample?')) return;
    setLoading(true);
    try {
      await api.samples.delete(id);
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

    setLoading(true);
    try {
      const text = await file.text();
      const lines = text.split('\n').filter(l => l.trim() && !l.startsWith('#'));
      const data = lines.map(line => {
        const [x, y] = line.trim().split(/\s+/).map(Number);
        return { angle: x, intensity: y };
      }).filter(d => !isNaN(d.angle) && !isNaN(d.intensity));

      if (data.length === 0) throw new Error("File contains no valid numeric data.");
      setXrdData({ filename: file.name, data, processedDate: new Date().toLocaleString() });
    } catch (error) {
      setError(`XRD Upload/Processing Failed: ${error.message}`);
      setXrdData(null);
    } finally {
      setLoading(false);
      e.target.value = null;
    }
  };

  const handleMagUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setLoading(true);
    try {
      const text = await file.text();
      const lines = text.split('\n').filter(l => l.trim() && !l.startsWith('#'));
      const data = lines.map(line => {
        const [x, y] = line.trim().split(/\s+/).map(Number);
        return { field: x, moment: y };
      }).filter(d => !isNaN(d.field) && !isNaN(d.moment));

      if (data.length === 0) throw new Error("File contains no valid numeric data.");

      const moments = data.map(d => Math.abs(d.moment));
      const Ms = Math.max(...moments);
      let Hc = 0;
      let minMoment = Ms;
      for (const d of data) {
        if (Math.abs(d.moment) < minMoment) {
          minMoment = Math.abs(d.moment);
          Hc = d.field;
        }
      }

      setMagData({
        filename: file.name,
        data,
        Ms: Ms.toFixed(3),
        Hc: Math.abs(Hc).toFixed(3),
        processedDate: new Date().toLocaleString()
      });
    } catch (error) {
      setError(`Magnetic Upload/Processing Failed: ${error.message}`);
      setMagData(null);
    } finally {
      setLoading(false);
      e.target.value = null;
    }
  };

  if (!user) {
    return <LoginForm onLogin={handleLogin} />;
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
              <p style={{ fontSize: '12px', color: '#718096', margin: 0 }}>Materials Characterization Platform</p>
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
            { id: 'calc', label: 'Stoichiometry Calculator', icon: Calculator },
            { id: 'history', label: 'Sample Database', icon: Database },
            { id: 'xrd', label: 'XRD Analysis', icon: LineChart },
            { id: 'mag', label: 'Magnetic Properties', icon: Magnet }
          ].map(tab => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
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

            {result && (
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
              These are stored locally in your browser for now.
            </p>

            {loading ? (
              <div style={{ padding: '10px 0' }}>Loading…</div>
            ) : history.length === 0 ? (
              <div style={{ padding: '10px 0', color: '#64748b' }}>No saved samples yet.</div>
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '12px' }}>
                {history.slice().reverse().map((s) => (
                  <div key={s.id} style={{ border: '1px solid #e2e8f0', borderRadius: '10px', padding: '14px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '10px' }}>
                      <div>
                        <div style={{ fontWeight: '700', color: '#0f172a' }}>{s.name || s.formula}</div>
                        <div style={{ fontSize: '13px', color: '#64748b' }}>{s.formula}</div>
                        <div style={{ fontSize: '12px', color: '#94a3b8', marginTop: '4px' }}>
                          {s.createdAt ? new Date(s.createdAt).toLocaleString() : ''}
                        </div>
                      </div>
                      <div style={{ fontSize: '12px', color: '#64748b', textAlign: 'right' }}>
                        Total: {Number(s.total || 0).toFixed(6)} g
                      </div>
                    </div>

                    <div style={{ display: 'flex', gap: '10px', marginTop: '12px' }}>
                      <button
                        onClick={() => loadSample(s)}
                        style={{ padding: '8px 10px', background: '#111827', color: 'white', border: 'none', borderRadius: '8px', cursor: 'pointer', flex: 1 }}
                      >
                        Load
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
          </div>
        )}

        {activeTab === 'xrd' && (
          <div style={cardStyle}>
            <h2 style={{ fontSize: '20px', fontWeight: '600', color: '#1a202c', marginBottom: '10px' }}>
              XRD Analysis
            </h2>
            <p style={{ color: '#64748b', marginTop: 0 }}>
              Upload a 2-column text file (angle vs intensity). This view parses locally.
            </p>

            <div style={{ display: 'flex', gap: '12px', alignItems: 'center', marginBottom: '16px' }}>
              <label style={{ display: 'inline-flex', alignItems: 'center', gap: '10px', padding: '10px 12px', border: '1px solid #e2e8f0', borderRadius: '10px', cursor: loading ? 'wait' : 'pointer' }}>
                <Upload size={16} />
                <span>Choose file</span>
                <input type="file" accept=".txt,.csv" onChange={handleXRDUpload} disabled={loading} style={{ display: 'none' }} />
              </label>
              {xrdData?.filename && <div style={{ color: '#0f172a' }}>{xrdData.filename}</div>}
            </div>

            {xrdData ? (
              <div style={{ border: '1px solid #e2e8f0', borderRadius: '10px', padding: '14px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '10px', flexWrap: 'wrap' }}>
                  <div><strong>Points:</strong> {xrdData.data.length}</div>
                  <div><strong>Processed:</strong> {xrdData.processedDate}</div>
                </div>
                <div style={{ marginTop: '12px', fontSize: '13px', color: '#64748b' }}>
                  Preview (first 8 points):
                  <pre style={{ background: '#0b1220', color: '#e5e7eb', padding: '10px', borderRadius: '8px', overflowX: 'auto', marginTop: '8px' }}>
                    {xrdData.data.slice(0, 8).map(p => `${p.angle}\t${p.intensity}`).join('\n')}
                  </pre>
                </div>
              </div>
            ) : (
              <div style={{ color: '#64748b' }}>No XRD file loaded yet.</div>
            )}
          </div>
        )}

        {activeTab === 'mag' && (
          <div style={cardStyle}>
            <h2 style={{ fontSize: '20px', fontWeight: '600', color: '#1a202c', marginBottom: '10px' }}>
              Magnetic Properties
            </h2>
            <p style={{ color: '#64748b', marginTop: 0 }}>
              Upload a 2-column text file (field vs moment). This view parses locally and estimates Ms/Hc.
            </p>

            <div style={{ display: 'flex', gap: '12px', alignItems: 'center', marginBottom: '16px' }}>
              <label style={{ display: 'inline-flex', alignItems: 'center', gap: '10px', padding: '10px 12px', border: '1px solid #e2e8f0', borderRadius: '10px', cursor: loading ? 'wait' : 'pointer' }}>
                <Upload size={16} />
                <span>Choose file</span>
                <input type="file" accept=".txt,.csv" onChange={handleMagUpload} disabled={loading} style={{ display: 'none' }} />
              </label>
              {magData?.filename && <div style={{ color: '#0f172a' }}>{magData.filename}</div>}
            </div>

            {magData ? (
              <div style={{ border: '1px solid #e2e8f0', borderRadius: '10px', padding: '14px' }}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '10px' }}>
                  <div><strong>Points:</strong> {magData.data.length}</div>
                  <div><strong>Ms:</strong> {magData.Ms}</div>
                  <div><strong>Hc:</strong> {magData.Hc}</div>
                  <div><strong>Processed:</strong> {magData.processedDate}</div>
                </div>
                <div style={{ marginTop: '12px', fontSize: '13px', color: '#64748b' }}>
                  Preview (first 8 points):
                  <pre style={{ background: '#0b1220', color: '#e5e7eb', padding: '10px', borderRadius: '8px', overflowX: 'auto', marginTop: '8px' }}>
                    {magData.data.slice(0, 8).map(p => `${p.field}\t${p.moment}`).join('\n')}
                  </pre>
                </div>
              </div>
            ) : (
              <div style={{ color: '#64748b' }}>No magnetic file loaded yet.</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
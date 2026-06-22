import React from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceDot,
  Label,
} from 'recharts';

// Origin-style default hkl labels (matches reference XRD figure).
const DEFAULT_HKL = ['(111)', '(200)', '(102)', '(202)', '(311)', '(222)'];

const AXIS_COLOR = '#111827';
const AXIS_FONT = { fontSize: 15, fill: AXIS_COLOR, fontWeight: 600 };
const TICK_FONT = { fontSize: 12, fill: AXIS_COLOR };

// Pick the strongest peaks, then order them by angle and assign Miller indices.
export function assignHklLabels(peaks, labels = DEFAULT_HKL) {
  if (!peaks || peaks.length === 0) return [];
  const byIntensity = [...peaks].sort((a, b) => b.intensity - a.intensity);
  const top = byIntensity.slice(0, labels.length);
  top.sort((a, b) => a.angle - b.angle);
  return top.map((p, i) => ({ ...p, hkl: labels[i] }));
}

const originAxisLine = { stroke: AXIS_COLOR, strokeWidth: 1.5 };
const originTickLine = { stroke: AXIS_COLOR };

export function XRDPlot({ record, color = '#1d4ff5', title }) {
  if (!record || !record.data || record.data.length === 0) {
    return (
      <div style={{ color: '#94a3b8', fontSize: '13px', padding: '12px 0' }}>
        No XRD curve data to plot for this record.
      </div>
    );
  }

  const data = record.data.map((d) => ({ x: d.angle, y: d.intensity }));
  const labeledPeaks = assignHklLabels(record.peaks || []);

  return (
    <div style={{ width: '100%', background: 'white', borderRadius: '10px', padding: '12px 8px 4px' }}>
      {title && (
        <div style={{ textAlign: 'center', fontWeight: 600, color: AXIS_COLOR, marginBottom: '6px' }}>
          {title}
        </div>
      )}
      <ResponsiveContainer width="100%" height={360}>
        <LineChart data={data} margin={{ top: 24, right: 30, bottom: 36, left: 16 }}>
          <XAxis
            dataKey="x"
            type="number"
            domain={['dataMin', 'dataMax']}
            axisLine={originAxisLine}
            tickLine={originTickLine}
            tick={TICK_FONT}
            tickCount={9}
            allowDecimals={false}
          >
            <Label value="2θ (degrees)" position="bottom" offset={12} style={AXIS_FONT} />
          </XAxis>
          <YAxis
            axisLine={originAxisLine}
            tickLine={originTickLine}
            tick={TICK_FONT}
            width={64}
          >
            <Label
              value="Intensity (arb. units)"
              angle={-90}
              position="insideLeft"
              style={{ ...AXIS_FONT, textAnchor: 'middle' }}
            />
          </YAxis>
          <Tooltip
            formatter={(v) => [Number(v).toFixed(0), 'Intensity']}
            labelFormatter={(l) => `2θ = ${Number(l).toFixed(2)}°`}
          />
          <Legend verticalAlign="top" height={28} />
          <Line
            type="linear"
            dataKey="y"
            name={record.filename || 'XRD pattern'}
            stroke={color}
            strokeWidth={1}
            dot={false}
            isAnimationActive={false}
          />
          {labeledPeaks.map((p, i) => (
            <ReferenceDot
              key={i}
              x={p.angle}
              y={p.intensity}
              r={2}
              fill="#dc2626"
              stroke="none"
              label={{ value: p.hkl, position: 'top', fill: '#dc2626', fontSize: 13, fontWeight: 600 }}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function MagneticPlot({ record, color = '#1414ff', title, measurementType }) {
  if (!record || !record.data || record.data.length === 0) {
    return (
      <div style={{ color: '#94a3b8', fontSize: '13px', padding: '12px 0' }}>
        No magnetometry curve data to plot for this record.
      </div>
    );
  }

  const type = measurementType || record.measurementType || 'M-H';
  const isMT = type.toUpperCase().includes('M-T') || type.toLowerCase().includes('temp');

  const maxAbsField = Math.max(...record.data.map((d) => Math.abs(d.x)));
  const useKOe = !isMT && maxAbsField > 1000;
  const scale = useKOe ? 1000 : 1;
  const xAxisLabel = isMT ? 'Temperature (K)' : `Magnetic Field (${useKOe ? 'KOe' : 'Oe'})`;
  const fieldUnit = useKOe ? 'KOe' : isMT ? 'K' : 'Oe';
  const seriesName = isMT ? 'M-T curve' : 'M-H loop';

  const data = record.data.map((d) => ({ x: isMT ? d.x : d.x / scale, y: d.y }));

  return (
    <div style={{ width: '100%', background: 'white', borderRadius: '10px', padding: '12px 8px 4px' }}>
      {title && (
        <div style={{ textAlign: 'center', fontWeight: 600, color: AXIS_COLOR, marginBottom: '6px' }}>
          {title}
        </div>
      )}
      <ResponsiveContainer width="100%" height={360}>
        <LineChart data={data} margin={{ top: 20, right: 30, bottom: 36, left: 16 }}>
          <XAxis
            dataKey="x"
            type="number"
            domain={['dataMin', 'dataMax']}
            axisLine={originAxisLine}
            tickLine={originTickLine}
            tick={TICK_FONT}
            tickCount={7}
          >
            <Label value={xAxisLabel} position="bottom" offset={12} style={AXIS_FONT} />
          </XAxis>
          <YAxis
            axisLine={originAxisLine}
            tickLine={originTickLine}
            tick={TICK_FONT}
            width={70}
          >
            <Label
              value="Magnetic Moment (emu/g)"
              angle={-90}
              position="insideLeft"
              style={{ ...AXIS_FONT, textAnchor: 'middle' }}
            />
          </YAxis>
          <Tooltip
            formatter={(v) => [Number(v).toFixed(2), 'Moment (emu/g)']}
            labelFormatter={(l) => (isMT ? `T = ${Number(l).toFixed(2)} K` : `H = ${Number(l).toFixed(2)} ${fieldUnit}`)}
          />
          <Line
            type="linear"
            dataKey="y"
            name={record.filename || seriesName}
            stroke={color}
            strokeWidth={3}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

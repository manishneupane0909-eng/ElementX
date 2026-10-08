import {
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { XrdCandidatePeak } from '../services/magnetApi'

interface XrdPlotProps {
  twoThetaDeg: number[]
  intensity: number[]
  peaks?: XrdCandidatePeak[]
}

function formatTick(value: number): string {
  if (!Number.isFinite(value)) {
    return '—'
  }
  const absolute = Math.abs(value)
  if (absolute >= 100) {
    return value.toLocaleString(undefined, { maximumFractionDigits: 1 })
  }
  return value.toLocaleString(undefined, { maximumFractionDigits: 3 })
}

export default function XrdPlot({ twoThetaDeg, intensity, peaks = [] }: XrdPlotProps) {
  if (
    twoThetaDeg.length === 0 ||
    twoThetaDeg.length !== intensity.length
  ) {
    return (
      <p className="magnetometry-empty">No measured XRD points were returned for this plot.</p>
    )
  }

  const points = twoThetaDeg.map((twoTheta, index) => ({
    index,
    twoTheta,
    intensity: intensity[index],
  }))

  const peakPoints = peaks.flatMap((peak) => {
    const index = twoThetaDeg.findIndex(
      (value, pointIndex) =>
        value === peak.two_theta_deg && intensity[pointIndex] === peak.intensity,
    )
    if (index < 0) {
      return []
    }
    return [
      {
        index,
        twoTheta: peak.two_theta_deg,
        intensity: peak.intensity,
      },
    ]
  })

  return (
    <div
      className="scientific-plot xrd-plot"
      role="img"
      aria-label={`Intensity (arb. units) against 2θ (degrees), ${points.length} measured points`}
    >
      <ResponsiveContainer width="100%" height={340}>
        <ComposedChart data={points} margin={{ top: 16, right: 24, bottom: 24, left: 16 }}>
          <CartesianGrid stroke="var(--plot-grid)" strokeDasharray="3 3" />
          <XAxis
            dataKey="index"
            type="number"
            domain={[0, Math.max(points.length - 1, 0)]}
            tickFormatter={(index) => {
              const point = points[Number(index)]
              return point ? formatTick(point.twoTheta) : ''
            }}
            label={{
              value: '2θ (degrees)',
              position: 'insideBottom',
              offset: -12,
            }}
          />
          <YAxis
            dataKey="intensity"
            type="number"
            tickFormatter={formatTick}
            width={72}
            label={{
              value: 'Intensity (arb. units)',
              angle: -90,
              position: 'insideLeft',
              offset: 4,
              style: { textAnchor: 'middle' },
            }}
          />
          <Tooltip
            formatter={(value) => [
              `${formatTick(Number(value))} arb. units`,
              'Intensity',
            ]}
            labelFormatter={(index) => {
              const point = points[Number(index)]
              return point ? `2θ: ${formatTick(point.twoTheta)} °` : ''
            }}
          />
          <Line
            type="linear"
            dataKey="intensity"
            stroke="var(--plot-series-1)"
            strokeWidth={1.5}
            dot={{ r: 1.25, fill: 'var(--plot-series-1)', strokeWidth: 0 }}
            isAnimationActive={false}
            connectNulls={false}
          />
          {peakPoints.length > 0 && (
            <Scatter
              data={peakPoints}
              dataKey="intensity"
              fill="var(--plot-series-2)"
              name="Detected intensity maxima"
              isAnimationActive={false}
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>
      <p className="scientific-plot__caption">{points.length} measured points</p>
    </div>
  )
}

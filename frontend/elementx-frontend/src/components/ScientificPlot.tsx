import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

export interface PlotPoint {
  x: number
  y: number
}

export interface PlotReferenceLine {
  x: number
  label: string
}

interface ScientificPlotProps {
  points: PlotPoint[]
  xLabel: string
  yLabel: string
  xUnit: string
  yUnit: string
  referenceX?: PlotReferenceLine[]
  height?: number
}

function formatTick(value: number): string {
  if (!Number.isFinite(value)) {
    return '—'
  }
  const absolute = Math.abs(value)
  if (absolute >= 1000) {
    return value.toLocaleString(undefined, { maximumFractionDigits: 0 })
  }
  if (absolute >= 1) {
    return value.toLocaleString(undefined, { maximumFractionDigits: 3 })
  }
  return value.toLocaleString(undefined, { maximumFractionDigits: 6 })
}

export default function ScientificPlot({
  points,
  xLabel,
  yLabel,
  xUnit,
  yUnit,
  referenceX = [],
  height = 340,
}: ScientificPlotProps) {
  if (points.length === 0) {
    return (
      <p className="magnetometry-empty">No measured points were returned for this plot.</p>
    )
  }

  return (
    <div
      className="scientific-plot"
      role="img"
      aria-label={`${yLabel} (${yUnit}) against ${xLabel} (${xUnit}), ${points.length} measured points`}
    >
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={points} margin={{ top: 16, right: 24, bottom: 24, left: 16 }}>
          <CartesianGrid stroke="var(--plot-grid)" strokeDasharray="3 3" />
          <XAxis
            dataKey="x"
            type="number"
            tickFormatter={formatTick}
            label={{
              value: `${xLabel} (${xUnit})`,
              position: 'insideBottom',
              offset: -12,
            }}
          />
          <YAxis
            dataKey="y"
            type="number"
            tickFormatter={formatTick}
            width={72}
            label={{
              value: `${yLabel} (${yUnit})`,
              angle: -90,
              position: 'insideLeft',
              offset: 4,
              style: { textAnchor: 'middle' },
            }}
          />
          <Tooltip
            formatter={(value) => [
              `${formatTick(Number(value))} ${yUnit}`,
              yLabel,
            ]}
            labelFormatter={(value) => `${xLabel}: ${formatTick(Number(value))} ${xUnit}`}
          />
          <ReferenceLine x={0} stroke="var(--plot-ref)" strokeDasharray="4 4" />
          <ReferenceLine y={0} stroke="var(--plot-ref)" strokeDasharray="4 4" />
          {referenceX.map((line) => (
            <ReferenceLine
              key={`${line.label}-${line.x}`}
              x={line.x}
              stroke="var(--plot-series-2)"
              strokeDasharray="2 4"
              label={{ value: line.label, fill: 'var(--plot-series-2)', fontSize: 11 }}
            />
          ))}
          <Line
            type="linear"
            dataKey="y"
            stroke="var(--plot-series-1)"
            strokeWidth={1.5}
            dot={{ r: 1.25, fill: 'var(--plot-series-1)', strokeWidth: 0 }}
            isAnimationActive={false}
            connectNulls={false}
          />
        </LineChart>
      </ResponsiveContainer>
      <p className="scientific-plot__caption">{points.length} measured points</p>
    </div>
  )
}

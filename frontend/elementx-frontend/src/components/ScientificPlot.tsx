import { useEffect, useId, useRef, useState } from 'react'
import type { FormEvent, RefObject } from 'react'
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import Button from './ui/Button'

export interface PlotPoint {
  x: number
  y: number
}

export interface PlotReferenceLine {
  x: number
  label: string
  /** Which side of the line the label sits on, so neighbouring labels do not overlap. */
  side?: 'left' | 'right'
}

interface ScientificPlotProps {
  points: PlotPoint[]
  xLabel: string
  yLabel: string
  xUnit: string
  yUnit: string
  referenceX?: PlotReferenceLine[]
  height?: number
  /** Heading for the enlarged view. */
  title?: string
  /** Base file name for exported data and images. */
  exportName?: string
}

type Range = [number, number]
type ChartPoint = { x: number; y: number | null }

const COMPACT_WIDTH = 480
const SVG_STYLE_PROPERTIES = [
  'fill',
  'fill-opacity',
  'stroke',
  'stroke-width',
  'stroke-dasharray',
  'stroke-opacity',
  'opacity',
  'font-family',
  'font-size',
  'font-weight',
  'text-anchor',
  'dominant-baseline',
]

function withMinus(text: string): string {
  return text.startsWith('-') ? `−${text.slice(1)}` : text
}

function formatTick(value: number): string {
  if (!Number.isFinite(value)) {
    return '—'
  }
  const absolute = Math.abs(value)
  const digits = absolute >= 1000 ? 0 : absolute >= 1 ? 3 : 6
  return withMinus(value.toLocaleString(undefined, { maximumFractionDigits: digits }))
}

/**
 * Measured points whose x lies inside the range. Where the series leaves the range and comes back
 * (a hysteresis loop crosses the window on both branches), a gap is inserted so the plot never
 * draws a line between points that were not measured consecutively.
 */
function pointsInRange(points: PlotPoint[], range: Range | null): ChartPoint[] {
  if (!range) {
    return points
  }
  const [low, high] = range
  const visible: ChartPoint[] = []
  let previousIndex = -2
  points.forEach((point, index) => {
    if (point.x < low || point.x > high) {
      return
    }
    if (visible.length > 0 && previousIndex !== index - 1) {
      visible.push({ x: point.x, y: null })
    }
    visible.push(point)
    previousIndex = index
  })
  return visible
}

function useElementWidth(ref: RefObject<HTMLElement | null>): number {
  const [width, setWidth] = useState(0)
  useEffect(() => {
    const element = ref.current
    if (!element) return
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width))
    observer.observe(element)
    return () => observer.disconnect()
  }, [ref])
  return width
}

function safeFileName(name: string): string {
  return name.replace(/[^\w.-]+/g, '_').replace(/^_+|_+$/g, '') || 'elementx-plot'
}

function download(fileName: string, type: string, content: string) {
  const url = URL.createObjectURL(new Blob([content], { type }))
  const link = document.createElement('a')
  link.href = url
  link.download = fileName
  document.body.append(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 0)
}

function csvCell(text: string): string {
  return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text
}

/** Serialises the rendered chart with its theme colours resolved, so the file stands alone. */
function serializeChart(container: HTMLElement | null, title: string): string | null {
  const source = container?.querySelector<SVGSVGElement>('svg.recharts-surface')
  if (!source) return null

  const clone = source.cloneNode(true) as SVGSVGElement
  const sourceNodes = [source, ...source.querySelectorAll('*')]
  const cloneNodes = [clone, ...clone.querySelectorAll('*')]
  sourceNodes.forEach((node, index) => {
    const target = cloneNodes[index] as SVGElement | undefined
    if (!target) return
    const computed = getComputedStyle(node)
    for (const property of SVG_STYLE_PROPERTIES) {
      const value = computed.getPropertyValue(property)
      if (value) target.style.setProperty(property, value)
    }
    for (const attribute of [...target.attributes]) {
      if (attribute.value.includes('var(')) target.removeAttribute(attribute.name)
    }
  })

  const { width, height } = source.getBoundingClientRect()
  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
  clone.setAttribute('width', String(Math.round(width)))
  clone.setAttribute('height', String(Math.round(height)))
  clone.setAttribute('viewBox', `0 0 ${Math.round(width)} ${Math.round(height)}`)
  clone.removeAttribute('tabindex')

  const background = document.createElementNS('http://www.w3.org/2000/svg', 'rect')
  background.setAttribute('width', '100%')
  background.setAttribute('height', '100%')
  background.setAttribute(
    'fill',
    getComputedStyle(document.documentElement).getPropertyValue('--plot-surface').trim() || '#ffffff',
  )
  const titleNode = document.createElementNS('http://www.w3.org/2000/svg', 'title')
  titleNode.textContent = title
  clone.prepend(background)
  clone.prepend(titleNode)

  return `<?xml version="1.0" encoding="UTF-8"?>\n${new XMLSerializer().serializeToString(clone)}`
}

interface ChartProps {
  data: ChartPoint[]
  range: Range | null
  height: number
  compact: boolean
  xLabel: string
  yLabel: string
  xUnit: string
  yUnit: string
  referenceX: PlotReferenceLine[]
  onZoom: (range: Range) => void
}

function Chart({
  data,
  range,
  height,
  compact,
  xLabel,
  yLabel,
  xUnit,
  yUnit,
  referenceX,
  onZoom,
}: ChartProps) {
  const [dragStart, setDragStart] = useState<number | null>(null)
  const [dragEnd, setDragEnd] = useState<number | null>(null)

  const xAt = (index: unknown): number | null => {
    // Recharts reports the active index as a string.
    const position = typeof index === 'number' || typeof index === 'string' ? Number(index) : NaN
    const point = Number.isInteger(position) ? data[position] : undefined
    return point ? point.x : null
  }

  const finishDrag = () => {
    if (dragStart !== null && dragEnd !== null && dragStart !== dragEnd) {
      onZoom([Math.min(dragStart, dragEnd), Math.max(dragStart, dragEnd)])
    }
    setDragStart(null)
    setDragEnd(null)
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart
        data={data}
        margin={
          compact
            ? { top: 12, right: 18, bottom: 22, left: 2 }
            : { top: 16, right: 24, bottom: 24, left: 16 }
        }
        onMouseDown={(state) => {
          const x = xAt(state?.activeTooltipIndex)
          if (x !== null) {
            setDragStart(x)
            setDragEnd(x)
          }
        }}
        onMouseMove={(state) => {
          if (dragStart === null) return
          const x = xAt(state?.activeTooltipIndex)
          if (x !== null) setDragEnd(x)
        }}
        onMouseUp={finishDrag}
        onMouseLeave={() => {
          setDragStart(null)
          setDragEnd(null)
        }}
      >
        <CartesianGrid stroke="var(--plot-grid)" strokeDasharray="3 3" />
        <XAxis
          dataKey="x"
          type="number"
          domain={range ?? undefined}
          allowDataOverflow={range !== null}
          tickFormatter={formatTick}
          tickMargin={8}
          interval="preserveStartEnd"
          minTickGap={compact ? 18 : 8}
          label={{
            value: `${xLabel} (${xUnit})`,
            position: 'insideBottom',
            offset: compact ? -14 : -12,
          }}
        />
        <YAxis
          dataKey="y"
          type="number"
          tickFormatter={formatTick}
          width={compact ? 62 : 72}
          label={{
            value: `${yLabel} (${yUnit})`,
            angle: -90,
            position: 'insideLeft',
            offset: compact ? 2 : 4,
            style: { textAnchor: 'middle' },
          }}
        />
        <Tooltip
          formatter={(value) => [`${formatTick(Number(value))} ${yUnit}`, yLabel]}
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
            label={{
              value: line.label,
              fill: 'var(--plot-series-2)',
              fontSize: 11,
              position:
                line.side === 'left'
                  ? 'insideTopRight'
                  : line.side === 'right'
                    ? 'insideTopLeft'
                    : 'top',
            }}
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
        {dragStart !== null && dragEnd !== null && dragStart !== dragEnd && (
          <ReferenceArea
            x1={dragStart}
            x2={dragEnd}
            fill="var(--accent)"
            fillOpacity={0.15}
            stroke="var(--accent)"
            strokeOpacity={0.6}
          />
        )}
      </LineChart>
    </ResponsiveContainer>
  )
}

interface RangeFormProps {
  xLabel: string
  xUnit: string
  range: Range | null
  extent: Range
  points: PlotPoint[]
  onApply: (range: Range) => void
  onClose: () => void
}

function RangeForm({ xLabel, xUnit, range, extent, points, onApply, onClose }: RangeFormProps) {
  const [from, setFrom] = useState(String((range ?? extent)[0]))
  const [to, setTo] = useState(String((range ?? extent)[1]))
  const [error, setError] = useState<string | null>(null)
  const fromId = useId()
  const toId = useId()
  const errorId = useId()

  const submit = (event: FormEvent) => {
    event.preventDefault()
    const low = Number(from)
    const high = Number(to)
    if (from.trim() === '' || to.trim() === '' || !Number.isFinite(low) || !Number.isFinite(high)) {
      setError('Enter numeric limits for both ends.')
      return
    }
    if (low >= high) {
      setError('The lower limit must be smaller than the upper limit.')
      return
    }
    if (!points.some((point) => point.x >= low && point.x <= high)) {
      setError('No measured points fall inside this range.')
      return
    }
    setError(null)
    onApply([low, high])
  }

  return (
    <form className="plot-range" onSubmit={submit} aria-label={`${xLabel} range`}>
      <div className="plot-range__field">
        <label htmlFor={fromId}>
          {xLabel} from ({xUnit})
        </label>
        <input
          id={fromId}
          className="text-input"
          type="number"
          step="any"
          inputMode="decimal"
          value={from}
          onChange={(event) => setFrom(event.target.value)}
          aria-describedby={error ? errorId : undefined}
          aria-invalid={error ? true : undefined}
        />
      </div>
      <div className="plot-range__field">
        <label htmlFor={toId}>to ({xUnit})</label>
        <input
          id={toId}
          className="text-input"
          type="number"
          step="any"
          inputMode="decimal"
          value={to}
          onChange={(event) => setTo(event.target.value)}
          aria-describedby={error ? errorId : undefined}
          aria-invalid={error ? true : undefined}
        />
      </div>
      <div className="plot-range__actions">
        <Button type="submit" variant="primary">
          Apply
        </Button>
        <Button onClick={onClose}>Close</Button>
      </div>
      {error && (
        <p className="plot-range__error" id={errorId} role="alert">
          {error}
        </p>
      )}
    </form>
  )
}

interface PlotViewProps extends Omit<ScientificPlotProps, 'height' | 'referenceX'> {
  referenceX: PlotReferenceLine[]
  height: number
  range: Range | null
  onRangeChange: (range: Range | null) => void
  onEnlarge?: () => void
}

function PlotView({
  points,
  xLabel,
  yLabel,
  xUnit,
  yUnit,
  referenceX,
  height,
  title,
  exportName,
  range,
  onRangeChange,
  onEnlarge,
}: PlotViewProps) {
  const frameRef = useRef<HTMLDivElement | null>(null)
  const width = useElementWidth(frameRef)
  const compact = width > 0 && width < COMPACT_WIDTH
  const [rangeOpen, setRangeOpen] = useState(false)
  const rangeButtonRef = useRef<HTMLButtonElement | null>(null)

  const data = pointsInRange(points, range)
  const visibleCount = range ? data.filter((point) => point.y !== null).length : points.length
  const extent = points.reduce<Range>(
    ([low, high], point) => [Math.min(low, point.x), Math.max(high, point.x)],
    [Infinity, -Infinity],
  )
  const plotTitle = title ?? `${yLabel} against ${xLabel}`
  const baseName = safeFileName(exportName ?? plotTitle)

  const exportCsv = () => {
    const header = [`${xLabel} (${xUnit})`, `${yLabel} (${yUnit})`].map(csvCell).join(',')
    const rows = points.map((point) => `${point.x},${point.y}`)
    download(`${baseName}.csv`, 'text/csv;charset=utf-8', `${[header, ...rows].join('\n')}\n`)
  }

  const exportSvg = () => {
    const svg = serializeChart(frameRef.current, plotTitle)
    if (svg) download(`${baseName}.svg`, 'image/svg+xml;charset=utf-8', svg)
  }

  const closeRange = () => {
    setRangeOpen(false)
    rangeButtonRef.current?.focus()
  }

  const rangeText = range
    ? `${xLabel} ${formatTick(range[0])} to ${formatTick(range[1])} ${xUnit}`
    : null

  return (
    <div className="plot-view">
      <div className="plot-toolbar" role="group" aria-label={`${plotTitle} plot controls`}>
        <Button
          ref={rangeButtonRef}
          className="plot-toolbar__btn"
          aria-expanded={rangeOpen}
          onClick={() => setRangeOpen((open) => !open)}
        >
          Set range
        </Button>
        <Button
          className="plot-toolbar__btn"
          onClick={() => onRangeChange(null)}
          disabled={range === null}
        >
          Reset range
        </Button>
        {onEnlarge && (
          <Button className="plot-toolbar__btn" onClick={onEnlarge} aria-haspopup="dialog">
            Enlarge
          </Button>
        )}
        <Button className="plot-toolbar__btn" onClick={exportSvg}>
          Export SVG
        </Button>
        <Button
          className="plot-toolbar__btn"
          onClick={exportCsv}
          aria-label={`Export all ${points.length} measured points as CSV`}
        >
          Export CSV
        </Button>
      </div>

      {rangeOpen && (
        <RangeForm
          key={range ? range.join(':') : 'full'}
          xLabel={xLabel}
          xUnit={xUnit}
          range={range}
          extent={extent}
          points={points}
          onApply={(next) => onRangeChange(next)}
          onClose={closeRange}
        />
      )}

      <div
        className="scientific-plot"
        ref={frameRef}
        role="figure"
        aria-label={`${yLabel} (${yUnit}) against ${xLabel} (${xUnit}), ${visibleCount} measured points${rangeText ? `, ${rangeText}` : ''}`}
      >
        <Chart
          data={data}
          range={range}
          height={compact ? Math.min(height, onEnlarge ? 300 : 520) : height}
          compact={compact}
          xLabel={xLabel}
          yLabel={yLabel}
          xUnit={xUnit}
          yUnit={yUnit}
          referenceX={referenceX}
          onZoom={onRangeChange}
        />
        <p className="scientific-plot__caption" aria-live="polite">
          {range
            ? `Showing ${visibleCount} of ${points.length} measured points · ${rangeText}`
            : `${points.length} measured points`}
          {!compact && (
            <span className="scientific-plot__hint">
              {range ? '' : ' · drag across the plot to zoom'} · arrow keys step through points
            </span>
          )}
        </p>
      </div>
    </div>
  )
}

export default function ScientificPlot({
  points,
  xLabel,
  yLabel,
  xUnit,
  yUnit,
  referenceX = [],
  height = 340,
  title,
  exportName,
}: ScientificPlotProps) {
  const [range, setRange] = useState<Range | null>(null)
  const [enlarged, setEnlarged] = useState(false)
  const dialogRef = useRef<HTMLDialogElement | null>(null)
  const openerRef = useRef<HTMLElement | null>(null)
  const headingId = useId()

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    if (enlarged && !dialog.open) dialog.showModal()
    if (!enlarged && dialog.open) dialog.close()
  }, [enlarged])

  if (points.length === 0) {
    return (
      <p className="magnetometry-empty">No measured points were returned for this plot.</p>
    )
  }

  const plotTitle = title ?? `${yLabel} against ${xLabel}`
  const shared = { points, xLabel, yLabel, xUnit, yUnit, referenceX, title: plotTitle, exportName }

  const openEnlarged = () => {
    openerRef.current = document.activeElement as HTMLElement | null
    setEnlarged(true)
  }

  return (
    <>
      <PlotView
        {...shared}
        height={height}
        range={range}
        onRangeChange={setRange}
        onEnlarge={openEnlarged}
      />
      <dialog
        ref={dialogRef}
        className="plot-dialog"
        aria-labelledby={headingId}
        onClose={() => {
          setEnlarged(false)
          openerRef.current?.focus()
        }}
      >
        <div className="plot-dialog__head">
          <h2 id={headingId} className="plot-dialog__title">
            {plotTitle}
          </h2>
          <Button onClick={() => setEnlarged(false)} autoFocus>
            Close
          </Button>
        </div>
        {enlarged && (
          <PlotView
            {...shared}
            height={Math.max(320, Math.min(window.innerHeight - 220, 720))}
            range={range}
            onRangeChange={setRange}
          />
        )}
      </dialog>
    </>
  )
}

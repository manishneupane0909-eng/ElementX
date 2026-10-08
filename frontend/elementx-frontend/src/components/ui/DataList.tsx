import type { ReactNode } from 'react'

export function ResultRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="kv__row">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  )
}

/** Dense label/value list. Values use tabular figures so columns of numbers line up. */
export default function DataList({
  children,
  label,
  columns = false,
}: {
  children: ReactNode
  label?: string
  /** Flow rows into several columns when there is room (for wide, short lists). */
  columns?: boolean
}) {
  return (
    <dl className={columns ? 'kv kv--cols' : 'kv'} aria-label={label}>
      {children}
    </dl>
  )
}

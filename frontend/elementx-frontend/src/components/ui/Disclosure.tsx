import type { ReactNode, SyntheticEvent } from 'react'

interface DisclosureProps {
  summary: ReactNode
  children: ReactNode
  /** Controlled open state; omit to let the element manage itself. */
  open?: boolean
  defaultOpen?: boolean
  onOpenChange?: (open: boolean) => void
  className?: string
}

/**
 * Expandable section built on <details>. Collapsed content stays in the document, so values are
 * never discarded and in-page search can still reveal them.
 */
export default function Disclosure({
  summary,
  children,
  open,
  defaultOpen,
  onOpenChange,
  className,
}: DisclosureProps) {
  const handleToggle = (event: SyntheticEvent<HTMLDetailsElement>) => {
    const next = event.currentTarget.open
    if (next !== open) onOpenChange?.(next)
  }

  return (
    <details
      className={['disclosure', className].filter(Boolean).join(' ')}
      open={open ?? defaultOpen}
      onToggle={handleToggle}
    >
      <summary className="disclosure__summary">{summary}</summary>
      <div className="disclosure__body">{children}</div>
    </details>
  )
}

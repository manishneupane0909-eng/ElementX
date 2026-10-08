import type { ReactNode } from 'react'

export type NoticeKind = 'info' | 'error' | 'warning' | 'loading' | 'empty'

interface NoticeProps {
  kind?: NoticeKind
  children: ReactNode
}

/**
 * One component for the messages a screen shows about itself: loading, empty and error states
 * share the same look and the right live-region semantics.
 */
export default function Notice({ kind = 'info', children }: NoticeProps) {
  if (kind === 'empty') {
    return <p className="empty-state">{children}</p>
  }
  const modifier =
    kind === 'error' ? 'error' : kind === 'warning' ? 'conflict' : 'info'
  const role = kind === 'error' ? 'alert' : 'status'
  return (
    <div className={`status-banner status-banner--${modifier}`} role={role}>
      {children}
    </div>
  )
}

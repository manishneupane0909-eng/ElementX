import { useId } from 'react'
import type { ReactNode } from 'react'

interface SectionProps {
  title: string
  /** Heading level: sections use h2, sub-sections inside them use h3. */
  level?: 2 | 3
  description?: ReactNode
  actions?: ReactNode
  children?: ReactNode
  className?: string
}

/** Flat, unboxed content section: a heading with a hairline above it and optional actions. */
export default function Section({
  title,
  level = 2,
  description,
  actions,
  children,
  className,
}: SectionProps) {
  const id = useId()
  const Heading = level === 2 ? 'h2' : 'h3'
  return (
    <section
      className={['section', `section--h${level}`, className].filter(Boolean).join(' ')}
      aria-labelledby={id}
    >
      <div className="section__head">
        <Heading id={id} className="section__title">
          {title}
        </Heading>
        {actions && <div className="section__actions">{actions}</div>}
      </div>
      {description && <p className="section__description">{description}</p>}
      {children}
    </section>
  )
}

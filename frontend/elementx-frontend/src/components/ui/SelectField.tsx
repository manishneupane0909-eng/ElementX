import { useId } from 'react'
import type { SelectHTMLAttributes } from 'react'

interface SelectFieldProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, 'id'> {
  label: string
  hint?: string
}

export default function SelectField({
  label,
  hint,
  className,
  children,
  ...rest
}: SelectFieldProps) {
  const id = useId()
  const hintId = hint ? `${id}-hint` : undefined
  return (
    <div className="form-field">
      <label className="field-label" htmlFor={id}>
        {label}
      </label>
      <select
        id={id}
        className={['text-input', className].filter(Boolean).join(' ')}
        aria-describedby={hintId}
        {...rest}
      >
        {children}
      </select>
      {hint && (
        <p className="field-hint" id={hintId}>
          {hint}
        </p>
      )}
    </div>
  )
}

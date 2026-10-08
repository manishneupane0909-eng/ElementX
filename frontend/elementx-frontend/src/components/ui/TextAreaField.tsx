import { useId } from 'react'
import type { ComponentPropsWithRef } from 'react'

interface TextAreaFieldProps extends Omit<ComponentPropsWithRef<'textarea'>, 'id'> {
  label: string
  hint?: string
}

export default function TextAreaField({ label, hint, className, ...rest }: TextAreaFieldProps) {
  const id = useId()
  const hintId = hint ? `${id}-hint` : undefined
  return (
    <div className="form-field">
      <label className="field-label" htmlFor={id}>
        {label}
      </label>
      <textarea
        id={id}
        className={['text-input', className].filter(Boolean).join(' ')}
        aria-describedby={hintId}
        {...rest}
      />
      {hint && (
        <p className="field-hint" id={hintId}>
          {hint}
        </p>
      )}
    </div>
  )
}

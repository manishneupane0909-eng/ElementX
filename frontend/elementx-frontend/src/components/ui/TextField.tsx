import { useId } from 'react'
import type { InputHTMLAttributes } from 'react'

interface TextFieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'id'> {
  label: string
  hint?: string
}

/** Label + input pair with a guaranteed association and optional helper text. */
export default function TextField({ label, hint, className, ...rest }: TextFieldProps) {
  const id = useId()
  const hintId = hint ? `${id}-hint` : undefined
  return (
    <div className="form-field">
      <label className="field-label" htmlFor={id}>
        {label}
      </label>
      <input
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

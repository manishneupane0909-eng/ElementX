import { useId } from 'react'
import type { ReactNode } from 'react'
import Button from './Button'

interface FileUploadBarProps {
  label: string
  accept: string
  file: File | null
  onFileChange: (file: File | null) => void
  /** Primary action, shown after the file chooser. Omit for choose-and-go flows (e.g. CIF). */
  actionLabel?: string
  onAction?: () => void
  busy?: boolean
  chooseLabel?: string
  hint?: ReactNode
  /** Shown instead of the file name while there is no file. */
  emptyText?: string
}

/**
 * One compact row for choosing a file and running an action on it:
 * [label] [Choose file] filename [Action]. The native input stays in the tab order.
 */
export default function FileUploadBar({
  label,
  accept,
  file,
  onFileChange,
  actionLabel,
  onAction,
  busy = false,
  chooseLabel = 'Choose file',
  hint,
  emptyText = 'No file selected',
}: FileUploadBarProps) {
  const inputId = useId()
  const hintId = useId()
  return (
    <div className="upload-bar">
      <span className="upload-bar__label" id={`${inputId}-label`}>
        {label}
      </span>
      <div className="upload-bar__row">
        <input
          id={inputId}
          className="file-input"
          type="file"
          accept={accept}
          aria-labelledby={`${inputId}-label`}
          aria-describedby={hint ? hintId : undefined}
          disabled={busy}
          onChange={(event) => onFileChange(event.target.files?.[0] ?? null)}
        />
        <label htmlFor={inputId} className="secondary-btn upload-bar__choose">
          {chooseLabel}
        </label>
        <span className="upload-bar__name" title={file?.name}>
          {file ? file.name : emptyText}
        </span>
        {actionLabel && (
          <Button variant="primary" onClick={onAction} disabled={busy || !file}>
            {actionLabel}
          </Button>
        )}
      </div>
      {hint && (
        <p className="field-hint" id={hintId}>
          {hint}
        </p>
      )}
    </div>
  )
}

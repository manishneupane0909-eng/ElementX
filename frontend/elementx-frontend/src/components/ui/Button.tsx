import type { ButtonHTMLAttributes } from 'react'

type Variant = 'primary' | 'secondary' | 'link'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
}

const CLASS_BY_VARIANT: Record<Variant, string> = {
  primary: 'primary-btn',
  secondary: 'secondary-btn',
  link: 'link-btn',
}

/** Shared button. Defaults to type="button" so it never submits a form by accident. */
export default function Button({
  variant = 'secondary',
  type = 'button',
  className,
  ...rest
}: ButtonProps) {
  const classes = [CLASS_BY_VARIANT[variant], className].filter(Boolean).join(' ')
  return <button type={type} className={classes} {...rest} />
}

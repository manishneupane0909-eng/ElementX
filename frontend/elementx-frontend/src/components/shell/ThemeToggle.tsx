import { useTheme } from '../../theme/useTheme'
import { MoonIcon, SunIcon } from '../ui/Icons'

/** The text label is visually hidden by the collapsed-sidebar CSS; the accessible name is constant. */
export default function ThemeToggle() {
  const { theme, toggleTheme } = useTheme()
  const next = theme === 'dark' ? 'light' : 'dark'
  const label = `Switch to ${next} theme`

  return (
    <button
      type="button"
      className="shell-btn"
      onClick={toggleTheme}
      aria-label={label}
      title={label}
      data-theme-toggle
    >
      {theme === 'dark' ? <SunIcon /> : <MoonIcon />}
      <span className="shell-btn__label">
        {theme === 'dark' ? 'Light theme' : 'Dark theme'}
      </span>
    </button>
  )
}

import { createContext } from 'react'

export type Theme = 'dark' | 'light'

export const THEME_STORAGE_KEY = 'elementx.theme'
export const DEFAULT_THEME: Theme = 'dark'

export interface ThemeContextValue {
  theme: Theme
  setTheme: (theme: Theme) => void
  toggleTheme: () => void
}

export const ThemeContext = createContext<ThemeContextValue | null>(null)

export function isTheme(value: unknown): value is Theme {
  return value === 'dark' || value === 'light'
}

/** Stored preference, or dark. The OS colour scheme is intentionally not consulted. */
export function readStoredTheme(): Theme {
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY)
    return isTheme(stored) ? stored : DEFAULT_THEME
  } catch {
    return DEFAULT_THEME
  }
}

import type { ReactNode } from 'react'

/** Small stroke icons, drawn on a 16px grid with a 1.5px stroke. Decorative: always aria-hidden. */
function Icon({ children }: { children: ReactNode }) {
  return (
    <svg
      className="icon"
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  )
}

export const SamplesIcon = () => (
  <Icon>
    <path d="M6 2h4M6.75 2v4.3L3.1 12.2a1.2 1.2 0 0 0 1 1.8h7.8a1.2 1.2 0 0 0 1-1.8L9.25 6.3V2" />
  </Icon>
)

export const MagnetometryIcon = () => (
  <Icon>
    <path d="M2 11.5c3.2 0 4-1.2 5-3.5s1.8-4 7-4M14 4.5c-3.2 0-4 1.2-5 3.5s-1.8 4-7 4" />
  </Icon>
)

export const MaterialsIcon = () => (
  <Icon>
    <path d="M8 1.75l5.25 3v6L8 13.75l-5.25-3v-6z" />
    <path d="M8 7.75v6M2.75 4.75L8 7.75l5.25-3" />
  </Icon>
)

export const CopilotIcon = () => (
  <Icon>
    <path d="M2.5 3.25h11v7.5H7.4L4.5 13.25v-2.5h-2z" />
    <path d="M5.5 6.25h5M5.5 8.25h3" />
  </Icon>
)

export const SunIcon = () => (
  <Icon>
    <circle cx="8" cy="8" r="2.75" />
    <path d="M8 1.5v1.6M8 12.9v1.6M1.5 8h1.6M12.9 8h1.6M3.4 3.4l1.1 1.1M11.5 11.5l1.1 1.1M3.4 12.6l1.1-1.1M11.5 4.5l1.1-1.1" />
  </Icon>
)

export const MoonIcon = () => (
  <Icon>
    <path d="M13.25 9.4A5.5 5.5 0 0 1 6.6 2.75a5.5 5.5 0 1 0 6.65 6.65z" />
  </Icon>
)

export const LogoutIcon = () => (
  <Icon>
    <path d="M6.5 2.5h-3v11h3M10 5l3 3-3 3M13 8H6.5" />
  </Icon>
)

export const CollapseIcon = () => (
  <Icon>
    <path d="M2.5 2.75h11v10.5h-11zM6.25 2.75v10.5M10.75 6l-2 2 2 2" />
  </Icon>
)

export const ExpandIcon = () => (
  <Icon>
    <path d="M2.5 2.75h11v10.5h-11zM6.25 2.75v10.5M9 6l2 2-2 2" />
  </Icon>
)

export const MenuIcon = () => (
  <Icon>
    <path d="M2.5 4h11M2.5 8h11M2.5 12h11" />
  </Icon>
)

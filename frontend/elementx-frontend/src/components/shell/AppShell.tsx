import { useCallback, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { CollapseIcon, ExpandIcon, LogoutIcon, MenuIcon } from '../ui/Icons'
import ThemeToggle from './ThemeToggle'

export interface NavItem {
  id: string
  label: string
  icon: ReactNode
}

interface ShellUser {
  name: string
  email: string
}

interface AppShellProps {
  items: NavItem[]
  activeId: string
  onSelect: (id: string) => void
  user: ShellUser | null
  onSignOut: () => void
  children: ReactNode
}

const SIDEBAR_STORAGE_KEY = 'elementx.sidebar'

function readCollapsed(): boolean {
  try {
    return window.localStorage.getItem(SIDEBAR_STORAGE_KEY) === 'collapsed'
  } catch {
    return false
  }
}

function initialOf(user: ShellUser | null): string {
  const source = (user?.name || user?.email || '').trim()
  return source ? source[0].toUpperCase() : '?'
}

/**
 * Application frame: collapsible sidebar (navigation, identity, theme, log out) and a content
 * column. On narrow screens the sidebar becomes a drawer opened from the top bar.
 */
export default function AppShell({
  items,
  activeId,
  onSelect,
  user,
  onSignOut,
  children,
}: AppShellProps) {
  const [collapsed, setCollapsed] = useState<boolean>(readCollapsed)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const menuButtonRef = useRef<HTMLButtonElement | null>(null)
  const firstNavRef = useRef<HTMLButtonElement | null>(null)

  const toggleCollapsed = useCallback(() => {
    setCollapsed((current) => {
      const next = !current
      try {
        window.localStorage.setItem(SIDEBAR_STORAGE_KEY, next ? 'collapsed' : 'expanded')
      } catch {
        // Preference just won't persist.
      }
      return next
    })
  }, [])

  const closeDrawer = useCallback((returnFocus: boolean) => {
    setDrawerOpen(false)
    if (returnFocus) menuButtonRef.current?.focus()
  }, [])

  useEffect(() => {
    if (!drawerOpen) return
    firstNavRef.current?.focus()
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closeDrawer(true)
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [drawerOpen, closeDrawer])

  const active = items.find((item) => item.id === activeId)

  return (
    <div className="shell" data-collapsed={collapsed} data-drawer={drawerOpen}>
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>

      {drawerOpen && (
        <button
          type="button"
          className="shell__backdrop"
          aria-label="Close navigation"
          onClick={() => closeDrawer(true)}
        />
      )}

      <aside className="sidebar" id="app-sidebar" aria-label="Application">
        <div className="sidebar__head">
          <span className="sidebar__brand">
            <span className="sidebar__mark" aria-hidden="true">
              E
            </span>
            <span className="sidebar__wordmark">ElementX</span>
          </span>
          <button
            type="button"
            className="shell-btn shell-btn--icon sidebar__collapse"
            onClick={toggleCollapsed}
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            aria-expanded={!collapsed}
            aria-controls="app-sidebar"
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {collapsed ? <ExpandIcon /> : <CollapseIcon />}
          </button>
        </div>

        <nav className="sidebar__nav" aria-label="Workspace sections">
          <ul className="sidebar__list">
            {items.map((item, index) => (
              <li key={item.id}>
                <button
                  type="button"
                  ref={index === 0 ? firstNavRef : undefined}
                  className="nav-item"
                  aria-current={item.id === activeId ? 'page' : undefined}
                  title={item.label}
                  onClick={() => {
                    onSelect(item.id)
                    setDrawerOpen(false)
                  }}
                >
                  {item.icon}
                  <span className="nav-item__label">{item.label}</span>
                </button>
              </li>
            ))}
          </ul>
        </nav>

        <div className="sidebar__foot" role="group" aria-label="Account">
          <div
            className="sidebar__user"
            title={user ? `${user.name} (${user.email})` : undefined}
          >
            <span className="sidebar__initial" aria-hidden="true">
              {initialOf(user)}
            </span>
            <span className="sidebar__identity">
              <span className="sidebar__name">{user?.name}</span>
              <span className="sidebar__email">{user?.email}</span>
            </span>
          </div>
          <ThemeToggle />
          <button type="button" className="shell-btn" onClick={onSignOut} title="Log out">
            <LogoutIcon />
            <span className="shell-btn__label">Log out</span>
          </button>
        </div>
      </aside>

      <div className="shell__main">
        <header className="topbar">
          <button
            type="button"
            ref={menuButtonRef}
            className="shell-btn shell-btn--icon topbar__menu"
            onClick={() => setDrawerOpen(true)}
            aria-label="Open navigation"
            aria-expanded={drawerOpen}
            aria-controls="app-sidebar"
          >
            <MenuIcon />
          </button>
          <h1 className="topbar__title">{active?.label}</h1>
        </header>
        <main id="main-content" className="app-main" tabIndex={-1}>
          {children}
        </main>
      </div>
    </div>
  )
}

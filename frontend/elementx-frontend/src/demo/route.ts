import { useEffect, useState } from 'react'

/**
 * Hash routes of the static demo. A hash needs no server-side rewrite rule, so direct links
 * (`/#about`, `/#explore`) and the browser's back and forward buttons work on any static host.
 *
 *   (no hash) or `#`  landing page
 *   `#about`          About ElementX
 *   `#explore`        read-only workspace
 */
export type DemoRoute = 'landing' | 'about' | 'explore'

export const ROUTE_HASH: Record<DemoRoute, string> = {
  landing: '#',
  about: '#about',
  explore: '#explore',
}

export function parseRoute(hash: string): DemoRoute {
  if (hash === '#explore') return 'explore'
  if (hash === '#about') return 'about'
  return 'landing'
}

export const ROUTE_TITLE: Record<DemoRoute, string> = {
  landing: 'ElementX: Portfolio demo',
  about: 'About ElementX: Portfolio demo',
  explore: 'ElementX: Portfolio demo',
}

/** Current route, kept in step with the address bar and the history buttons. */
export function useDemoRoute(): DemoRoute {
  const [route, setRoute] = useState<DemoRoute>(() => parseRoute(window.location.hash))

  useEffect(() => {
    const sync = () => setRoute(parseRoute(window.location.hash))
    window.addEventListener('hashchange', sync)
    window.addEventListener('popstate', sync)
    return () => {
      window.removeEventListener('hashchange', sync)
      window.removeEventListener('popstate', sync)
    }
  }, [])

  return route
}

/** Programmatic navigation. Adds a history entry so the back button returns to the previous page. */
export function navigateTo(route: DemoRoute): void {
  window.location.hash = ROUTE_HASH[route]
}

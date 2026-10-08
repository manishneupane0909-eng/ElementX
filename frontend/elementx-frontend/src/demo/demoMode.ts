/**
 * Portfolio-demo switch.
 *
 * With `VITE_DEMO_MODE=true` the app is a static, read-only showcase: it needs no backend, no
 * account and no API keys, and shows snapshots of what the real ElementX backend produced for
 * two bundled example files. With the flag off (the default) none of this code runs.
 */
export const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === 'true'

/** Public source repository, shown on the demo landing page. */
export const REPOSITORY_URL = 'https://github.com/manishneupane0909-eng/ElementX'

export class DemoDisabledError extends Error {
  constructor(what: string) {
    super(`${what} is not available in the portfolio demo. Example records are read-only.`)
    this.name = 'DemoDisabledError'
  }
}

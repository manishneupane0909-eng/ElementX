import ThemeToggle from '../components/shell/ThemeToggle'
import Button from '../components/ui/Button'
import BrandMark from '../components/ui/BrandMark'
import { ROUTE_HASH } from './route'
import ScheduleLink from './ScheduleLink'
import SiteFooter from './SiteFooter'

interface DemoLandingProps {
  onEnter: () => void
}

/** Entry page of the public demo. No sign-in: Explore Demo opens the read-only workspace. */
export default function DemoLanding({ onEnter }: DemoLandingProps) {
  return (
    <div className="auth-shell demo-landing">
      <div className="auth-theme">
        <ThemeToggle />
      </div>
      <main className="demo-landing__main" id="main-content" tabIndex={-1}>
        <p className="demo-landing__brand">
          <BrandMark size={28} />
        </p>
        <p>
          <span className="demo-tag">Public demo</span>
        </p>
        <h1 className="demo-landing__title">Fabrivium</h1>
        <p className="demo-landing__tagline">From experimental data to materials discovery.</p>
        <p className="demo-landing__lede">
          Scientific software built to simplify experimental analysis today and accelerate materials
          discovery tomorrow.
        </p>
        <p className="demo-landing__actions">
          <Button variant="primary" onClick={onEnter} autoFocus>
            Explore Demo
          </Button>
          <ScheduleLink className="schedule-link--button" />
          <a className="secondary-btn demo-landing__about" href={ROUTE_HASH.about}>
            About Fabrivium
          </a>
        </p>

        <div className="demo-landing__cols">
          <section aria-labelledby="demo-today">
            <h2 id="demo-today">What works today</h2>
            <ul>
              <li>Quantum Design magnetometry analysis of instrument files</li>
              <li>Interactive M-H and M-T plots, with zoom, loop switching and CSV/SVG export</li>
              <li>Coercivity and remanence from the original sweep order</li>
              <li>XRD visualization and candidate intensity maxima</li>
              <li>
                Research sample and experiment organization in the complete application; this demo
                shows two read-only examples
              </li>
            </ul>
            <p className="demo-landing__small">
              This demo is read-only. Every number comes from the analysis pipeline; the browser
              only displays it. Nothing is uploaded or saved.
            </p>
          </section>
          <section aria-labelledby="demo-next">
            <h2 id="demo-next">What comes next</h2>
            <ul>
              <li>
                The long-term goal is AI-assisted materials discovery: predictive modeling, active
                learning, and experimental validation.
              </li>
              <li>
                That is a direction, not a shipped feature. No language model, paid plan, or
                discovery engine runs here.
              </li>
            </ul>
            <p className="demo-landing__small">
              Sign-in, uploads, live Materials Project queries and live Copilot are switched off in
              this demo.
            </p>
          </section>
        </div>
      </main>
      <SiteFooter />
    </div>
  )
}

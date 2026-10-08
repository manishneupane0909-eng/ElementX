import ThemeToggle from '../components/shell/ThemeToggle'
import Button from '../components/ui/Button'
import { REPOSITORY_URL } from './demoMode'

interface DemoLandingProps {
  onEnter: () => void
}

/** Entry page of the portfolio demo. No sign-in: one button opens the read-only workspace. */
export default function DemoLanding({ onEnter }: DemoLandingProps) {
  return (
    <div className="auth-shell demo-landing">
      <div className="auth-theme">
        <ThemeToggle />
      </div>
      <main className="demo-landing__main" id="main-content">
        <p className="auth-brand">ElementX</p>
        <p>
          <span className="demo-tag">Portfolio demo</span>
        </p>
        <h1 className="demo-landing__title">
          Magnetometry and XRD analysis for magnetic-materials research
        </h1>
        <p className="demo-landing__lede">
          ElementX reads instrument files, runs a documented analysis pipeline on a backend, and
          stores the results with their provenance. This demo shows stored results from that
          pipeline for two example files. It needs no account and no server connection.
        </p>
        <p>
          <Button variant="primary" onClick={onEnter} autoFocus>
            Explore Demo
          </Button>
        </p>

        <div className="demo-landing__cols">
          <section aria-labelledby="demo-inside">
            <h2 id="demo-inside">What you can explore</h2>
            <ul>
              <li>
                A <strong>real</strong> Fe2CoGe VSM measurement: ten M-H loops and an M-T sweep,
                with zoom, loop switching and CSV/SVG export.
              </li>
              <li>
                A <strong>synthetic</strong> XRD test pattern, clearly labelled as not a laboratory
                measurement.
              </li>
              <li>Reference data for example magnets from the Materials Project (CC BY 4.0).</li>
              <li>Recorded “stored-record” Copilot readouts. No language model is running.</li>
            </ul>
          </section>
          <section aria-labelledby="demo-limits">
            <h2 id="demo-limits">What is switched off</h2>
            <ul>
              <li>Sign-in and registration</li>
              <li>Creating or saving samples, and file uploads</li>
              <li>Live AI (Gemini) and any server calls</li>
            </ul>
            <p className="demo-landing__small">
              Example records are read-only. Every number comes from the ElementX backend pipeline;
              the browser only displays it.
            </p>
          </section>
        </div>

        <p className="demo-landing__small">
          <a href={REPOSITORY_URL} target="_blank" rel="noopener noreferrer">
            Source code and documentation on GitHub
          </a>
        </p>
      </main>
    </div>
  )
}

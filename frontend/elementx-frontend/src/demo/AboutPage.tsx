import ThemeToggle from '../components/shell/ThemeToggle'
import BrandMark from '../components/ui/BrandMark'
import { ROUTE_HASH } from './route'
import ScheduleLink from './ScheduleLink'
import SiteFooter from './SiteFooter'

interface CapabilityRow {
  name: string
  full: string
  demo: string
}

/**
 * Every row separates what the complete application does from what this static demo shows.
 * Keep the wording in line with the README and docs/DEMO.md.
 */
const CAPABILITIES: CapabilityRow[] = [
  {
    name: 'Quantum Design magnetometry analysis',
    full: 'Upload a .dat file; the Python backend parses and analyses it.',
    demo: 'One real measurement, shown from stored backend results.',
  },
  {
    name: 'M-H and M-T plots',
    full: 'Interactive plots of your own uploaded data.',
    demo: 'Interactive plots of that stored measurement, with zoom, loop switching and CSV/SVG export.',
  },
  {
    name: 'Coercivity and remanence',
    full: 'Calculated on upload from the original sweep order.',
    demo: 'Stored values for the example measurement.',
  },
  {
    name: 'Sample-mass provenance and normalization',
    full: 'Every candidate mass is kept with its source; normalization is blocked when sources disagree.',
    demo: 'Shown for the example measurement.',
  },
  {
    name: 'XRD visualization and candidate intensity maxima',
    full: 'Upload a two-column pattern; local maxima are detected and listed.',
    demo: 'One synthetic test pattern, labelled as not a laboratory measurement.',
  },
  {
    name: 'Sample and experiment organization',
    full: 'Accounts, saved samples and experiments, re-opened later.',
    demo: 'Not available. Two read-only example samples.',
  },
  {
    name: 'Materials Project integration',
    full: 'Live formula lookup. Needs a Materials Project API key.',
    demo: 'Four curated entries. No live queries.',
  },
  {
    name: 'Physics Copilot',
    full: 'Answers grounded in your stored records. A language model is optional.',
    demo: 'Recorded readouts of stored values. No language model runs and there is no free-text box.',
  },
]

/**
 * About page of the public demo. It is a plain reading page: no sign-in, no network calls.
 * Navigation uses real links so the address bar, back button and direct URLs all work.
 */
export default function AboutPage() {
  return (
    <div className="about">
      <header className="about__bar">
        <a className="about__brand" href={ROUTE_HASH.landing}>
          <BrandMark size={22} />
          Fabrivium
        </a>
        <nav className="about__nav" aria-label="Site">
          <ul>
            <li>
              <a href={ROUTE_HASH.landing}>Home</a>
            </li>
            <li>
              <a href={ROUTE_HASH.about} aria-current="page">
                About
              </a>
            </li>
            <li>
              <a href={ROUTE_HASH.explore}>Explore Demo</a>
            </li>
            <li>
              <ScheduleLink />
            </li>
          </ul>
        </nav>
        <ThemeToggle />
      </header>

      <main className="about__main" id="main-content" tabIndex={-1}>
        <p>
          <span className="demo-tag">Early-stage project</span>
        </p>
        <h1 className="about__title">About Fabrivium</h1>
        <p className="about__lede">
          Fabrivium is a scientific computing platform that automates experimental data analysis
          and helps materials researchers organize, visualize, and understand their measurements.
        </p>
        <p>
          It is an early-stage prototype and a possible startup direction, not an established
          company. There are no customers, paid plans or commercial service today.
        </p>

        <section aria-labelledby="about-why">
          <h2 id="about-why">Why I built it</h2>
          <p>
            Fabrivium grew out of four years of undergraduate research on rare-earth-free permanent
            magnets, primarily MnBi and MnAl.
          </p>
          <p>
            The work meant repetitive analysis, disconnected instrument files, and too much time
            spent reconstructing how a number was obtained. I wanted a reproducible scientific
            workflow: read the measurement, run a documented pipeline, and keep the provenance with
            the result.
          </p>
          <p className="about__byline">
            Manish Neupane · <a href="https://mneupane.com">mneupane.com</a>
          </p>
        </section>

        <section aria-labelledby="about-today">
          <h2 id="about-today">What works today</h2>
          <p>
            Fabrivium exists in two forms. The <strong>complete application</strong> is a FastAPI
            and Python backend with a React and TypeScript frontend, and it is where uploads,
            accounts and saved records live. This <strong>public demo</strong> is read-only: it
            shows stored results that the backend produced from two example files, and it makes no
            server calls.
          </p>
          <ul className="about__caps" aria-label="Capabilities in the complete application and in the public demo">
            {CAPABILITIES.map((row) => (
              <li key={row.name} className="about__cap">
                <h3 className="about__cap-name">{row.name}</h3>
                <dl className="about__cap-where">
                  <div>
                    <dt>Complete application</dt>
                    <dd>{row.full}</dd>
                  </div>
                  <div>
                    <dt>Public demo</dt>
                    <dd>{row.demo}</dd>
                  </div>
                </dl>
              </li>
            ))}
          </ul>
          <p className="about__note">
            The magnetometry record in the demo is a real measurement of an Fe2CoGe sample. The XRD
            pattern is a synthetic software test pattern and is labelled as one. Copilot replies in
            the demo are recorded readouts, not live responses from a language model.
          </p>
        </section>

        <section aria-labelledby="about-next">
          <h2 id="about-next">What comes next</h2>
          <p>
            The long-term vision is AI-assisted materials discovery through predictive modeling,
            active learning, and experimental validation.
          </p>
          <p>
            That is a future goal, not a feature that exists today. Nothing beyond the capabilities
            above is shipped. Feedback from researchers on what would actually save them time will
            shape what gets built.
          </p>
        </section>

        <section aria-labelledby="about-connect">
          <h2 id="about-connect">Connect</h2>
          <p>
            If you are a materials researcher, a scientific software engineer, a potential
            collaborator, or a mentor, I would like to hear from you.
          </p>
          <p className="about__actions">
            <ScheduleLink className="schedule-link--button" />
            <a className="secondary-btn about__cta" href={ROUTE_HASH.explore}>
              Explore Demo
            </a>
          </p>
        </section>
      </main>
      <SiteFooter />
    </div>
  )
}

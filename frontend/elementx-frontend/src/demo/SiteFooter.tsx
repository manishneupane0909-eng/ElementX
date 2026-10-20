import { ROUTE_HASH } from './route'
import ScheduleLink from './ScheduleLink'

/** Compact footer for the public demo pages. */
export default function SiteFooter() {
  return (
    <footer className="site-footer">
      <p className="site-footer__brand">
        Fabrivium
        <span className="site-footer__tag">From experimental data to materials discovery.</span>
      </p>
      <nav aria-label="Footer">
        <ul className="site-footer__nav">
          <li>
            <a href={ROUTE_HASH.landing}>Home</a>
          </li>
          <li>
            <a href={ROUTE_HASH.about}>About</a>
          </li>
          <li>
            <a href={ROUTE_HASH.explore}>Explore Demo</a>
          </li>
          <li>
            <ScheduleLink />
          </li>
        </ul>
      </nav>
    </footer>
  )
}

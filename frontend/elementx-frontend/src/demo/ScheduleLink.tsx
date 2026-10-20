import { CalendarIcon } from '../components/ui/Icons'
import { SCHEDULE_PATH } from './schedule'

interface ScheduleLinkProps {
  className?: string
}

/**
 * Booking link used on the public pages. Points at the public /schedule path, not at
 * Calendly directly, so the address people copy stays on this site.
 */
export default function ScheduleLink({ className }: ScheduleLinkProps) {
  const classes = ['schedule-link', className].filter(Boolean).join(' ')
  return (
    <a className={classes} href={SCHEDULE_PATH}>
      <CalendarIcon />
      Schedule a Conversation
    </a>
  )
}

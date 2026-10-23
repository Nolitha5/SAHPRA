import type { QAStatus } from '../types'

interface Props {
  status: QAStatus | null
}

const LABELS: Record<QAStatus, string> = {
  PASS: 'PASS',
  FLAG: 'FLAG',
  ESCALATE: 'ESCALATE',
}

export default function QAStatusBadge({ status }: Props) {
  if (!status) {
    return <span className="badge badge--pending">Pending QA</span>
  }
  return (
    <span className={`badge badge--${status.toLowerCase()}`}>
      {LABELS[status]}
    </span>
  )
}

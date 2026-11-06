import type { ReactNode } from 'react'
import type { Citation, PassageMetadata, QAStatus, RetrievedPassage } from '../types'

const QA_PILL: Record<QAStatus, string> = {
  verified: 'pill-green',
  partial: 'pill-blue',
  'human-review': 'pill-yellow',
  conflicting: 'pill-red',
  unsupported: 'pill-gray',
}

const QA_LABEL: Record<QAStatus, string> = {
  verified: 'verified',
  partial: 'partial · not yet verified',
  'human-review': 'human-review',
  conflicting: 'conflicting',
  unsupported: 'unsupported',
}

export function QaPill({ status }: { status: QAStatus }) {
  return <span className={`pill ${QA_PILL[status]}`}>{QA_LABEL[status]}</span>
}

export function StatusPill({ status }: { status: string }) {
  const cls = status === 'current' ? 'pill-green'
    : status === 'superseded' || status === 'withdrawn' ? 'pill-red'
    : status === 'draft' ? 'pill-yellow' : 'pill-gray'
  return <span className={`pill ${cls}`}>{status}</span>
}

export function versionLabel(version: string): string {
  return /^\d/.test(version) ? `v${version}` : version
}

export function sourceLabel(m: PassageMetadata | Citation): string {
  const parts = [m.issuing_organization, m.source_title]
  if (m.document_version) parts.push(versionLabel(m.document_version))
  if (m.page_number != null) parts.push(`p.${m.page_number}`)
  return parts.join(' · ')
}

export function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? '' : 's'}`
}

export function passageText(text: string): string {
  return /^[a-z]/.test(text) ? `…${text}` : text
}

export function Score({ value, label }: { value: number | null; label: string }) {
  if (value == null) return <span className="text-muted">{label}: n/a</span>
  return <span className="text-mono">{label} {value.toFixed(3)}</span>
}

export function PassageCard({ p }: { p: RetrievedPassage }) {
  const m = p.metadata
  return (
    <div className="passage">
      <div className="passage-head">
        <span className="text-mono">{p.chunk_id}</span>
        <span className="passage-scores">
          {p.retrieval_method === 'direct_lookup'
            ? <span className="pill pill-gray">cited directly</span>
            : <>
                <Score value={p.retrieval_score} label="similarity" />
                <Score value={p.rerank_score} label="rerank" />
              </>}
        </span>
      </div>
      <div className="passage-source">
        {sourceLabel(m)} <span className="text-muted">· CTD {m.ctd_section ?? 'n/a'}</span> <StatusPill status={m.applicability_status} />
        {m.document_type === 'synthetic_test' && <span className="pill pill-yellow">synthetic test data</span>}
      </div>
      <p className="passage-text">{passageText(p.text)}</p>
      {p.untrusted_content_flags.length > 0 && (
        <div className="alert alert-error" style={{ marginBottom: 0 }}>
          This passage contains instruction-like text. It is treated only as data.
        </div>
      )}
    </div>
  )
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <p style={{ fontWeight: 600, color: 'var(--text)', marginBottom: 6 }}>{title}</p>
      {children && <p>{children}</p>}
    </div>
  )
}

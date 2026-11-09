import { useEffect, useState } from 'react'
import { api } from '../api'
import type { Coverage } from '../types'
import { Empty, StatusPill, versionLabel } from './shared'

function pageRange(first: number | null, last: number | null): string {
  if (first == null) return 'n/a'
  return first === last ? `p. ${first}` : `pp. ${first}–${last}`
}

/** Overview of the knowledge base: sources, gaps and CTD coverage. `version` changes after imports/deletes. */
export default function CoveragePage({ version = 0 }: { version?: number }) {
  const [data, setData] = useState<Coverage | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.coverage().then(d => { setData(d); setError('') }).catch(e => setError((e as Error).message))
  }, [version])

  if (error) return <div className="alert alert-error">{error}</div>
  if (!data) return <div className="empty"><span className="spinner" /></div>
  if (data.total_passages === 0) {
    return (
      <Empty title="The knowledge base is empty">
        Build it with <code>python scripts/build_knowledge_base.py</code> in the member2-rag folder.
      </Empty>
    )
  }

  const maxReach = Math.max(1, ...data.s_sections.map(s => s.reachable))
  const gaps = data.s_sections.filter(s => s.direct === 0).map(s => s.section)

  return (
    <div className="stack">
      <div className="stats">
        <div className="stat"><div className="stat-value">{data.total_passages}</div><div className="stat-label">Passages in {data.collection}</div></div>
        <div className="stat">
          <div className="stat-value">{data.source_count}{data.expected_count > 0 && <span className="stat-of"> / {data.expected_count}</span>}</div>
          <div className="stat-label">Sources indexed{data.expected_count > 0 && ' / expected'}</div>
        </div>
        <div className="stat"><div className="stat-value">{data.missing_sources.length}</div><div className="stat-label">Expected sources missing</div></div>
        <div className="stat"><div className="stat-value">{gaps.length}</div><div className="stat-label">3.2.S headings with no direct sources</div></div>
      </div>

      {data.missing_sources.length > 0 && (
        <div className="alert alert-error" style={{ marginBottom: 0 }}>
          <b>Not indexed:</b> {data.missing_sources.map(m => `${m.issuing_organization} ${m.source_identifier}${m.document_version ? ` (${m.document_version})` : ''}`).join('; ')}.
          Listed in <code>{data.manifest}</code> but not found in the knowledge base.
        </div>
      )}

      <div className="card">
        <div className="card-header"><span className="card-title">Sources</span><span className="text-muted">Expected list: {data.manifest}</span></div>
        <div className="card-body">
          <div className="table-wrap">
            <table className="doc-table table-stack">
              <thead>
                <tr><th>Source</th><th>Version · date</th><th>Status</th><th className="num">Passages</th><th>PDF pages</th><th>CTD tags</th><th>Official PDF</th></tr>
              </thead>
              <tbody>
                {data.sources.map(s => (
                  <tr key={`${s.issuing_organization}|${s.source_identifier}|${s.document_version}`}>
                    <td data-label="Source">
                      <b>{s.issuing_organization}</b> · {s.source_identifier}
                      <div className="text-muted" style={{ fontSize: 12 }}>{s.source_title}</div>
                      {!s.in_manifest && data.expected_count > 0 && <span className="pill pill-yellow">not in expected list</span>}
                    </td>
                    <td data-label="Version">{[s.document_version ? versionLabel(s.document_version) : null, s.publication_date].filter(Boolean).join(' · ') || 'n/a'}</td>
                    <td data-label="Status"><StatusPill status={s.applicability_status} /></td>
                    <td className="num" data-label="Passages">{s.passages}</td>
                    <td data-label="Pages">{pageRange(s.first_page, s.last_page)}</td>
                    <td data-label="CTD tags">
                      {Object.entries(s.ctd_sections).map(([sec, n]) => <div key={sec} className="text-mono">{sec} <span className="text-muted">×{n}</span></div>)}
                    </td>
                    <td data-label="PDF">{s.url ? <a href={s.url} target="_blank" rel="noreferrer noopener">Open</a> : <span className="text-muted">n/a</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-header"><span className="card-title">CTD Module 3.2.S coverage</span></div>
        <div className="card-body stack">
          <p className="text-muted" style={{ fontSize: 13 }}>
            <b>Tagged</b>: passages tagged with the heading or one of its subsections.
            <b> Reachable</b>: what a search filtered to that heading sees, which also includes general passages tagged
            with a parent heading (3.2.S or 3.2). A heading with nothing tagged relies only on general guidance.
          </p>
          <div className="table-wrap">
            <table className="doc-table table-stack">
              <thead><tr><th>Section</th><th>Heading</th><th className="num">Tagged</th><th className="num">Reachable</th><th style={{ width: '30%' }}>Coverage</th></tr></thead>
              <tbody>
                {data.s_sections.map(s => (
                  <tr key={s.section}>
                    <td className="text-mono" data-label="Section">{s.section}</td>
                    <td data-label="Heading">{s.label}</td>
                    <td className="num" data-label="Tagged">{s.direct === 0 ? <span className="pill pill-yellow">gap</span> : s.direct}</td>
                    <td className="num" data-label="Reachable">{s.reachable}</td>
                    <td data-label="Coverage">
                      <div className="bar"><div className="bar-direct" style={{ width: `${(100 * s.direct) / maxReach}%` }} />
                        <div className="bar-inherited" style={{ width: `${(100 * (s.reachable - s.direct)) / maxReach}%` }} /></div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="bar-legend"><span><i className="bar-direct" /> tagged</span><span><i className="bar-inherited" /> from parent headings</span></div>
        </div>
      </div>
    </div>
  )
}

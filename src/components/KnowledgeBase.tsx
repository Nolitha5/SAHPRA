import { Fragment, useCallback, useEffect, useRef, useState } from 'react'
import { api, CTD_SECTIONS, DOCUMENT_TYPES } from '../api'
import type { Facets, ImportReport, StoredPassage } from '../types'
import { Empty, StatusPill, passageText, sourceLabel, versionLabel } from './shared'

const PAGE = 25

function shortSource(p: StoredPassage): string {
  const m = p.metadata
  const parts = [m.source_identifier]
  if (m.document_version) parts.push(versionLabel(m.document_version))
  if (m.page_number != null) parts.push(`p.${m.page_number}`)
  if (m.chunk_index != null) parts.push(`chunk ${m.chunk_index + 1}`)
  return parts.join(' · ')
}

export default function KnowledgeBase({ canEdit, onChanged }: { canEdit: boolean; onChanged: () => void }) {
  const [items, setItems] = useState<StoredPassage[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [filter, setFilter] = useState({ ctd_section: '', organization: '', document_type: '' })
  const [facets, setFacets] = useState<Facets | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [expanded, setExpanded] = useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [page, f] = await Promise.all([api.passages({ ...filter, limit: PAGE, offset }), api.facets()])
      setItems(page.items)
      setTotal(page.total)
      setFacets(f)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [filter, offset])

  useEffect(() => { load() }, [load])

  async function remove(chunkId: string) {
    setError('')
    try {
      await api.deletePassage(chunkId)
      setConfirmDelete(null)
      await load()
      onChanged()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const orgs = Object.keys(facets?.issuing_organization ?? {})

  return (
    <div>
      {canEdit && <ImportPanel onDone={() => { setOffset(0); load(); onChanged() }} />}

      <div className="card">
        <div className="card-header">
          <span className="card-title">Stored passages</span>
          <div className="row-actions filters">
            <label className="sr-only" htmlFor="kb-ctd">CTD section</label>
            <select id="kb-ctd" value={filter.ctd_section} onChange={e => { setOffset(0); setFilter({ ...filter, ctd_section: e.target.value }) }}>
              <option value="">All CTD sections</option>
              {CTD_SECTIONS.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
            <label className="sr-only" htmlFor="kb-org">Organisation</label>
            <select id="kb-org" value={filter.organization} onChange={e => { setOffset(0); setFilter({ ...filter, organization: e.target.value }) }}>
              <option value="">All organisations</option>
              {orgs.map(o => <option key={o} value={o}>{o}</option>)}
            </select>
            <label className="sr-only" htmlFor="kb-type">Document type</label>
            <select id="kb-type" value={filter.document_type} onChange={e => { setOffset(0); setFilter({ ...filter, document_type: e.target.value }) }}>
              <option value="">All document types</option>
              {DOCUMENT_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
        </div>

        {error && <div className="alert alert-error" style={{ margin: 16 }}>{error}</div>}

        {loading ? (
          <div className="empty"><span className="spinner" /></div>
        ) : items.length === 0 ? (
          <Empty title={total === 0 && !filter.ctd_section && !filter.organization && !filter.document_type ? 'No passages loaded yet' : 'No passages match these filters'}>
            {canEdit ? 'Use the import panel above to add source material.' : 'No passages are available in the current knowledge base.'}
          </Empty>
        ) : (
          <div className="table-wrap">
            <table className="table-stack">
              <thead>
                <tr><th>Source</th><th>CTD</th><th>Type</th><th>Status</th><th>Provenance</th><th /></tr>
              </thead>
              <tbody>
                {items.map(p => (
                  <Fragment key={p.chunk_id}>
                    <tr>
                      <td>
                        <div className="kb-source">{shortSource(p)}</div>
                        <div className="kb-title text-muted" title={sourceLabel(p.metadata)}>{p.metadata.source_title}</div>
                      </td>
                      <td data-label="CTD">{p.metadata.ctd_section ?? <span className="text-muted">n/a</span>}</td>
                      <td data-label="Type">{p.metadata.document_type === 'synthetic_test' ? <span className="pill pill-yellow">synthetic</span> : p.metadata.document_type}</td>
                      <td data-label="Status"><StatusPill status={p.metadata.applicability_status} /></td>
                      <td data-label="Provenance">{p.provenance_complete
                        ? <span className="pill pill-green">complete</span>
                        : <span className="pill pill-yellow" title={p.missing_provenance.join(', ')}>missing {p.missing_provenance.length}</span>}</td>
                      <td><div className="row-actions">
                        <button className="btn btn-ghost" onClick={() => setExpanded(expanded === p.chunk_id ? null : p.chunk_id)}>
                          {expanded === p.chunk_id ? 'Hide text' : 'Show text'}
                        </button>
                        {canEdit && (confirmDelete === p.chunk_id ? (
                          <>
                            <button className="btn btn-danger" onClick={() => remove(p.chunk_id)}>Confirm delete</button>
                            <button className="btn btn-ghost" onClick={() => setConfirmDelete(null)}>Keep</button>
                          </>
                        ) : (
                          <button className="btn btn-ghost" onClick={() => setConfirmDelete(p.chunk_id)}>Delete</button>
                        ))}
                      </div></td>
                    </tr>
                    {expanded === p.chunk_id && (
                      <tr className="expanded-row">
                        <td colSpan={6}>
                          <p className="text-muted" style={{ marginBottom: 6 }}>{sourceLabel(p.metadata)}</p>
                          <p className="passage-text">{passageText(p.text)}</p>
                          {!p.provenance_complete && (
                            <p className="text-muted">Missing: {p.missing_provenance.join(', ')}. Citations from this passage will be marked incomplete.</p>
                          )}
                          <p className="text-muted text-mono" style={{ marginTop: 6, overflowWrap: 'anywhere' }}>
                            {p.chunk_id} · sha256 {p.metadata.content_hash}
                          </p>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {total > PAGE && (
          <div className="pager">
            <button className="btn btn-ghost" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Previous</button>
            <span className="text-muted">{offset + 1}–{Math.min(offset + PAGE, total)} of {total}</span>
            <button className="btn btn-ghost" disabled={offset + PAGE >= total} onClick={() => setOffset(offset + PAGE)}>Next</button>
          </div>
        )}
      </div>
    </div>
  )
}

function ImportPanel({ onDone }: { onDone: () => void }) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<{ name: string; content: string } | null>(null)
  const [report, setReport] = useState<ImportReport | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function pick(f: File | undefined) {
    setReport(null)
    setError('')
    if (!f) { setFile(null); return }
    setFile({ name: f.name, content: await f.text() })
  }

  async function run(dryRun: boolean) {
    if (!file) return
    setBusy(true)
    setError('')
    try {
      const r = await api.importPassages(file.name, file.content, dryRun)
      setReport(r)
      if (!dryRun) onDone()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="card section-gap">
      <div className="card-header"><span className="card-title">Import passages</span></div>
      <div className="card-body">
        <div className="row-actions" style={{ flexWrap: 'wrap' }}>
          <input id="kb-import-file" ref={fileRef} type="file" accept=".jsonl,.ndjson" onChange={e => pick(e.target.files?.[0])} />
          <button className="btn btn-ghost" disabled={!file || busy} onClick={() => run(true)}>Check file</button>
          <button className="btn btn-primary" disabled={!file || busy} onClick={() => run(false)}>{busy ? 'Working…' : 'Import'}</button>
        </div>
        {error && <div className="alert alert-error" style={{ marginTop: 12 }}>{error}</div>}
        {report && (
          <div className={`alert ${report.rejected ? 'alert-error' : 'alert-success'}`} style={{ marginTop: 12 }}>
            <b>{report.dry_run ? 'Check complete' : 'Import complete'}:</b> {report.valid_records} valid, {report.rejected} rejected
            {!report.dry_run && <>, {report.added} added, {report.updated} updated, {report.unchanged} unchanged</>}
            {report.skipped_duplicates > 0 && <>, {report.skipped_duplicates} duplicate lines skipped</>}.
            {report.rejected_details.length > 0 && (
              <ul style={{ margin: '8px 0 0 18px' }}>
                {report.rejected_details.slice(0, 10).map(r => (
                  <li key={`${r.line_number}-${r.chunk_id}`}>Line {r.line_number}{r.chunk_id ? ` (${r.chunk_id})` : ''}: {r.message}</li>
                ))}
                {report.rejected_details.length > 10 && <li>…and {report.rejected_details.length - 10} more</li>}
              </ul>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

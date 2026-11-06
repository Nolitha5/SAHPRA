import type { FormEvent } from 'react'
import { useState } from 'react'
import { api, CTD_SECTIONS } from '../api'
import type { RetrievalResult, SearchFilters } from '../types'
import { downloadSearchReport } from '../wordExport'
import WordToolbar from './WordToolbar'
import { Empty, PassageCard, StatusPill, versionLabel } from './shared'

const score = (v: number | null) => (v == null ? 'n/a' : v.toFixed(3))

export default function SearchPanel() {
  const [query, setQuery] = useState('')
  const [section, setSection] = useState('')
  const [parents, setParents] = useState(true)
  const [currentOnly, setCurrentOnly] = useState(false)
  const [rerank, setRerank] = useState(true)
  const [finalK, setFinalK] = useState(5)
  const [result, setResult] = useState<RetrievalResult | null>(null)
  const [asked, setAsked] = useState<{ query: string; filters: SearchFilters } | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function run(e: FormEvent) {
    e.preventDefault()
    if (!query.trim()) { setError('Type a question to search for.'); return }
    setBusy(true)
    setError('')
    const filters: SearchFilters = {
      ctd_sections: section ? [section] : [],
      include_parent_sections: parents,
      applicability_statuses: currentOnly ? ['current'] : [],
    }
    try {
      const r = await api.search(query, filters, finalK, rerank)
      setResult(r)
      setAsked({ query: query.trim(), filters })
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <form className="card section-gap" onSubmit={run}>
        <div className="card-body form-grid">
          <div className="form-group form-full">
            <label htmlFor="search-query">Question</label>
            <textarea id="search-query" value={query} onChange={e => setQuery(e.target.value)}
              placeholder="Ask a question about the knowledge base" />
          </div>
          <div className="form-group">
            <label htmlFor="search-section">CTD section</label>
            <select id="search-section" value={section} onChange={e => setSection(e.target.value)}>
              <option value="">Any section</option>
              {CTD_SECTIONS.map(s => <option key={s} value={s}>{s} and subsections</option>)}
            </select>
          </div>
          <div className="form-group">
            <label htmlFor="search-k">Passages to return</label>
            <select id="search-k" value={finalK} onChange={e => setFinalK(Number(e.target.value))}>
              {[3, 5, 10].map(k => <option key={k} value={k}>{k}</option>)}
            </select>
          </div>
          <div className="checks form-full">
            <label className="check"><input id="search-parents" type="checkbox" checked={parents} onChange={e => setParents(e.target.checked)} /> Include parent headings</label>
            <label className="check"><input id="search-current" type="checkbox" checked={currentOnly} onChange={e => setCurrentOnly(e.target.checked)} /> Current sources only</label>
            <label className="check"><input id="search-rerank" type="checkbox" checked={rerank} onChange={e => setRerank(e.target.checked)} /> Rerank results</label>
          </div>
          <div className="form-full row-actions">
            <button className="btn btn-primary" type="submit" disabled={busy}>{busy ? 'Searching…' : 'Search'}</button>
          </div>
        </div>
      </form>

      {error && <div className="alert alert-error">{error}</div>}

      {result && asked && (
        <WordToolbar onDownload={() => downloadSearchReport(asked.query, asked.filters, result)} />
      )}

      {result && (
        <div className="card">
          <div className="card-header">
            <span className="card-title">{result.passages.length} passage(s)</span>
            <span className="text-muted">
              {result.candidates_considered} candidates · {result.reranked ? `reranked with ${result.reranker_model}` : 'not reranked'} · {result.latency_ms.toFixed(0)} ms
            </span>
          </div>
          <div className="card-body stack">
            {result.knowledge_base_size === 0
              ? <Empty title="The knowledge base is empty">Load passages first.</Empty>
              : result.passages.length === 0
                ? <Empty title="No passages matched">Try another section or switch off "Current sources only".</Empty>
                : (
                  <>
                    <div className="table-wrap">
                      <table className="doc-table table-stack">
                        <thead>
                          <tr><th className="num">#</th><th>Source</th><th className="num">Page</th><th>CTD</th><th>Status</th><th className="num">Similarity</th><th className="num">Rerank</th></tr>
                        </thead>
                        <tbody>
                          {result.passages.map((p, i) => (
                            <tr key={p.chunk_id}>
                              <td className="num" data-label="#">{i + 1}</td>
                              <td data-label="Source">
                                <b>{p.metadata.issuing_organization}</b> · {p.metadata.source_title}
                                <div className="text-muted" style={{ fontSize: 12 }}>
                                  {p.metadata.source_identifier}{p.metadata.document_version ? ` · ${versionLabel(p.metadata.document_version)}` : ''}
                                </div>
                              </td>
                              <td className="num" data-label="Page">{p.metadata.page_number ?? 'n/a'}</td>
                              <td data-label="CTD">{p.metadata.ctd_section ?? 'n/a'}</td>
                              <td data-label="Status"><StatusPill status={p.metadata.applicability_status} /></td>
                              <td className="num" data-label="Similarity">{score(p.retrieval_score)}</td>
                              <td className="num" data-label="Rerank">{score(p.rerank_score)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <details>
                      <summary>Show the passage text</summary>
                      <div className="stack" style={{ marginTop: 12 }}>
                        {result.passages.map(p => <PassageCard key={p.chunk_id} p={p} />)}
                      </div>
                    </details>
                  </>
                )}
          </div>
        </div>
      )}
    </div>
  )
}

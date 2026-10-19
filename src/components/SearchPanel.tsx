import type { FormEvent } from 'react'
import { useState } from 'react'
import { api, CTD_SECTIONS } from '../api'
import type { RetrievalResult } from '../types'
import { Empty, PassageCard } from './shared'

export default function SearchPanel() {
  const [query, setQuery] = useState('')
  const [section, setSection] = useState('')
  const [parents, setParents] = useState(true)
  const [currentOnly, setCurrentOnly] = useState(false)
  const [rerank, setRerank] = useState(true)
  const [finalK, setFinalK] = useState(5)
  const [result, setResult] = useState<RetrievalResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function run(e: FormEvent) {
    e.preventDefault()
    if (!query.trim()) { setError('Type a question to search for.'); return }
    setBusy(true)
    setError('')
    try {
      setResult(await api.search(query, {
        ctd_sections: section ? [section] : [],
        include_parent_sections: parents,
        applicability_statuses: currentOnly ? ['current'] : [],
      }, finalK, rerank))
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <div className="alert alert-info section-gap">
        Runs the same shared retrieval service the agents use: BGE embedding search, then the BGE reranker.
        Scores show relevance to the question only. They are not probabilities and say nothing about compliance.
      </div>

      <form className="card section-gap" onSubmit={run}>
        <div className="card-body form-grid">
          <div className="form-group form-full">
            <label htmlFor="search-query">Question</label>
            <textarea id="search-query" value={query} onChange={e => setQuery(e.target.value)}
              placeholder="e.g. What characteristics are assessed when validating an analytical procedure?" />
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
            <label className="check"><input id="search-parents" type="checkbox" checked={parents} onChange={e => setParents(e.target.checked)} /> Include parent headings (e.g. 3.2.S)</label>
            <label className="check"><input id="search-current" type="checkbox" checked={currentOnly} onChange={e => setCurrentOnly(e.target.checked)} /> Current sources only</label>
            <label className="check"><input id="search-rerank" type="checkbox" checked={rerank} onChange={e => setRerank(e.target.checked)} /> Rerank with BGE cross-encoder</label>
          </div>
          <div className="form-full row-actions">
            <button className="btn btn-primary" type="submit" disabled={busy}>{busy ? 'Searching…' : 'Search'}</button>
            {busy && <span className="text-muted">The first search loads the models and can take a minute.</span>}
          </div>
        </div>
      </form>

      {error && <div className="alert alert-error">{error}</div>}

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
                ? <Empty title="No passages matched">Try another section or switch off "Current sources only". No result does not prove that no relevant rule exists.</Empty>
                : result.passages.map(p => <PassageCard key={p.chunk_id} p={p} />)}
          </div>
        </div>
      )}
    </div>
  )
}

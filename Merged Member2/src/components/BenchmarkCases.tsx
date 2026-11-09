import type { FormEvent } from 'react'
import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import CtdSelect from './CtdSelect'
import type { BenchmarkCase, BenchmarkResultFile } from '../types'
import { Empty, plural } from './shared'

const emptyForm = { question_id: '', question: '', ctd_section: '3.2.S.4', chunk_ids: '', pages: '', expert_notes: '', labelled_by: '' }

const METRICS = ['hit@1', 'recall@5', 'recall@10', 'mrr', 'ndcg@10'] as const
const formatMs = (ms: number) => (ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms)} ms`)

const RAGAS = [
  ['non_llm_context_recall', 'Ragas recall'],
  ['non_llm_context_precision_with_reference', 'Ragas precision'],
] as const

export default function BenchmarkCases({ canEdit, benchmarkFile }: { canEdit: boolean; benchmarkFile?: string }) {
  const [cases, setCases] = useState<BenchmarkCase[]>([])
  const [results, setResults] = useState<BenchmarkResultFile[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [form, setForm] = useState(emptyForm)
  const [showForm, setShowForm] = useState(false)
  const [saving, setSaving] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [c, r] = await Promise.all([api.cases(), api.results()])
      setCases(c)
      setResults(r)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  async function save(e: FormEvent) {
    e.preventDefault()
    setError('')
    const pages = form.pages.split('\n').map(l => l.trim()).filter(Boolean).map(l => {
      const [source, page] = l.split('|').map(s => s.trim())
      return { source_identifier: source, page_number: Number(page) }
    })
    if (pages.some(p => !p.source_identifier || !Number.isInteger(p.page_number) || p.page_number < 1)) {
      setError('Write each relevant page as SOURCE-ID | page number, one per line.')
      return
    }
    setSaving(true)
    try {
      await api.addCase({
        question_id: form.question_id.trim(),
        question: form.question.trim(),
        ctd_section: form.ctd_section,
        relevant_chunk_ids: form.chunk_ids.split(/[\s,]+/).map(s => s.trim()).filter(Boolean),
        relevant_pages: pages,
        expert_notes: form.expert_notes.trim() || null,
        labelled_by: form.labelled_by.trim() || null,
      })
      setForm(emptyForm)
      setShowForm(false)
      await load()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  async function remove(id: string) {
    setError('')
    try {
      await api.deleteCase(id)
      setConfirmDelete(null)
      await load()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const latest = results[0]
  const ragasCols = RAGAS.filter(([key]) => latest?.runs.some(r => typeof r.ragas?.[key] === 'number'))
  const otherQuestions = latest?.benchmark_file && benchmarkFile && latest.benchmark_file !== benchmarkFile

  return (
    <div>
      <div className="card section-gap">
        <div className="card-header">
          <span className="card-title">Latest benchmark run</span>
          {latest && <span className="text-muted text-mono">{latest.file}</span>}
        </div>
        <div className="card-body">
          {!latest ? (
            <Empty title="No benchmark run yet" />
          ) : (
            <>
              <p className="text-muted" style={{ marginBottom: 12 }}>
                {plural(latest.num_questions, 'question')} · {new Date(latest.created_at).toLocaleString()}
              </p>
              {otherQuestions && (
                <div className="alert alert-info">
                  These results were produced with <code>{latest.benchmark_file}</code>; the questions listed below are
                  from <code>{benchmarkFile}</code>.
                </div>
              )}
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Configuration</th><th>Passages</th>
                      {METRICS.map(m => <th key={m} className="num">{m}</th>)}
                      {ragasCols.map(([key, label]) => <th key={key} className="num">{label}</th>)}
                      <th className="num">p50 latency</th><th>Checks</th>
                    </tr>
                  </thead>
                  <tbody>
                    {latest.runs.map(r => {
                      const issues = (r.checks.missing_labelled_chunk_ids?.length ?? 0) + (r.checks.questions_found_verbatim_in_index?.length ?? 0)
                      return (
                        <tr key={r.name}>
                          <td className="text-mono">{r.name}</td>
                          <td className="num">{r.knowledge_base_size}</td>
                          {METRICS.map(m => <td key={m} className="num">{r.aggregate[m] != null ? r.aggregate[m].toFixed(3) : 'n/a'}</td>)}
                          {ragasCols.map(([key]) => (
                            <td key={key} className="num">{typeof r.ragas?.[key] === 'number' ? r.ragas[key].toFixed(3) : 'n/a'}</td>
                          ))}
                          <td className="num">{r.latency.p50_ms != null ? formatMs(r.latency.p50_ms) : 'n/a'}</td>
                          <td>{issues ? <span className="pill pill-yellow">{issues} warning(s)</span> : <span className="pill pill-green">ok</span>}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {canEdit && (showForm ? (
        <form className="card section-gap" onSubmit={save}>
          <div className="card-header"><span className="card-title">New benchmark question</span></div>
          <div className="card-body form-grid">
            <div className="form-group">
              <label htmlFor="bc-id">Question ID</label>
              <input id="bc-id" required value={form.question_id} onChange={e => setForm({ ...form, question_id: e.target.value })} placeholder="Q001" />
            </div>
            <div className="form-group">
              <label htmlFor="bc-section">CTD section</label>
              <CtdSelect id="bc-section" value={form.ctd_section} onChange={v => setForm({ ...form, ctd_section: v })} />
            </div>
            <div className="form-group form-full">
              <label htmlFor="bc-question">Question</label>
              <textarea id="bc-question" required value={form.question} onChange={e => setForm({ ...form, question: e.target.value })} />
            </div>
            <div className="form-group">
              <label htmlFor="bc-chunks">Relevant chunk IDs</label>
              <textarea id="bc-chunks" className="text-mono" value={form.chunk_ids} onChange={e => setForm({ ...form, chunk_ids: e.target.value })} placeholder="ich-q2-p12-c3, ich-q2-p13-c0" />
            </div>
            <div className="form-group">
              <label htmlFor="bc-pages">Relevant pages (for chunk-size tests)</label>
              <textarea id="bc-pages" className="text-mono" value={form.pages} onChange={e => setForm({ ...form, pages: e.target.value })} placeholder={'ICH-Q2 | 12\nICH-Q2 | 13'} />
            </div>
            <div className="form-group">
              <label htmlFor="bc-notes">Expert notes</label>
              <input id="bc-notes" value={form.expert_notes} onChange={e => setForm({ ...form, expert_notes: e.target.value })} placeholder="Optional notes" />
            </div>
            <div className="form-group">
              <label htmlFor="bc-by">Labelled by</label>
              <input id="bc-by" value={form.labelled_by} onChange={e => setForm({ ...form, labelled_by: e.target.value })} />
            </div>
            <div className="form-full row-actions">
              <button className="btn btn-primary" type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save question'}</button>
              <button className="btn btn-ghost" type="button" onClick={() => setShowForm(false)}>Cancel</button>
            </div>
          </div>
        </form>
      ) : (
        <div className="section-gap"><button className="btn btn-primary" onClick={() => setShowForm(true)}>Add benchmark question</button></div>
      ))}

      <div className="card">
        <div className="card-header">
          <span className="card-title">Benchmark questions ({cases.length})</span>
          <span className="text-muted">Stored in {benchmarkFile ?? 'benchmark.jsonl'}</span>
        </div>
        {loading ? <div className="empty"><span className="spinner" /></div> : cases.length === 0 ? (
          <Empty title="No benchmark questions yet" />
        ) : (
          <div className="table-wrap">
            <table className="table-stack">
              <thead><tr><th>ID</th><th>Question</th><th>CTD</th><th>Labels</th><th>Notes</th>{canEdit && <th />}</tr></thead>
              <tbody>
                {cases.map(c => (
                  <tr key={c.question_id}>
                    <td className="text-mono" data-label="ID">{c.question_id}</td>
                    <td data-label="Question">{c.question}</td>
                    <td data-label="CTD">{c.ctd_section}</td>
                    <td className="text-mono" data-label="Labels">
                      {c.relevant_chunk_ids.length > 0 && <div>{plural(c.relevant_chunk_ids.length, 'chunk')}</div>}
                      {c.relevant_pages.length > 0 && <div>{plural(c.relevant_pages.length, 'page')}</div>}
                    </td>
                    <td className="text-muted" data-label="Notes">
                      {c.labelled_by === 'synthetic' && <span className="pill pill-yellow">synthetic</span>} {c.expert_notes}
                    </td>
                    {canEdit && (
                      <td><div className="row-actions">
                        {confirmDelete === c.question_id ? (
                          <>
                            <button className="btn btn-danger" onClick={() => remove(c.question_id)}>Confirm delete</button>
                            <button className="btn btn-ghost" onClick={() => setConfirmDelete(null)}>Keep</button>
                          </>
                        ) : <button className="btn btn-ghost" onClick={() => setConfirmDelete(c.question_id)}>Delete</button>}
                      </div></td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

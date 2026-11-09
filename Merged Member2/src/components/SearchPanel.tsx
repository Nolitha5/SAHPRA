import type { FormEvent } from 'react'
import { useState } from 'react'
import { api } from '../api'
import { ctdTitle } from '../ctd'
import { AGENT_LABEL, buildRequest, isS4, routeAgent } from '../searchRouting'
import type { AgentChoice } from '../searchRouting'
import type { Finding, Route, SearchFilters } from '../types'
import { downloadFindingsReport } from '../wordExport'
import CtdSelect from './CtdSelect'
import { FindingCard } from './Findings'
import SectionScope from './SectionScope'
import WordToolbar from './WordToolbar'

const ROUTE_AGENT_LABEL: Record<Route['agent'], string> = { evidence_rera: 'Evidence/RERA', s4_control: 'S.4 Control' }

/** How the result was produced: chosen automatically (with the reason) or set by hand. */
interface Answered { auto: boolean; agent: string; section: string; route?: Route }

export default function SearchPanel() {
  const [question, setQuestion] = useState('')
  // Advanced options: leave them alone and the app chooses the CTD section and agent itself.
  const [section, setSection] = useState('')
  const [choice, setChoice] = useState<AgentChoice>('auto')
  const [parents, setParents] = useState(true)
  const [currentOnly, setCurrentOnly] = useState(false)
  const [rerank, setRerank] = useState(true)
  const [findings, setFindings] = useState<Finding[] | null>(null)
  const [answered, setAnswered] = useState<Answered | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const automatic = section === '' && choice === 'auto'
  const manualAgent = routeAgent(choice, section)

  async function run(e: FormEvent) {
    e.preventDefault()
    if (!question.trim()) { setError('Type a question.'); return }
    setBusy(true)
    setError('')
    try {
      if (automatic) {
        const res = await api.ask(question.trim(), currentOnly, rerank)
        setFindings(res.findings)
        setAnswered({ auto: true, agent: ROUTE_AGENT_LABEL[res.route.agent], section: res.route.ctd_section, route: res.route })
      } else {
        const filters: SearchFilters = { include_parent_sections: parents, applicability_statuses: currentOnly ? ['current'] : [] }
        const res = await api.runAgent(manualAgent, buildRequest(manualAgent, question.trim(), section, filters, rerank))
        setFindings(res)
        setAnswered({ auto: false, agent: AGENT_LABEL[manualAgent], section: res[0]?.ctd_section ?? section })
      }
    } catch (err) {
      setError((err as Error).message)
      setFindings(null)
      setAnswered(null)
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
            <textarea id="search-query" value={question} onChange={e => setQuestion(e.target.value)}
              placeholder="Ask in your own words, e.g. What are the long-term storage conditions for a drug substance stability study?" />
          </div>

          <div className="form-full row-actions">
            <button className="btn btn-primary" type="submit" disabled={busy}>{busy ? 'Searching…' : 'Search'}</button>
            <span className="text-muted" style={{ fontSize: 12.5 }}>
              {automatic
                ? 'The app searches all guidelines and picks the CTD section and agent for you.'
                : `Using your choice: ${AGENT_LABEL[manualAgent]}${section ? ` · ${section}` : ' · any section'}`}
            </span>
          </div>

          <details className="form-full advanced" open={!automatic}>
            <summary>Advanced options (choose the CTD section or agent yourself)</summary>
            <div className="form-grid" style={{ marginTop: 12 }}>
              <div className="form-group">
                <label htmlFor="search-section">CTD section</label>
                <CtdSelect id="search-section" value={section} onChange={setSection} emptyLabel="Automatic (search all guidelines)" />
              </div>
              <div className="form-group">
                <label htmlFor="search-agent">Agent</label>
                <select id="search-agent" value={choice} onChange={e => setChoice(e.target.value as AgentChoice)}>
                  <option value="auto">Automatic</option>
                  <option value="evidence-rera">Evidence/RERA · find and cite</option>
                  <option value="s4-control">S.4 Control · specifications and batches</option>
                </select>
              </div>
              {section && <div className="form-full"><SectionScope section={section} parents={parents} /></div>}
              <div className="checks form-full">
                {!automatic && (
                  <label className="check"><input id="search-parents" type="checkbox" checked={parents} onChange={e => setParents(e.target.checked)} /> Include parent headings</label>
                )}
                <label className="check"><input id="search-current" type="checkbox" checked={currentOnly} onChange={e => setCurrentOnly(e.target.checked)} /> Current sources only</label>
                <label className="check"><input id="search-rerank" type="checkbox" checked={rerank} onChange={e => setRerank(e.target.checked)} /> Rerank results</label>
              </div>
              {!automatic && (
                <div className="form-full">
                  <button className="btn btn-link" type="button" onClick={() => { setSection(''); setChoice('auto') }}>
                    Back to automatic
                  </button>
                  {manualAgent === 's4-control' && !isS4(section) && (
                    <span className="text-muted" style={{ fontSize: 12.5 }}> S.4 Control will use the general 3.2.S.4 topic.</span>
                  )}
                </div>
              )}
            </div>
          </details>
        </div>
      </form>

      {error && <div className="alert alert-error">{error}</div>}

      {findings && findings.length > 0 && answered && (
        <>
          <div className="route-card">
            <div>
              <b>Answered by {answered.agent}</b> · CTD {answered.section}
              {ctdTitle(answered.section) ? ` ${ctdTitle(answered.section)}` : ''}
              <span className="pill pill-gray" style={{ marginLeft: 8 }}>{answered.auto ? 'chosen automatically' : 'chosen by you'}</span>
            </div>
            {answered.route && (
              <>
                <div className="route-reason">{answered.route.reason}</div>
                {answered.route.based_on.length > 0 && (
                  <div className="route-reason">Best matches: {answered.route.based_on.join(' · ')}</div>
                )}
              </>
            )}
          </div>
          <WordToolbar onDownload={() => downloadFindingsReport(findings)}
            note="Saved assessor comments are included in red." />
          {findings.map(f => <FindingCard key={f.finding_id} f={f} />)}
        </>
      )}
    </div>
  )
}

import { useCallback, useEffect, useState } from 'react'
import { api, getEditorToken, setEditorToken } from './api'
import type { Health } from './types'
import KnowledgeBase from './components/KnowledgeBase'
import SearchPanel from './components/SearchPanel'
import BenchmarkCases from './components/BenchmarkCases'
import CoveragePage from './components/CoveragePage'

type Tab = 'kb' | 'search' | 'bench'

const TABS: { id: Tab; label: string; description: string }[] = [
  { id: 'kb', label: 'Knowledge Base', description: 'The guidelines that Search uses: what is indexed, what is missing, how each CTD 3.2.S heading is covered, and every passage.' },
  { id: 'search', label: 'Search', description: 'Ask a question: the right agent (Evidence/RERA or S.4 Control) searches the guidelines and returns a cited finding for assessor review.' },
  { id: 'bench', label: 'Benchmark', description: 'Retrieval benchmark results and the questions used to measure them.' },
]

export default function App() {
  const [tab, setTab] = useState<Tab>('kb')
  const [kbVersion, setKbVersion] = useState(0) // bumped after imports/deletes so the overview reloads
  const [health, setHealth] = useState<Health | null>(null)
  const [healthError, setHealthError] = useState('')
  const [token, setToken] = useState(getEditorToken())
  const [showToken, setShowToken] = useState(false)
  const [sidebarStats, setSidebarStats] = useState({ total: 0, sources: 0, sections: 0 })

  // Also called after imports/deletes (onChanged), so the sidebar stats stay current.
  const refreshHealth = useCallback(async () => {
    try {
      const nextHealth = await api.health()
      setHealth(nextHealth)
      setHealthError('')
    } catch (e) {
      setHealth(null)
      setHealthError((e as Error).message)
    }
    try {
      const [page, facets] = await Promise.all([api.passages({ limit: 1, offset: 0 }), api.facets()])
      setSidebarStats({
        total: page.total,
        sources: Object.keys(facets.issuing_organization ?? {}).length,
        sections: Object.keys(facets.ctd_section ?? {}).length,
      })
    } catch {
      setSidebarStats({ total: 0, sources: 0, sections: 0 })
    }
  }, [])

  useEffect(() => { refreshHealth() }, [refreshHealth])

  function saveToken(value: string) {
    setEditorToken(value.trim())
    setToken(value.trim())
    setShowToken(false)
  }

  const canEdit = Boolean(health?.editing_enabled && token)
  const active = TABS.find(t => t.id === tab) ?? TABS[0]

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <h1>Agentic QA-RAG</h1>
          <div className="sidebar-sub">Retrieval &amp; Knowledge Base</div>
        </div>

        <nav className="sidebar-nav" role="tablist" aria-orientation="vertical" aria-label="Sections">
          {TABS.map(t => (
            <button key={t.id} role="tab" aria-selected={tab === t.id}
              className={`nav-btn ${tab === t.id ? 'active' : ''}`} onClick={() => setTab(t.id)}>
              {t.label}
            </button>
          ))}
        </nav>

        <div className="sidebar-stats" aria-label="Knowledge base summary">
          <div className="sidebar-stat">
            <span className="sidebar-stat-label">Passages</span>
            <strong>{sidebarStats.total || health?.knowledge_base_size || 0}</strong>
          </div>
          <div className="sidebar-stat">
            <span className="sidebar-stat-label">Issuers</span>
            <strong>{sidebarStats.sources}</strong>
          </div>
          <div className="sidebar-stat">
            <span className="sidebar-stat-label">Sections</span>
            <strong>{sidebarStats.sections}</strong>
          </div>
        </div>

        <div className="sidebar-edit">
          <div className="sidebar-status">
            {health ? (
              <>
                <span className="status-dot status-ok" aria-hidden="true" />
                <span>Connected · <span className="sidebar-collection">{health.collection}</span></span>
              </>
            ) : (
              <>
                <span className="status-dot status-error" aria-hidden="true" />
                <span>{healthError || 'Connecting…'}</span>
              </>
            )}
          </div>
          {health && !health.editing_enabled && <div className="sidebar-note">Read-only mode</div>}
          {health?.editing_enabled && (
            showToken ? (
              <form className="token-form" onSubmit={e => { e.preventDefault(); saveToken((e.currentTarget.elements.namedItem('token') as HTMLInputElement).value) }}>
                <input id="editor-token" name="token" type="password" placeholder="Editor token" defaultValue={token} autoComplete="off" />
                <div className="row-actions">
                  <button className="btn btn-primary" type="submit">Save</button>
                  <button className="btn btn-sidebar" type="button" onClick={() => setShowToken(false)}>Cancel</button>
                </div>
              </form>
            ) : (
              <button className="btn btn-sidebar btn-block" onClick={() => setShowToken(true)}>
                {token ? 'Editing unlocked · change token' : 'Unlock editing'}
              </button>
            )
          )}
        </div>
      </aside>

      <main className="main">
        <header className="page-header">
          <h2 className="page-title">{active.label}</h2>
          <p className="page-description">{active.description}</p>
        </header>
        {tab === 'kb' && (
          <div className="stack">
            <CoveragePage version={kbVersion} />
            <KnowledgeBase canEdit={canEdit} onChanged={() => { setKbVersion(v => v + 1); refreshHealth() }} />
          </div>
        )}
        {tab === 'search' && <SearchPanel />}        {tab === 'bench' && <BenchmarkCases canEdit={canEdit} benchmarkFile={health?.benchmark_file} />}      </main>
    </div>
  )
}

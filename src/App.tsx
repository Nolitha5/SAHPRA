import { useCallback, useEffect, useState } from 'react'
import { api, getEditorToken, setEditorToken } from './api'
import type { Health } from './types'
import KnowledgeBase from './components/KnowledgeBase'
import SearchPanel from './components/SearchPanel'
import Findings from './components/Findings'
import BenchmarkCases from './components/BenchmarkCases'
import ArchitecturePage from './components/ArchitecturePage'

type Tab = 'kb' | 'search' | 'agents' | 'bench' | 'arch'

const TABS: { id: Tab; label: string }[] = [
  { id: 'kb', label: 'Knowledge Base' },
  { id: 'search', label: 'Search' },
  { id: 'agents', label: 'Agents' },
  { id: 'bench', label: 'Benchmark' },
  { id: 'arch', label: 'Architecture' },
]

export default function App() {
  const [tab, setTab] = useState<Tab>('kb')
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

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <span className="badge">M2</span>
          <div>
            <h1>Agentic QA-RAG</h1>
            <div className="sidebar-sub">Retrieval &amp; Knowledge Base</div>
          </div>
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

        <div className="sidebar-status">
          {health ? (
            <>
              <span className="pill pill-green">Connected</span>
              <div><b>{health.knowledge_base_size}</b> available in <code>{health.collection}</code></div>
            </>
          ) : (
            <span className="pill pill-red">{healthError || 'Connecting…'}</span>
          )}
        </div>

        <div className="sidebar-edit">
          {health && !health.editing_enabled && <span className="pill pill-gray">Read-only mode</span>}
          {health?.editing_enabled && (
            showToken ? (
              <form className="token-form" onSubmit={e => { e.preventDefault(); saveToken((e.currentTarget.elements.namedItem('token') as HTMLInputElement).value) }}>
                <input id="editor-token" name="token" type="password" placeholder="Editor token" defaultValue={token} autoComplete="off" />
                <div className="row-actions">
                  <button className="btn btn-primary" type="submit">Save</button>
                  <button className="btn btn-ghost" type="button" onClick={() => setShowToken(false)}>Cancel</button>
                </div>
              </form>
            ) : (
              <button className="btn btn-ghost btn-block" onClick={() => setShowToken(true)}>
                {token ? 'Editing unlocked · change token' : 'Unlock editing'}
              </button>
            )
          )}
        </div>
      </aside>

      <main className="main">
        {tab === 'kb' && <KnowledgeBase canEdit={canEdit} onChanged={refreshHealth} />}
        {tab === 'search' && <SearchPanel />}
        {tab === 'agents' && <Findings />}
        {tab === 'bench' && <BenchmarkCases canEdit={canEdit} benchmarkFile={health?.benchmark_file} />}
        {tab === 'arch' && <ArchitecturePage />}
      </main>
    </div>
  )
}

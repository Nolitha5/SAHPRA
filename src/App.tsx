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

  const refreshHealth = useCallback(async () => {
    try {
      setHealth(await api.health())
      setHealthError('')
    } catch (e) {
      setHealth(null)
      setHealthError((e as Error).message)
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
      <header className="header">
        <div className="header-logo">
          <span className="badge">M2</span>
          <h1>Agentic QA-RAG · Member 2</h1>
        </div>
        <span className="header-sub">Retrieval &amp; Knowledge Base · SAHPRA Module 3.2.S</span>
      </header>

      <div className="statusbar">
        {health ? (
          <>
            <span className="pill pill-green">Server connected</span>
            <span><b>{health.knowledge_base_size}</b> passages in <code>{health.collection}</code></span>
            <span className="text-muted hide-sm">Embeddings: <code>{health.embedding_model}</code></span>
            <span className="text-muted hide-sm">Reranker: <code>{health.reranker_model ?? 'off'}</code></span>
          </>
        ) : (
          <span className="pill pill-red">{healthError || 'Connecting…'}</span>
        )}
        <span className="statusbar-spacer" />
        {health && !health.editing_enabled && <span className="pill pill-gray">Read-only (no editor token set on server)</span>}
        {health?.editing_enabled && (
          showToken ? (
            <form className="row-actions" onSubmit={e => { e.preventDefault(); saveToken((e.currentTarget.elements.namedItem('token') as HTMLInputElement).value) }}>
              <input id="editor-token" name="token" type="password" placeholder="Editor token" defaultValue={token} autoComplete="off" style={{ width: 200 }} />
              <button className="btn btn-primary" type="submit">Save</button>
              <button className="btn btn-ghost" type="button" onClick={() => setShowToken(false)}>Cancel</button>
            </form>
          ) : (
            <button className="btn btn-ghost" onClick={() => setShowToken(true)}>
              {token ? 'Editing unlocked · change token' : 'Unlock editing'}
            </button>
          )
        )}
      </div>

      <nav className="tabs" role="tablist">
        {TABS.map(t => (
          <button key={t.id} role="tab" aria-selected={tab === t.id}
            className={`tab-btn ${tab === t.id ? 'active' : ''}`} onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </nav>

      <main className="main">
        {tab === 'kb' && <KnowledgeBase canEdit={canEdit} onChanged={refreshHealth} />}
        {tab === 'search' && <SearchPanel />}
        {tab === 'agents' && <Findings />}
        {tab === 'bench' && <BenchmarkCases canEdit={canEdit} />}
        {tab === 'arch' && <ArchitecturePage />}
      </main>
    </div>
  )
}

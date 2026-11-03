import type {
  AgentRequest, BenchmarkCase, BenchmarkResultFile, Facets, Finding, Health,
  ImportReport, PassagePage, RetrievalResult, SearchFilters,
} from './types'

const TOKEN_KEY = 'm2-editor-token'

export function getEditorToken(): string {
  try { return sessionStorage.getItem(TOKEN_KEY) ?? '' } catch { return '' }
}
export function setEditorToken(token: string): void {
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token)
    else sessionStorage.removeItem(TOKEN_KEY)
  } catch {
    return
  }
}

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message) }
}

function describe(detail: unknown): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((d: { loc?: string[]; msg?: string }) => `${(d.loc ?? []).filter(x => x !== 'body').join('.')}: ${d.msg ?? 'invalid'}`)
      .join('; ')
  }
  return 'Request failed'
}

async function request<T>(path: string, init: RequestInit = {}, edit = false): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (edit) headers['X-Admin-Token'] = getEditorToken()
  let res: Response
  try {
    res = await fetch(`/api${path}`, { ...init, headers: { ...headers, ...(init.headers as Record<string, string>) } })
  } catch {
    throw new ApiError(0, 'Cannot reach the server. Start it with: python -m app.api (in member2-rag).')
  }
  const text = await res.text()
  let body: { detail?: unknown } | null = null
  try {
    body = text ? JSON.parse(text) : null
  } catch {
    if (!res.ok) {
      throw new ApiError(res.status, res.status >= 500
        ? 'The server is not responding. Start it with: python -m app.api (in member2-rag).'
        : `Request failed (HTTP ${res.status}).`)
    }
    throw new ApiError(res.status, 'The server sent a response that is not JSON.')
  }
  if (!res.ok) throw new ApiError(res.status, describe(body?.detail))
  return body as T
}

export const api = {
  health: () => request<Health>('/health'),

  passages: (p: { ctd_section?: string; organization?: string; document_type?: string; limit: number; offset: number }) => {
    const q = new URLSearchParams()
    Object.entries(p).forEach(([k, v]) => { if (v !== undefined && v !== '') q.set(k, String(v)) })
    return request<PassagePage>(`/passages?${q}`)
  },
  facets: () => request<Facets>('/passages/facets'),
  importPassages: (filename: string, content: string, dry_run: boolean, strict = false) =>
    request<ImportReport>('/passages/import', { method: 'POST', body: JSON.stringify({ filename, content, dry_run, strict }) }, true),
  deletePassage: (chunkId: string) =>
    request<{ deleted: string }>(`/passages/${encodeURIComponent(chunkId)}`, { method: 'DELETE' }, true),

  search: (query: string, filters: SearchFilters, final_k?: number, use_reranker?: boolean) =>
    request<RetrievalResult>('/search', { method: 'POST', body: JSON.stringify({ query, filters, final_k, use_reranker }) }),

  runAgent: (agent: 'evidence-rera' | 's4-control', req: AgentRequest) =>
    request<Finding[]>(`/agents/${agent}`, { method: 'POST', body: JSON.stringify(req) }),

  cases: () => request<BenchmarkCase[]>('/benchmark/cases'),
  addCase: (c: BenchmarkCase) => request<BenchmarkCase>('/benchmark/cases', { method: 'POST', body: JSON.stringify(c) }, true),
  deleteCase: (id: string) => request<{ deleted: string }>(`/benchmark/cases/${encodeURIComponent(id)}`, { method: 'DELETE' }, true),
  results: () => request<BenchmarkResultFile[]>('/benchmark/results'),
}

export const CTD_SECTIONS = [
  '3.2.S', '3.2.S.1', '3.2.S.2', '3.2.S.3', '3.2.S.4', '3.2.S.4.1', '3.2.S.4.2',
  '3.2.S.4.3', '3.2.S.4.4', '3.2.S.4.5', '3.2.S.5', '3.2.S.6', '3.2.S.7',
]
export const DOCUMENT_TYPES = [
  'guideline', 'guidance', 'regulation', 'act', 'monograph', 'general_chapter',
  'template', 'q_and_a', 'other', 'synthetic_test',
]

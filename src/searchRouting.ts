import type { AgentRequest, SearchFilters } from './types'

export type AgentChoice = 'auto' | 'evidence-rera' | 's4-control'
export type Agent = Exclude<AgentChoice, 'auto'>

export const AGENT_LABEL: Record<Agent, string> = { 'evidence-rera': 'Evidence/RERA', 's4-control': 'S.4 Control' }

export const isS4 = (section: string) => section === '3.2.S.4' || section.startsWith('3.2.S.4.')

/** Which agent answers a search: 3.2.S.4 questions go to S.4 Control, everything else to Evidence/RERA. */
export function routeAgent(choice: AgentChoice, section: string): Agent {
  if (choice !== 'auto') return choice
  return isS4(section) ? 's4-control' : 'evidence-rera'
}

/** The agent request for one search. `section` is '' for "Any section". */
export function buildRequest(
  agent: Agent, question: string, section: string, filters: SearchFilters, rerank: boolean,
): AgentRequest {
  const parameters: Record<string, unknown> = { use_reranker: rerank }
  if (agent === 's4-control') {
    // S.4 Control derives its topic from the section; a non-S.4 section falls back to 3.2.S.4.
    return {
      ctd_section: isS4(section) ? section : '3.2.S.4',
      assessment_question: question,
      filters: { ...filters, ctd_sections: [] },
      parameters,
    }
  }
  return {
    ctd_section: section || '3.2', // "Any section": no section filter, the agent searches everything
    assessment_question: question,
    filters: { ...filters, ctd_sections: section ? [section] : [] },
    parameters: { ...parameters, use_section_filter: Boolean(section) },
  }
}

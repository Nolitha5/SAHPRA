// CTD Module 3 headings, copied from ICH M4Q(R1) (in the knowledge base as "ICH M4Q(R1)").
// Every CTD tag used in the knowledge base must appear here, or it cannot be filtered on.

export interface CtdHeading {
  code: string
  title: string
  level: number // 0 = module / part heading, 1 = section, 2 = subsection
}

export interface CtdGroup {
  label: string
  headings: CtdHeading[]
}

export const CTD_GROUPS: CtdGroup[] = [
  {
    label: 'Module 3: Quality',
    headings: [
      { code: '3.2', title: 'Body of data (general guidance for the whole module)', level: 0 },
    ],
  },
  {
    label: '3.2.S Drug substance',
    headings: [
      { code: '3.2.S', title: 'Drug substance (all sections)', level: 0 },
      { code: '3.2.S.1', title: 'General information', level: 1 },
      { code: '3.2.S.1.1', title: 'Nomenclature', level: 2 },
      { code: '3.2.S.1.2', title: 'Structure', level: 2 },
      { code: '3.2.S.1.3', title: 'General properties', level: 2 },
      { code: '3.2.S.2', title: 'Manufacture', level: 1 },
      { code: '3.2.S.2.1', title: 'Manufacturer(s)', level: 2 },
      { code: '3.2.S.2.2', title: 'Description of manufacturing process and process controls', level: 2 },
      { code: '3.2.S.2.3', title: 'Control of materials', level: 2 },
      { code: '3.2.S.2.4', title: 'Controls of critical steps and intermediates', level: 2 },
      { code: '3.2.S.2.5', title: 'Process validation and/or evaluation', level: 2 },
      { code: '3.2.S.2.6', title: 'Manufacturing process development', level: 2 },
      { code: '3.2.S.3', title: 'Characterisation', level: 1 },
      { code: '3.2.S.3.1', title: 'Elucidation of structure and other characteristics', level: 2 },
      { code: '3.2.S.3.2', title: 'Impurities', level: 2 },
      { code: '3.2.S.4', title: 'Control of drug substance', level: 1 },
      { code: '3.2.S.4.1', title: 'Specification', level: 2 },
      { code: '3.2.S.4.2', title: 'Analytical procedures', level: 2 },
      { code: '3.2.S.4.3', title: 'Validation of analytical procedures', level: 2 },
      { code: '3.2.S.4.4', title: 'Batch analyses', level: 2 },
      { code: '3.2.S.4.5', title: 'Justification of specification', level: 2 },
      { code: '3.2.S.5', title: 'Reference standards or materials', level: 1 },
      { code: '3.2.S.6', title: 'Container closure system', level: 1 },
      { code: '3.2.S.7', title: 'Stability', level: 1 },
      { code: '3.2.S.7.1', title: 'Stability summary and conclusions', level: 2 },
      { code: '3.2.S.7.2', title: 'Post-approval stability protocol and stability commitment', level: 2 },
      { code: '3.2.S.7.3', title: 'Stability data', level: 2 },
    ],
  },
  {
    label: '3.2.P Drug product',
    headings: [
      { code: '3.2.P', title: 'Drug product (all sections)', level: 0 },
      { code: '3.2.P.2', title: 'Pharmaceutical development', level: 1 },
    ],
  },
]

export const CTD_HEADINGS: CtdHeading[] = CTD_GROUPS.flatMap(g => g.headings)
export const CTD_SECTIONS: string[] = CTD_HEADINGS.map(h => h.code)

export function ctdTitle(code: string): string | undefined {
  return CTD_HEADINGS.find(h => h.code === code)?.title
}

/** Parent headings, most specific first: 3.2.S.4.1 -> [3.2.S.4, 3.2.S, 3.2] (same rule as the backend filter). */
export function ctdAncestors(code: string): string[] {
  const parts = code.split('.')
  const letter = parts.findIndex(p => /^[A-Z]$/.test(p))
  const stop = letter >= 0 ? letter : 1
  const out: string[] = []
  for (let i = parts.length - 1; i >= stop; i--) out.push(parts.slice(0, i).join('.'))
  return out
}

/** True when `tag` is `code` itself or one of its subsections. */
export function withinSection(tag: string, code: string): boolean {
  return tag === code || tag.startsWith(code + '.')
}

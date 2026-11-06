/**
 * Builds Word (.docx) reports in the browser for search results and agent findings.
 * Nothing is sent to the server: questions, sponsor data and assessor comments stay local.
 * The `docx` library is loaded only when a document is first created, to keep the page light.
 */
import type { ComparisonRow, Finding, RetrievalResult, RetrievedPassage, SearchFilters } from './types'
import { loadComment } from './reviewStore'

type Docx = typeof import('docx')

// A4 portrait, 2 cm margins → usable width 11906 - 2 * 1134 = 9638 DXA.
const PAGE = { width: 11906, height: 16838, margin: 1134 }
const CONTENT_WIDTH = PAGE.width - 2 * PAGE.margin
const FONT = 'Calibri'
const HEADER_FILL = 'D9E2F3'
const LABEL_FILL = 'F2F5FB'
const BORDER = 'A6B4CC'
const BLUE = '1E3A8A'
const RED = 'C81E1E'

const QA_TEXT: Record<string, string> = {
  verified: 'Verified',
  partial: 'Partial (not yet verified)',
  'human-review': 'Human review required',
  conflicting: 'Conflicting evidence',
  unsupported: 'Unsupported',
}

const OUTCOME_TEXT: Record<ComparisonRow['outcome'], string> = {
  within_criteria: 'Within',
  outside_criteria: 'Outside',
  at_least_as_strict: 'At least as strict',
  less_strict: 'Less strict',
  not_compared: 'Not compared',
}

const FLAG_TEXT: Record<string, string> = {
  knowledge_base_empty: 'Knowledge base is empty',
  no_passages_matched_filters: 'No passages matched',
  retrieved_passages_below_relevance_threshold: 'Retrieved passages below relevance threshold',
  contains_superseded_or_withdrawn_source: 'Superseded or withdrawn source',
  contains_draft_source: 'Draft source',
  applicability_status_unknown_for_some_sources: 'Applicability unknown for some sources',
  incomplete_provenance_for_some_sources: 'Incomplete provenance',
  synthetic_test_data_not_real_evidence: 'Synthetic test data, not real evidence',
  instruction_like_text_in_retrieved_passage: 'Instruction-like text in a passage',
  multiple_versions_of_same_document: 'Multiple versions of one document',
}

function stamp(d = new Date()): string {
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`
}

function fmtScore(v: number | null): string {
  return v == null ? 'n/a' : v.toFixed(3)
}

function versionText(v: string | null): string {
  if (!v) return 'n/a'
  return /^\d/.test(v) ? `v${v}` : v
}

/** Small helpers bound to the lazily loaded docx module. */
function kit(d: Docx) {
  const border = { style: d.BorderStyle.SINGLE, size: 4, color: BORDER }
  const borders = { top: border, bottom: border, left: border, right: border }
  const margins = { top: 80, bottom: 80, left: 110, right: 110 }

  const run = (text: string, opts: { bold?: boolean; color?: string; italics?: boolean; size?: number } = {}) =>
    new d.TextRun({ text, font: FONT, size: opts.size ?? 20, bold: opts.bold, color: opts.color, italics: opts.italics })

  // Multi-line text becomes separate paragraphs (docx must not contain "\n").
  const paras = (text: string, opts: Parameters<typeof run>[1] = {}) =>
    (text || '').split(/\r?\n/).map(line => new d.Paragraph({ children: [run(line, opts)], spacing: { after: 40 } }))

  const cell = (content: string | InstanceType<Docx['Paragraph']>[], width: number,
    opts: { fill?: string; bold?: boolean; color?: string; borderColor?: string } = {}) =>
    new d.TableCell({
      width: { size: width, type: d.WidthType.DXA },
      borders: opts.borderColor
        ? (() => { const b = { style: d.BorderStyle.SINGLE, size: 8, color: opts.borderColor }; return { top: b, bottom: b, left: b, right: b } })()
        : borders,
      margins,
      shading: opts.fill ? { fill: opts.fill, type: d.ShadingType.CLEAR, color: 'auto' } : undefined,
      children: typeof content === 'string' ? paras(content, { bold: opts.bold, color: opts.color }) : content,
    })

  /** Grid table with a shaded header row. Column widths must sum to CONTENT_WIDTH. */
  const grid = (headers: string[], rows: string[][], widths: number[]) =>
    new d.Table({
      width: { size: CONTENT_WIDTH, type: d.WidthType.DXA },
      columnWidths: widths,
      rows: [
        new d.TableRow({
          tableHeader: true,
          children: headers.map((h, i) => cell(h, widths[i], { fill: HEADER_FILL, bold: true })),
        }),
        ...rows.map(r => new d.TableRow({ cantSplit: true, children: r.map((v, i) => cell(v, widths[i])) })),
      ],
    })

  /** Two-column label | value table. */
  const details = (pairs: [string, string][]) => {
    const widths = [2400, CONTENT_WIDTH - 2400]
    return new d.Table({
      width: { size: CONTENT_WIDTH, type: d.WidthType.DXA },
      columnWidths: widths,
      rows: pairs.map(([k, v]) => new d.TableRow({
        cantSplit: true,
        children: [cell(k, widths[0], { fill: LABEL_FILL, bold: true }), cell(v || 'n/a', widths[1])],
      })),
    })
  }

  const heading = (text: string, level: 1 | 2) =>
    new d.Paragraph({ heading: level === 1 ? d.HeadingLevel.HEADING_1 : d.HeadingLevel.HEADING_2, children: [new d.TextRun(text)] })

  const spacer = () => new d.Paragraph({ children: [], spacing: { after: 120 } })

  return { run, paras, cell, grid, details, heading, spacer }
}

function documentShell(d: Docx, title: string, children: (InstanceType<Docx['Paragraph']> | InstanceType<Docx['Table']>)[]) {
  const generated = new Date().toLocaleString()
  return new d.Document({
    creator: 'Agentic QA-RAG',
    title,
    styles: {
      default: { document: { run: { font: FONT, size: 20 } } },
      paragraphStyles: [
        { id: 'Title', name: 'Title', basedOn: 'Normal', run: { font: FONT, size: 36, bold: true, color: BLUE },
          paragraph: { spacing: { before: 0, after: 80 } } },
        { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true,
          run: { font: FONT, size: 28, bold: true, color: BLUE },
          paragraph: { spacing: { before: 320, after: 120 }, keepNext: true, outlineLevel: 0 } },
        { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true,
          run: { font: FONT, size: 23, bold: true, color: BLUE },
          paragraph: { spacing: { before: 220, after: 100 }, keepNext: true, outlineLevel: 1 } },
      ],
    },
    sections: [{
      properties: {
        page: {
          size: { width: PAGE.width, height: PAGE.height },
          margin: { top: PAGE.margin, bottom: PAGE.margin, left: PAGE.margin, right: PAGE.margin },
        },
      },
      footers: {
        default: new d.Footer({
          children: [new d.Paragraph({
            alignment: d.AlignmentType.CENTER,
            children: [
              new d.TextRun({ text: 'Research-support output. Not a compliance determination. Page ', font: FONT, size: 16, color: '666666' }),
              new d.TextRun({ children: [d.PageNumber.CURRENT], font: FONT, size: 16, color: '666666' }),
            ],
          })],
        }),
      },
      children: [
        new d.Paragraph({ heading: d.HeadingLevel.TITLE, children: [new d.TextRun(title)] }),
        new d.Paragraph({
          border: { bottom: { style: d.BorderStyle.SINGLE, size: 8, color: BLUE, space: 4 } },
          spacing: { after: 200 },
          children: [new d.TextRun({ text: `Agentic QA-RAG · Generated ${generated}`, font: FONT, size: 18, color: '555555' })],
        }),
        ...children,
      ],
    }],
  })
}

function passageBlock(k: ReturnType<typeof kit>, p: RetrievedPassage, n: number) {
  const m = p.metadata
  const head = `${n}. ${m.issuing_organization} · ${m.source_title} · ${versionText(m.document_version)} · p. ${m.page_number ?? 'n/a'}`
  return [
    ...k.paras(head, { bold: true }),
    ...k.paras(p.text, { size: 19 }),
    k.spacer(),
  ]
}

async function save(doc: InstanceType<Docx["Document"]>, filename: string) {
  const d = await import("docx")
  const blob = await d.Packer.toBlob(doc)
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 10_000)
}

// ---------------------------------------------------------------------------
export async function buildSearchReport(query: string, filters: SearchFilters, result: RetrievalResult) {
  const d = await import('docx')
  const k = kit(d)
  const section = filters.ctd_sections?.length ? filters.ctd_sections.join(', ') : 'Any section'

  const resultWidths = [500, 3838, 800, 1200, 1100, 1100, 1100] // = 9638
  const rows = result.passages.map((p, i) => [
    String(i + 1),
    `${p.metadata.issuing_organization} · ${p.metadata.source_title} (${p.metadata.source_identifier}, ${versionText(p.metadata.document_version)})`,
    p.metadata.page_number != null ? String(p.metadata.page_number) : 'n/a',
    p.metadata.ctd_section ?? 'n/a',
    p.metadata.applicability_status,
    fmtScore(p.retrieval_score),
    fmtScore(p.rerank_score),
  ])

  const doc = documentShell(d, 'Regulatory Search Report', [
    k.heading('Search', 1),
    k.details([
      ['Question', query],
      ['CTD section filter', section],
      ['Include parent headings', filters.include_parent_sections === false ? 'No' : 'Yes'],
      ['Current sources only', filters.applicability_statuses?.includes('current') ? 'Yes' : 'No'],
      ['Reranked', result.reranked ? `Yes (${result.reranker_model})` : 'No'],
      ['Embedding model', result.embedding_model],
      ['Knowledge base size', `${result.knowledge_base_size} passages`],
      ['Candidates considered', String(result.candidates_considered)],
      ['Latency', `${result.latency_ms.toFixed(0)} ms`],
    ]),
    k.heading(`Results (${result.passages.length})`, 1),
    result.passages.length
      ? k.grid(['#', 'Source', 'Page', 'CTD', 'Status', 'Similarity', 'Rerank'], rows, resultWidths)
      : new d.Paragraph({ children: [k.run('No passages matched this search.', { italics: true })] }),
    ...(result.passages.length ? [k.heading('Passage text', 1), ...result.passages.flatMap((p, i) => passageBlock(k, p, i + 1))] : []),
  ])
  return doc
}

// ---------------------------------------------------------------------------
export async function buildFindingsReport(findings: Finding[]) {
  const d = await import('docx')
  const k = kit(d)
  const children: (InstanceType<Docx['Paragraph']> | InstanceType<Docx['Table']>)[] = []

  findings.forEach((f, idx) => {
    const agent = f.agent_name === 'evidence_rera' ? 'Evidence/RERA' : 'S.4 Control'
    const flags = (f.metadata.flags ?? []).map(fl => FLAG_TEXT[fl] ?? fl).join('; ')
    if (idx > 0) children.push(new d.Paragraph({ children: [new d.PageBreak()] }))
    children.push(k.heading(`Finding ${idx + 1}: ${agent} · CTD ${f.ctd_section}`, 1))
    children.push(k.details([
      ['Assessment question', f.assessment_question],
      ['Agent', agent],
      ['CTD section', f.ctd_section],
      ['QA status', QA_TEXT[f.qa_status] ?? f.qa_status],
      ['Evidence status', f.evidence_status.replace(/_/g, ' ')],
      ['Conclusion', f.conclusion],
      ['Rationale', f.rationale],
      ['Uncertainty', f.uncertainty],
      ['Flags', flags || 'None'],
      ['Finding ID', f.finding_id],
      ['Generated', new Date(f.created_at).toLocaleString()],
    ]))

    const rows = f.metadata.confidential_comparison_rows ?? []
    if (rows.length) {
      children.push(k.heading('Comparison', 2))
      children.push(k.grid(
        ['Test', 'Batch', 'Reported', 'Criterion', 'Outcome', 'Reason'],
        rows.map(r => [
          r.test_name, r.batch_id ?? 'n/a', `${r.reported_value ?? ''} ${r.reported_unit ?? ''}`.trim() || 'n/a',
          r.criterion_text ?? 'n/a', OUTCOME_TEXT[r.outcome] + (r.borderline ? ' (borderline)' : ''), r.reason,
        ]),
        [1700, 1000, 1300, 1600, 1300, 2738],
      ))
    }

    children.push(k.heading(`Citations (${f.citations.length})`, 2))
    if (f.citations.length) {
      children.push(k.grid(
        ['#', 'Source', 'Document', 'Version', 'Page', 'CTD', 'Status'],
        f.citations.map((c, i) => [
          String(i + 1), `${c.issuing_organization} · ${c.source_title}`, c.source_identifier,
          versionText(c.document_version), c.page_number != null ? String(c.page_number) : 'n/a',
          c.ctd_section ?? 'n/a', c.applicability_status + (c.provenance_complete ? '' : ' (incomplete provenance)'),
        ]),
        [500, 3138, 1300, 1600, 700, 1200, 1200],
      ))
    } else {
      children.push(new d.Paragraph({ children: [k.run('No citations: no passage met the evidence threshold.', { italics: true })] }))
    }

    // Assessor review in red: the saved comment, or an empty box to write in after printing.
    children.push(k.heading('Assessor review', 2))
    const comment = loadComment(f.finding_id)
    const reviewWidths = [2400, CONTENT_WIDTH - 2400]
    children.push(new d.Table({
      width: { size: CONTENT_WIDTH, type: d.WidthType.DXA },
      columnWidths: reviewWidths,
      rows: [
        new d.TableRow({ children: [
          k.cell('Assessor comment', reviewWidths[0], { fill: 'FDECEC', bold: true, color: RED, borderColor: RED }),
          new d.TableCell({
            width: { size: reviewWidths[1], type: d.WidthType.DXA },
            borders: (() => { const b = { style: d.BorderStyle.SINGLE, size: 8, color: RED }; return { top: b, bottom: b, left: b, right: b } })(),
            margins: { top: 80, bottom: 80, left: 110, right: 110 },
            children: comment
              ? k.paras(comment.text, { color: RED, bold: true })
              : [new d.Paragraph({ children: [], spacing: { after: 900 } })],
          }),
        ] }),
        new d.TableRow({ children: [
          k.cell('Date', reviewWidths[0], { fill: 'FDECEC', bold: true, color: RED, borderColor: RED }),
          k.cell(comment ? new Date(comment.savedAt).toLocaleString() : '', reviewWidths[1], { color: RED, borderColor: RED }),
        ] }),
      ],
    }))

    if (f.regulatory_evidence.length) {
      children.push(k.heading('Supporting passages', 2))
      f.regulatory_evidence.forEach((p, i) => children.push(...passageBlock(k, p, i + 1)))
    }
  })

  const doc = documentShell(d, 'Regulatory Evidence Findings', children)
  return doc
}

export async function downloadSearchReport(query: string, filters: SearchFilters, result: RetrievalResult): Promise<void> {
  await save(await buildSearchReport(query, filters, result), `search-report-${stamp()}.docx`)
}

export async function downloadFindingsReport(findings: Finding[]): Promise<void> {
  await save(await buildFindingsReport(findings), `findings-report-${stamp()}.docx`)
}

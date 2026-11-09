import { useEffect, useState } from 'react'
import { api } from '../api'
import { ctdAncestors, ctdTitle, withinSection } from '../ctd'
import type { Coverage } from '../types'

interface Scope { sources: string[]; passages: number }

function scope(coverage: Coverage, match: (tag: string) => boolean): Scope {
  const sources: string[] = []
  let passages = 0
  for (const s of coverage.sources) {
    const n = Object.entries(s.ctd_sections).reduce((sum, [tag, count]) => sum + (match(tag) ? count : 0), 0)
    if (n > 0) {
      sources.push(s.source_identifier)
      passages += n
    }
  }
  return { sources, passages }
}

/** Under the section box: what the chosen heading covers, i.e. which guidelines a search will look in. */
export default function SectionScope({ section, parents }: { section: string; parents: boolean }) {
  const [coverage, setCoverage] = useState<Coverage | null>(null)

  useEffect(() => {
    api.coverage().then(setCoverage).catch(() => setCoverage(null))
  }, [])

  if (!coverage) return null

  if (!section) {
    return (
      <p className="section-scope">
        Searches all {coverage.source_count} guidelines ({coverage.total_passages} passages).
      </p>
    )
  }

  const own = scope(coverage, tag => withinSection(tag, section))
  const ancestors = ctdAncestors(section)
  const general = parents ? scope(coverage, tag => ancestors.includes(tag)) : { sources: [], passages: 0 }
  const title = ctdTitle(section)

  return (
    <div className={`section-scope ${own.passages === 0 ? 'section-scope-gap' : ''}`}>
      <b>{section}{title ? ` ${title}` : ''}.</b>{' '}
      {own.passages > 0
        ? <>Guidelines for this heading: {own.sources.join(', ')} ({own.passages} passages).</>
        : <>No guideline is tagged with this heading.</>}
      {general.passages > 0 && (
        <> {own.passages > 0 ? 'Also searched' : 'The search uses'}: general guidance tagged {ancestors.join(' or ')} ({general.sources.join(', ')}; {general.passages} passages).</>
      )}
      {own.passages === 0 && general.passages === 0 && (
        <> Nothing can be found here: tick <i>Include parent headings</i> or choose <i>Any section</i>.</>
      )}
    </div>
  )
}

import { TABLE_NOTE } from '../findingTables'
import { pageText } from '../pages'
import type { PageTable } from '../types'

/** Tables found on the cited pages: shown as real tables, with the original image from the PDF. */
export default function SourceTables({ tables }: { tables: PageTable[] }) {
  if (tables.length === 0) return null
  return (
    <div className="doc-section">
      <h4 className="doc-heading">Tables on the cited pages ({tables.length})</h4>
      <p className="table-note">{TABLE_NOTE}</p>
      {tables.map(t => {
        const [head, ...body] = t.rows
        return (
          <figure key={t.table_id} className="source-table">
            <figcaption>
              <b>{t.source_identifier}</b> · {pageText(t.page_number, t.page_label)} · table {t.index_on_page}
            </figcaption>
            <div className="table-wrap">
              <table className="doc-table">
                <thead><tr>{head.map((c, i) => <th key={i}>{c}</th>)}</tr></thead>
                <tbody>
                  {body.map((row, r) => <tr key={r}>{row.map((c, i) => <td key={i}>{c}</td>)}</tr>)}
                </tbody>
              </table>
            </div>
            <details>
              <summary>Show the original table from the PDF</summary>
              <img className="table-image" src={t.image_url} loading="lazy"
                alt={`Original table from ${t.source_identifier}, ${pageText(t.page_number, t.page_label)}`} />
            </details>
          </figure>
        )
      })}
    </div>
  )
}

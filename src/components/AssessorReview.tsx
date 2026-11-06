import { useState } from 'react'
import { loadComment, storeComment, type SavedComment } from '../reviewStore'

export default function AssessorReview({ findingId }: { findingId: string }) {
  const [saved, setSaved] = useState<SavedComment | null>(() => loadComment(findingId))
  const [editing, setEditing] = useState(saved === null)
  const [draft, setDraft] = useState(saved?.text ?? '')
  const inputId = `review-${findingId}`

  function save() {
    const text = draft.trim()
    if (!text) return
    const comment = { text, savedAt: new Date().toISOString() }
    storeComment(findingId, comment)
    setSaved(comment)
    setEditing(false)
  }

  function remove() {
    storeComment(findingId, null)
    setSaved(null)
    setDraft('')
    setEditing(true)
  }

  function cancel() {
    setDraft(saved?.text ?? '')
    setEditing(saved === null)
  }

  return (
    <section className="review" aria-label="Assessor review">
      <div className="review-head">
        <span className="review-title">Assessor review</span>
        {saved && !editing && (
          <span className="review-meta">Commented {new Date(saved.savedAt).toLocaleString()}</span>
        )}
      </div>

      {editing ? (
        <>
          <label htmlFor={inputId} className="sr-only">Assessor comment</label>
          <textarea
            id={inputId}
            className="review-input"
            value={draft}
            onChange={e => setDraft(e.target.value)}
            placeholder="Record your assessment of this finding: whether the evidence is adequate, deficiencies, questions for the applicant…"
          />
          <div className="row-actions">
            <button className="btn btn-review" type="button" onClick={save} disabled={!draft.trim()}>Save comment</button>
            {saved && <button className="btn btn-ghost" type="button" onClick={cancel}>Cancel</button>}
          </div>
        </>
      ) : saved && (
        <>
          <p className="review-text">{saved.text}</p>
          <div className="row-actions">
            <button className="btn btn-link" type="button" onClick={() => { setDraft(saved.text); setEditing(true) }}>Edit</button>
            <button className="btn btn-link btn-link-danger" type="button" onClick={remove}>Delete</button>
          </div>
        </>
      )}
      <p className="review-note">Saved in this browser only. The final regulatory decision rests with the assessor.</p>
    </section>
  )
}

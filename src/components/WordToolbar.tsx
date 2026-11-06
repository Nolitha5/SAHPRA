import { useState } from 'react'

/** "Download Word document" button shown above results. Nothing downloads unless it is clicked. */
export default function WordToolbar({ onDownload, note }: { onDownload: () => Promise<void>; note?: string }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function download() {
    setBusy(true)
    setError('')
    try {
      await onDownload()
    } catch {
      setError('The Word document could not be created. Try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="word-bar">
      <div className="word-bar-main">
        <button className="btn btn-word" type="button" onClick={download} disabled={busy}>
          {busy ? 'Creating…' : 'Download Word document'}
        </button>
        {note && <span className="word-bar-note">{note}</span>}
      </div>
      {error && <div className="alert alert-error" style={{ margin: 0 }}>{error}</div>}
    </div>
  )
}

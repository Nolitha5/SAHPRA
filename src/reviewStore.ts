// Assessor comments stay in this browser only (localStorage). Nothing is sent to the
// server, so review notes about a sponsor's dossier are never stored or logged centrally.
const KEY_PREFIX = 'm2-assessor-comment:'

export interface SavedComment {
  text: string
  savedAt: string
}

export function loadComment(findingId: string): SavedComment | null {
  try {
    const raw = localStorage.getItem(KEY_PREFIX + findingId)
    if (!raw) return null
    const parsed = JSON.parse(raw) as SavedComment
    return typeof parsed?.text === 'string' ? parsed : null
  } catch {
    return null
  }
}

export function storeComment(findingId: string, comment: SavedComment | null): void {
  try {
    if (comment) localStorage.setItem(KEY_PREFIX + findingId, JSON.stringify(comment))
    else localStorage.removeItem(KEY_PREFIX + findingId)
  } catch {
    // Storage blocked (private window etc.): the comment still shows for this session.
  }
}

// Recently analysed objects, kept only in this browser's localStorage (never sent anywhere).
const KEY = 'll-recent'
const MAX = 6

export function getRecent(): string[] {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) || '[]')
    return Array.isArray(v) ? v.filter((x) => typeof x === 'string').slice(0, MAX) : []
  } catch {
    return []
  }
}

export function pushRecent(id: string) {
  try {
    localStorage.setItem(KEY, JSON.stringify([id, ...getRecent().filter((x) => x !== id)].slice(0, MAX)))
  } catch {
    /* storage disabled */
  }
}

export function clearRecent() {
  try { localStorage.removeItem(KEY) } catch { /* ignore */ }
}

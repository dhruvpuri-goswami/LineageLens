import * as React from 'react'
import { api, type Health, type NodeLite } from './api'

interface Ctx {
  nodes: NodeLite[]
  byId: Map<string, NodeLite>
  version: number
  refresh: () => void
  drawerId: string | null
  openNode: (id: string | null) => void
  theme: 'light' | 'dark'
  health: Health | null
  toggleTheme: () => void
}

const AppCtx = React.createContext<Ctx | null>(null)

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [nodes, setNodes] = React.useState<NodeLite[]>([])
  const [version, setVersion] = React.useState(0)
  const [drawerId, setDrawerId] = React.useState<string | null>(null)
  const [theme, setTheme] = React.useState<'light' | 'dark'>(() => (document.documentElement.classList.contains('dark') ? 'dark' : 'light'))

  React.useEffect(() => {
    api.nodes().then((r) => setNodes(r.nodes)).catch(() => setNodes([]))
  }, [version])

  const [health, setHealth] = React.useState<Health | null>(null)
  React.useEffect(() => { api.health().then(setHealth).catch(() => setHealth(null)) }, [version])

  const byId = React.useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes])
  const toggleTheme = React.useCallback(() => {
    setTheme((t) => {
      const next = t === 'dark' ? 'light' : 'dark'
      document.documentElement.classList.toggle('dark', next === 'dark')
      try {
        localStorage.setItem('ll-theme', next)
      } catch {
        /* ignore */
      }
      return next
    })
  }, [])

  const value = React.useMemo(
    () => ({ nodes, byId, version, refresh: () => setVersion((v) => v + 1), drawerId, openNode: setDrawerId, theme, toggleTheme, health }),
    [nodes, byId, version, drawerId, theme, toggleTheme, health],
  )
  return <AppCtx.Provider value={value}>{children}</AppCtx.Provider>
}

export function useApp() {
  const c = React.useContext(AppCtx)
  if (!c) throw new Error('AppProvider missing')
  return c
}

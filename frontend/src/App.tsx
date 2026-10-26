import { NavLink, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { ArrowUpRight, ChevronRight, ChevronsUpDown, Coffee, GitCompareArrows, LayoutDashboard, Library, Moon, Radar, Route as RouteIcon, Settings as SettingsIcon, ShieldCheck, Star, Sun } from 'lucide-react'
import { api } from './lib/api'
import { fmtTime } from './lib/utils'
import { cn } from './lib/utils'
import { useApp } from './lib/store'
import { NodeSearch } from './components/NodeSearch'
import { DetailDrawer } from './components/DetailDrawer'
import { Button, useAsync } from './components/ui'
import Dashboard from './pages/Dashboard'
import ImpactExplorer from './pages/ImpactExplorer'
import Upstream from './pages/Upstream'
import Simulator from './pages/Simulator'
import Catalog from './pages/Catalog'
import Settings from './pages/Settings'

const NAV_SECTIONS = [
  {
    label: 'Analyse',
    items: [
      { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true, hint: 'Start here: pick the column you are about to change' },
      { to: '/impact', label: 'Impact Explorer', icon: Radar, hint: 'What breaks downstream if a column changes' },
      { to: '/upstream', label: 'Upstream Trace', icon: RouteIcon, hint: 'Where a visual, measure or column gets its data' },
      { to: '/simulator', label: 'Change Simulator', icon: GitCompareArrows, hint: 'Test several column changes together' },
    ],
  },
  { label: 'Explore', items: [{ to: '/catalog', label: 'Catalog', icon: Library, hint: 'Every scanned object with usage counts' }] },
  { label: 'Setup', items: [{ to: '/settings', label: 'Settings & Scan', icon: SettingsIcon, hint: 'Point at your files and run a scan' }] },
]
const ALL_NAV = NAV_SECTIONS.flatMap((s) => s.items)

function SupportLinks() {
  const { health } = useApp()
  const coffee = health?.links?.buymeacoffee_url
  const gh = health?.links?.github_repo_url
  if (!coffee && !gh) return null
  return (
    <div className="space-y-1.5">
      {coffee && (
        <a href={coffee} target="_blank" rel="noopener noreferrer" title="Opens in your browser. A plain link; no tracking."
          className="group flex items-center gap-2.5 rounded-lg border border-amber-500/25 bg-gradient-to-r from-amber-400/15 via-amber-300/5 to-transparent px-2.5 py-2 text-[12.5px] font-medium transition-colors hover:border-amber-500/50">
          <span className="flex size-6 items-center justify-center rounded-md bg-amber-400 text-amber-950 shadow-soft"><Coffee className="size-3.5" /></span>
          <span className="flex-1">Support this project</span>
          <ArrowUpRight className="size-3.5 text-muted-foreground transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
        </a>
      )}
      {gh && (
        <a href={gh} target="_blank" rel="noopener noreferrer" title="Opens the GitHub repository in your browser"
          className="group flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-[12.5px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground">
          <Star className="size-3.5" /><span className="flex-1">Star on GitHub</span><ArrowUpRight className="size-3.5 opacity-0 transition-opacity group-hover:opacity-100" />
        </a>
      )}
    </div>
  )
}

function GithubMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={className} fill="currentColor" aria-hidden>
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
    </svg>
  )
}

function Logo() {
  return (
    <div className="flex items-center gap-2.5 px-2">
      <svg viewBox="0 0 32 32" className="size-8 shrink-0">
        <defs><linearGradient id="lg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#6366f1" /><stop offset="1" stopColor="#06b6d4" /></linearGradient></defs>
        <rect width="32" height="32" rx="8" fill="url(#lg)" />
        <circle cx="9" cy="10" r="3" fill="#fff" /><circle cx="9" cy="22" r="3" fill="#fff" opacity=".8" /><circle cx="23" cy="16" r="4" fill="#fff" />
        <path d="M11.5 11.2 19.5 14.6M11.5 20.8l8-3.4" stroke="#fff" strokeWidth="2" strokeLinecap="round" />
      </svg>
      <div className="leading-tight">
        <div className="text-[15px] font-semibold tracking-tight">LineageLens</div>
        <div className="text-[10.5px] text-muted-foreground">dbt · Snowflake · Power BI</div>
      </div>
    </div>
  )
}

export default function App() {
  const { theme, toggleTheme, health, version } = useApp()
  const nav = useNavigate()
  const loc = useLocation()
  const sum = useAsync(() => api.summary(), [version])
  const current = ALL_NAV.find((n) => (n.end ? loc.pathname === n.to : loc.pathname.startsWith(n.to))) ?? ALL_NAV[0]
  const gh = health?.links?.github_repo_url
  return (
    <div className="flex h-full">
      <aside className="hidden w-[244px] shrink-0 flex-col border-r bg-sidebar md:flex">
        <div className="flex h-14 items-center border-b px-3"><Logo /></div>
        <div className="flex min-h-0 flex-1 flex-col overflow-y-auto px-3 py-4 scrollbar-thin">
          {sum.data && (
            <button onClick={() => nav('/settings')} title="Project and scan settings"
              className="mb-5 flex w-full items-center gap-2.5 rounded-lg border bg-card px-2.5 py-2 text-left shadow-soft transition-colors hover:border-primary/40">
              <span className="flex size-7 items-center justify-center rounded-md bg-gradient-to-br from-indigo-500 to-cyan-500 text-[11px] font-bold text-white">{(sum.data.project_name || 'P').slice(0, 1).toUpperCase()}</span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[12.5px] font-semibold">{sum.data.project_name}</span>
                <span className="block truncate text-[11px] text-muted-foreground">{sum.data.is_sample ? `Synthetic sample${sum.data.sample_name === 'large' ? ' · large' : ''}` : `Scanned ${fmtTime(sum.data.meta.scanned_at)}`}</span>
              </span>
              <ChevronsUpDown className="size-3.5 text-muted-foreground" />
            </button>
          )}
          <nav className="space-y-5">
            {NAV_SECTIONS.map((sec) => (
              <div key={sec.label}>
                <div className="mb-1.5 px-2.5 text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground/80">{sec.label}</div>
                <div className="space-y-0.5">
                  {sec.items.map(({ to, label, icon: Icon, end, hint }) => (
                    <NavLink key={to} to={to} end={end} title={hint}
                      className={({ isActive }) => cn(
                        'group relative flex items-center gap-2.5 rounded-md px-2.5 py-[7px] text-[13px] font-medium transition-colors',
                        isActive ? 'bg-card text-foreground shadow-soft ring-1 ring-border' : 'text-muted-foreground hover:bg-muted hover:text-foreground',
                      )}>
                      {({ isActive }) => (
                        <>
                          {isActive && <span className="absolute -left-3 top-1.5 bottom-1.5 w-[3px] rounded-r bg-primary" />}
                          <Icon className={cn('size-4', isActive ? 'text-primary' : '')} />
                          {label}
                        </>
                      )}
                    </NavLink>
                  ))}
                </div>
              </div>
            ))}
          </nav>
          <div className="mt-auto space-y-3 pt-6">
            <SupportLinks />
            <div className="flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-[11.5px] text-muted-foreground" title="Deterministic parsing. No AI, no telemetry. Nothing leaves this machine.">
              <ShieldCheck className="size-3.5 text-emerald-600 dark:text-emerald-400" />
              <span>100% local · no AI · no telemetry</span>
            </div>
          </div>
        </div>
        <div className="flex h-11 items-center justify-between border-t px-4">
          <span className="font-mono text-[11px] text-muted-foreground">v{health?.version ?? '2.1.0'}</span>
          <Button variant="ghost" size="icon" onClick={toggleTheme} title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'} className="size-7">
            {theme === 'dark' ? <Sun /> : <Moon />}
          </Button>
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-4 border-b bg-background/80 px-6 backdrop-blur">
          <div className="hidden min-w-0 items-center gap-1.5 text-[13px] lg:flex">
            <span className="text-muted-foreground">LineageLens</span>
            <ChevronRight className="size-3.5 text-muted-foreground/60" />
            <span className="font-medium">{current.label}</span>
          </div>
          <NodeSearch shortcut className="mx-auto w-full max-w-lg" onSelect={(n) => nav(`/impact?id=${encodeURIComponent(n.id)}`)} placeholder="Jump to any column, measure or visual…" />
          <div className="flex items-center gap-1">
            {gh && (
              <a href={gh} target="_blank" rel="noopener noreferrer" title="GitHub repository" className="inline-flex size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground">
                <GithubMark className="size-4" />
              </a>
            )}
            <Button variant="ghost" size="icon" onClick={toggleTheme} title="Toggle theme" className="size-8">{theme === 'dark' ? <Sun /> : <Moon />}</Button>
          </div>
        </header>
        <main className="min-h-0 flex-1 overflow-y-auto scrollbar-thin">
          <div className="mx-auto max-w-[1440px] px-6 py-7 lg:px-8">
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/impact" element={<ImpactExplorer />} />
              <Route path="/upstream" element={<Upstream />} />
              <Route path="/simulator" element={<Simulator />} />
              <Route path="/catalog" element={<Catalog />} />
              <Route path="/settings" element={<Settings />} />
              <Route path="*" element={<Dashboard />} />
            </Routes>
          </div>
        </main>
      </div>
      <DetailDrawer />
    </div>
  )
}

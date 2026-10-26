import { NavLink, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { ChevronRight, ChevronsUpDown, Coffee, HardDriveUpload, GitCompareArrows, LayoutDashboard, Library, Moon, Radar, Route as RouteIcon, Settings as SettingsIcon, Sun } from 'lucide-react'
import { api } from './lib/api'
import { fmtTime } from './lib/utils'
import { cn } from './lib/utils'
import { useApp } from './lib/store'
import { NodeSearch } from './components/NodeSearch'
import { DetailDrawer } from './components/DetailDrawer'
import { BrandMark, Button, GithubMark, useAsync } from './components/ui'
import Dashboard from './pages/Dashboard'
import ImpactExplorer from './pages/ImpactExplorer'
import Upstream from './pages/Upstream'
import Simulator from './pages/Simulator'
import Catalog from './pages/Catalog'
import Settings from './pages/Settings'
import LoadData from './pages/LoadData'

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
  {
    label: 'Setup',
    items: [
      { to: '/load', label: 'Load your data', icon: HardDriveUpload, hint: 'Upload your dbt, Snowflake and Power BI files' },
      { to: '/settings', label: 'Settings & Scan', icon: SettingsIcon, hint: 'Config file, samples and scan log' },
    ],
  },
]
const ALL_NAV = NAV_SECTIONS.flatMap((s) => s.items)

function SupportLinks() {
  const { health } = useApp()
  const coffee = health?.links?.buymeacoffee_url
  const gh = health?.links?.github_repo_url
  if (!coffee && !gh) return null
  const cls = 'flex items-center gap-2 rounded-md px-2 py-1 text-[12px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground'
  return (
    <div className="space-y-0.5">
      {gh && (
        <a href={gh} target="_blank" rel="noopener noreferrer" title="Source code, issues and releases on GitHub" className={cls}>
          <GithubMark className="size-3.5" /><span>GitHub</span>
        </a>
      )}
      {coffee && (
        <a href={coffee} target="_blank" rel="noopener noreferrer" title="Support development (opens Buy Me a Coffee in your browser)" className={cls}>
          <Coffee className="size-3.5" /><span>Sponsor</span>
        </a>
      )}
    </div>
  )
}

function Logo() {
  return (
    <div className="flex items-center gap-2.5 px-1">
      <BrandMark className="size-7 shrink-0" />
      <div className="leading-tight">
        <div className="text-[14px] font-semibold tracking-[-0.01em]">LineageLens</div>
        <div className="text-[11px] text-muted-foreground">dbt · Snowflake · Power BI</div>
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
              className="mb-5 flex w-full items-center gap-2.5 rounded-md border bg-card px-2 py-1.5 text-left transition-colors hover:bg-muted">
              <span className="flex size-6 items-center justify-center rounded border bg-muted text-[11px] font-semibold text-muted-foreground">{(sum.data.project_name || 'P').slice(0, 1).toUpperCase()}</span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[12.5px] font-semibold">{sum.data.project_name}</span>
                <span className="block truncate text-[11px] text-muted-foreground">{sum.data.is_sample ? `Synthetic sample${sum.data.sample_name === 'large' ? ' · large' : ''}` : sum.data.is_upload ? `Uploaded data · ${fmtTime(sum.data.meta.scanned_at)}` : `Scanned ${fmtTime(sum.data.meta.scanned_at)}`}</span>
              </span>
              <ChevronsUpDown className="size-3.5 text-muted-foreground" />
            </button>
          )}
          <nav className="space-y-4">
            {NAV_SECTIONS.map((sec) => (
              <div key={sec.label}>
                <div className="mb-1 px-2 text-[11px] font-medium text-muted-foreground">{sec.label}</div>
                <div className="space-y-0.5">
                  {sec.items.map(({ to, label, icon: Icon, end, hint }) => (
                    <NavLink key={to} to={to} end={end} title={hint}
                      className={({ isActive }) => cn(
                        'group relative flex items-center gap-2.5 rounded-md px-2 py-1.5 text-[13px] font-medium transition-colors',
                        isActive ? 'bg-muted text-foreground' : 'text-muted-foreground hover:bg-muted/70 hover:text-foreground',
                      )}>
                      {({ isActive }) => (
                        <>
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
          <div className="mt-auto space-y-3 border-t pt-3">
            <SupportLinks />
            <div className="px-2 text-[11px] leading-snug text-muted-foreground" title="Deterministic parsing. No telemetry. Nothing leaves this machine.">
              Runs locally. No telemetry.
            </div>
          </div>
        </div>
        <div className="flex h-11 items-center justify-between border-t px-4">
          <span className="font-mono text-[11px] text-muted-foreground">v{health?.version ?? '2.3.0'}</span>
          <Button variant="ghost" size="icon" onClick={toggleTheme} title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'} className="size-7">
            {theme === 'dark' ? <Sun /> : <Moon />}
          </Button>
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-4 border-b bg-background px-6">
          <div className="hidden min-w-0 items-center gap-1.5 text-[13px] lg:flex">
            <span className="text-muted-foreground">LineageLens</span>
            <ChevronRight className="size-3.5 text-muted-foreground/60" />
            <span className="font-medium">{current.label}</span>
          </div>
          <NodeSearch shortcut className="mx-auto w-full max-w-lg" onSelect={(n) => nav(`/impact?id=${encodeURIComponent(n.id)}`)} placeholder="Search columns, measures, visuals" />
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
              <Route path="/load" element={<LoadData />} />
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

import * as React from 'react'
import { Coffee, Database, AlertTriangle, CheckCircle2, FileCog, FolderOpen, Info, Loader2, Lock, Play, RefreshCw, Save, XCircle } from 'lucide-react'
import { api, type ScanStatus } from '@/lib/api'
import { useApp } from '@/lib/store'
import { cn, fmtTime } from '@/lib/utils'
import { Badge, Button, Card, CardHeader, ErrorBox, GithubMark, Input, PageHeader, Spinner, useAsync } from '@/components/ui'

export default function Settings() {
  const { refresh, version, health } = useApp()
  const cfg = useAsync(() => api.config(), [version])
  const sum = useAsync(() => api.summary(), [version])
  const [path, setPath] = React.useState('')
  const [yaml, setYaml] = React.useState('')
  const [msg, setMsg] = React.useState<{ ok: boolean; text: string } | null>(null)
  const [status, setStatus] = React.useState<ScanStatus | null>(null)
  const wasRunning = React.useRef(false)

  React.useEffect(() => { if (cfg.data) { setPath(cfg.data.path); setYaml(cfg.data.yaml) } }, [cfg.data])
  React.useEffect(() => {
    let alive = true
    const tick = async () => {
      try {
        const s = await api.scanStatus()
        if (!alive) return
        setStatus(s)
        if (wasRunning.current && !s.running) { refresh(); setMsg(s.error ? { ok: false, text: s.error } : { ok: true, text: s.message }) }
        wasRunning.current = s.running
      } catch { /* ignore */ }
    }
    tick()
    const t = setInterval(tick, 700)
    return () => { alive = false; clearInterval(t) }
  }, [refresh])

  const scan = async () => { setMsg(null); await api.scan(); wasRunning.current = true }
  const save = async (andScan: boolean) => {
    setMsg(null)
    try {
      const edited = !!cfg.data && yaml !== cfg.data.yaml
      try {
        await api.saveConfig(path, edited ? yaml : undefined)
      } catch (e: any) {
        // New path that does not exist yet: create it from the YAML in the editor.
        if (!edited && String(e.message).startsWith('Config not found')) await api.saveConfig(path, yaml)
        else throw e
      }
      setMsg({ ok: true, text: 'Configuration saved.' })
      if (andScan) await scan()
      else refresh()
    } catch (e: any) { setMsg({ ok: false, text: String(e.message) }) }
  }
  const useSample = async (name: 'standard' | 'large' = 'standard') => { setMsg(null); try { await api.useSample(name); wasRunning.current = true; refresh() } catch (e: any) { setMsg({ ok: false, text: String(e.message) }) } }
  const running = status?.running
  const warnings = sum.data?.warnings ?? []

  return (
    <div className="space-y-5">
      <PageHeader icon={<FileCog />} title="Settings & Scan" description="Point LineageLens at your dbt project, Snowflake view SQL and Power BI (PBIP) files, then scan. Everything stays on this machine." />
      <div className="grid gap-6 xl:grid-cols-3">
        <div className="space-y-6 xl:col-span-2">
          <Card>
            <CardHeader icon={<Database />} title="Sample data" description="Explore LineageLens with synthetic projects. Nothing here comes from a real company." />
            <div className="grid gap-3 px-5 pb-5 sm:grid-cols-2">
              {([
                { name: 'standard', title: 'Standard', sub: 'Retail analytics', detail: '1 report · 12 visuals · ~210 objects. Quick to read.' },
                { name: 'large', title: 'Large', sub: 'Helios analytics', detail: '7 reports · 151 visuals · ~940 objects. Stress-tests the lineage map.' },
              ] as const).map((o) => {
                const active = !!cfg.data?.is_sample && (sum.data?.sample_name ?? 'standard') === o.name
                return (
                  <button key={o.name} disabled={running || active} onClick={() => useSample(o.name)}
                    className={cn('rounded-lg border p-3.5 text-left transition-all', active ? 'border-primary/50 bg-primary/5 ring-1 ring-primary/30' : 'hover:border-primary/40 hover:bg-muted/40', running && 'opacity-60')}>
                    <div className="flex items-center justify-between">
                      <span className="text-[13px] font-semibold">{o.title} <span className="font-normal text-muted-foreground">· {o.sub}</span></span>
                      {active ? <Badge className="border-primary/30 bg-primary/10 text-primary">Loaded</Badge> : <span className="text-[11.5px] font-medium text-primary">Load</span>}
                    </div>
                    <p className="mt-1 text-[12px] text-muted-foreground">{o.detail}</p>
                  </button>
                )
              })}
            </div>
          </Card>
          <Card>
            <CardHeader icon={<FolderOpen />} title="Project configuration" description="lineagelens.yml — all paths are local files and folders" action={cfg.data?.is_sample && <Badge className="text-muted-foreground">Bundled sample (read-only)</Badge>} />
            <div className="space-y-3 px-5 pb-5">
              {cfg.error && <ErrorBox error={cfg.error} />}
              <label className="block space-y-1">
                <span className="text-xs font-medium">Config file path</span>
                <Input value={path} onChange={(e) => setPath(e.target.value)} className="font-mono text-xs" placeholder="C:\analytics\lineagelens.yml" />
                <span className="block text-[11px] text-muted-foreground">Create one with <span className="font-mono">lineagelens init</span>. To edit the sample, enter a new path (e.g. <span className="font-mono">C:\lineage\lineagelens.yml</span>) and save — a copy is written there.</span>
              </label>
              <label className="block space-y-1">
                <span className="text-xs font-medium">YAML</span>
                <textarea value={yaml} onChange={(e) => setYaml(e.target.value)} spellCheck={false}
                  className="h-[380px] w-full resize-y rounded-md border bg-muted/30 p-3 font-mono text-[12px] leading-relaxed outline-none scrollbar-thin focus:ring-2 focus:ring-ring" />
              </label>
              <div className="flex flex-wrap items-center gap-2">
                <Button onClick={() => save(true)} disabled={running}><Save /> Save & scan</Button>
                <Button variant="outline" onClick={() => save(false)} disabled={running}>Save only</Button>
                {msg && <span className={cn('flex items-center gap-1.5 text-sm', msg.ok ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400')}>{msg.ok ? <CheckCircle2 className="size-4" /> : <XCircle className="size-4" />}{msg.text}</span>}
              </div>
            </div>
          </Card>
        </div>
        <div className="space-y-6">
          <Card>
            <CardHeader icon={<RefreshCw />} title="Scan" description={sum.data ? `Last scan ${fmtTime(sum.data.meta.scanned_at)}` : undefined}
              action={<Button size="sm" onClick={scan} disabled={running}>{running ? <Loader2 className="animate-spin" /> : <Play />}{running ? 'Scanning' : 'Scan now'}</Button>} />
            <div className="space-y-3 px-5 pb-5">
              <div>
                <div className="mb-1 flex justify-between text-xs"><span className="font-medium">{status?.step || 'Idle'}</span><span className="tabular-nums text-muted-foreground">{Math.round((status?.pct ?? 0) * (status?.pct && status.pct <= 1 ? 100 : 1))}%</span></div>
                <div className="h-2 overflow-hidden rounded-full bg-muted"><div className={cn('h-full rounded-full transition-all', status?.error ? 'bg-red-500' : 'bg-primary')} style={{ width: `${(status?.pct ?? 0) <= 1 ? (status?.pct ?? 0) * 100 : status?.pct}%` }} /></div>
                <div className="mt-1.5 text-xs text-muted-foreground">{status?.message}</div>
              </div>
              <div className="max-h-56 overflow-y-auto rounded-md bg-muted/40 p-2 font-mono text-[11px] leading-relaxed scrollbar-thin">
                {(status?.log ?? []).length === 0 && <span className="text-muted-foreground">No scan log yet.</span>}
                {status?.log.map((l, i) => <div key={i}><span className="text-muted-foreground">{new Date(l.t * 1000).toLocaleTimeString()}</span> {l.message}</div>)}
              </div>
              {sum.data?.meta.sources && (
                <div className="space-y-1.5 text-xs">
                  {([['dbt', 'dbt projects'], ['views', 'Snowflake view files'], ['semantic_models', 'Semantic models'], ['reports', 'Reports']] as const).map(([k, label]) => {
                    const items: any[] = (sum.data!.meta.sources as any)[k] ?? []
                    return (
                      <div key={k} className="flex items-start justify-between gap-3 rounded-md border px-2.5 py-1.5">
                        <span className="text-muted-foreground">{label}</span>
                        <span className="text-right font-medium">{items.length ? items.map((i) => i.name ?? i.relation?.split('.').pop()).join(', ') : '—'}</span>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          </Card>
          <Card>
            <CardHeader icon={<AlertTriangle />} title="Warnings" description={`${warnings.length} from the last scan`} />
            <div className="max-h-72 space-y-1.5 overflow-y-auto px-5 pb-5 scrollbar-thin">
              {sum.loading && <Spinner />}
              {warnings.length === 0 && !sum.loading && <div className="text-sm text-muted-foreground">No warnings.</div>}
              {warnings.map((w, i) => (
                <div key={i} className="flex gap-2 text-xs">
                  {w.level === 'info' ? <Info className="mt-0.5 size-3.5 shrink-0 text-sky-500" /> : <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-amber-500" />}
                  <div><span className="font-mono text-foreground/80">{w.source}</span> <span className="text-muted-foreground">{w.message}</span></div>
                </div>
              ))}
            </div>
          </Card>
          <Card className="p-5">
            <div className="flex items-center gap-2 text-sm font-semibold"><Info className="size-4 text-muted-foreground" /> About</div>
            <p className="mt-2 text-xs text-muted-foreground">LineageLens v{health?.version} · MIT licensed open source.</p>
            <div className="mt-3 flex flex-wrap gap-2">
              {health?.links?.buymeacoffee_url && <a href={health.links.buymeacoffee_url} target="_blank" rel="noopener noreferrer" className="inline-flex h-7 items-center gap-1.5 rounded-md border px-2.5 text-xs font-medium text-muted-foreground hover:bg-muted hover:text-foreground"><Coffee className="size-3.5" />Sponsor</a>}
              {health?.links?.github_repo_url && <a href={health.links.github_repo_url} target="_blank" rel="noopener noreferrer" className="inline-flex h-7 items-center gap-1.5 rounded-md border px-2.5 text-xs font-medium hover:bg-muted"><GithubMark className="size-3.5" />GitHub repository</a>}
            </div>
            <p className="mt-3 text-[11px] text-muted-foreground">Links are set in <span className="font-mono">lineagelens/links.py</span> or the <span className="font-mono">BUYMEACOFFEE_URL</span> / <span className="font-mono">GITHUB_REPO_URL</span> environment variables. Plain links, no tracking.</p>
          </Card>
          <Card className="p-5">
            <div className="flex items-center gap-2 text-sm font-semibold"><Lock className="size-4 text-muted-foreground" /> Privacy</div>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-muted-foreground">
              <li>Runs entirely on this machine (server bound to 127.0.0.1).</li>
              <li>No telemetry and no cloud calls. Lineage comes from deterministic SQL, DAX and M parsing.</li>
              <li>Optional Snowflake / Power BI connections are only used if you enable them in the config.</li>
              <li>Scan results are stored locally in SQLite under your user profile.</li>
            </ul>
          </Card>
        </div>
      </div>
    </div>
  )
}

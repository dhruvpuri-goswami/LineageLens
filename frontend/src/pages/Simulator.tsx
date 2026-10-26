import * as React from 'react'
import { AlertOctagon, CheckCircle2, ClipboardCopy, FlaskConical, GitCompareArrows, Play, Plus, X } from 'lucide-react'
import { api, type ChangeType, type DiffResult, type ImpactEntry, type ImpactResult, type Impact } from '@/lib/api'
import { useApp } from '@/lib/store'
import { cn } from '@/lib/utils'
import { Badge, Button, Card, CardHeader, ConfidenceBadge, EmptyState, ErrorBox, ImpactBadge, Input, PageHeader, Spinner, Stat, Tabs, TypeIcon } from '@/components/ui'
import { NodeSearch } from '@/components/NodeSearch'

const CHANGES: ChangeType[] = ['drop', 'rename', 'type', 'logic']
const CHANGE_STYLE: Record<string, string> = {
  drop: 'bg-red-500/10 text-red-700 dark:text-red-400 border-red-500/30',
  rename: 'bg-orange-500/10 text-orange-700 dark:text-orange-400 border-orange-500/30',
  type: 'bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-500/30',
  logic: 'bg-sky-500/10 text-sky-700 dark:text-sky-400 border-sky-500/30',
  add: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-500/30',
}

interface Row { id: string; change: ChangeType }
interface Hit { e: ImpactEntry; impact: Impact; causes: string[] }

function WhatIf() {
  const { byId, openNode } = useApp()
  const [rows, setRows] = React.useState<Row[]>([])
  const [results, setResults] = React.useState<ImpactResult[] | null>(null)
  const [loading, setLoading] = React.useState(false)
  const [err, setErr] = React.useState<string | null>(null)

  const loadExample = async () => {
    try {
      const sum = await api.summary()
      const picks = sum.top_columns.filter((c) => c.type === 'dbt_model_column').slice(0, 3)
      const ch: ChangeType[] = ['drop', 'rename', 'type']
      setRows(picks.map((c, i) => ({ id: c.id, change: ch[i] }))); setResults(null)
    } catch (e: any) { setErr(String(e.message)) }
  }
  const run = async () => {
    setLoading(true); setErr(null)
    try { setResults(await Promise.all(rows.map((r) => api.impact([r.id], r.change)))) } catch (e: any) { setErr(String(e.message)) }
    setLoading(false)
  }
  const merged = React.useMemo(() => {
    if (!results) return null
    const visuals = new Map<string, Hit>(); const objects = new Map<string, Hit>()
    results.forEach((r, i) => {
      const cause = byId.get(rows[i]?.id)?.display ?? rows[i]?.id
      const add = (m: Map<string, Hit>, e: ImpactEntry) => {
        const h = m.get(e.id)
        if (!h) m.set(e.id, { e, impact: e.impact, causes: [cause] })
        else { if (e.impact === 'breaks') h.impact = 'breaks'; if (!h.causes.includes(cause)) h.causes.push(cause) }
      }
      r.reports.forEach((rep) => rep.pages.forEach((p) => p.visuals.forEach((v) => add(visuals, v))))
      ;['measure', 'calc_column', 'rls_role', 'calc_group_item', 'field_parameter'].forEach((t) => (r.groups[t] ?? []).forEach((e) => add(objects, e)))
    })
    const sort = (a: Hit, b: Hit) => (a.impact === b.impact ? a.e.display.localeCompare(b.e.display) : a.impact === 'breaks' ? -1 : 1)
    return { visuals: [...visuals.values()].sort(sort), objects: [...objects.values()].sort(sort) }
  }, [results, rows, byId])

  return (
    <div className="space-y-5">
      <Card className="p-4">
        <div className="mb-3 text-sm text-muted-foreground">Plan a batch of changes (e.g. a gold-layer refactor) and see the combined blast radius before you open the PR.</div>
        <div className="space-y-2">
          {rows.map((r, i) => {
            const n = byId.get(r.id)
            return (
              <div key={r.id} className="flex flex-wrap items-center gap-3 rounded-lg border bg-muted/30 px-3 py-2">
                <TypeIcon type={n?.type ?? 'dbt_model_column'} className="size-6" />
                <span className="min-w-[220px] font-mono text-[13px] font-medium">{n?.display ?? r.id}</span>
                <div className="flex gap-1">
                  {CHANGES.map((c) => (
                    <button key={c} onClick={() => setRows(rows.map((x, j) => (j === i ? { ...x, change: c } : x)))}
                      className={cn('rounded-md border px-2.5 py-1 text-xs font-medium capitalize', r.change === c ? CHANGE_STYLE[c] : 'border-transparent text-muted-foreground hover:bg-muted')}>{c}</button>
                  ))}
                </div>
                {results?.[i] && <span className="text-xs text-muted-foreground">{results[i].summary.visuals} visuals · {results[i].summary.measures} measures</span>}
                <button onClick={() => { setRows(rows.filter((_, j) => j !== i)); setResults(null) }} className="ml-auto text-muted-foreground hover:text-foreground"><X className="size-4" /></button>
              </div>
            )
          })}
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <NodeSearch className="w-full max-w-md" placeholder="Add a column to the change set…" onSelect={(n) => { if (!rows.some((r) => r.id === n.id)) { setRows([...rows, { id: n.id, change: 'drop' }]); setResults(null) } }} />
          <Button onClick={run} disabled={!rows.length || loading}>{loading ? <Spinner /> : <Play />} Simulate {rows.length > 0 && `${rows.length} change${rows.length > 1 ? 's' : ''}`}</Button>
          {!rows.length && <span className="flex items-center gap-1.5 text-xs text-muted-foreground"><Plus className="size-3.5" />Add one or more columns to begin</span>}
        </div>
      </Card>
      {err && <ErrorBox error={err} />}
      {!rows.length && (
        <Card>
          <EmptyState icon={<FlaskConical />} title="No changes planned yet">
            Add every column your refactor touches, pick drop, rename, type or logic change for each, then press <b>Simulate</b> to see the combined impact on measures, RLS and visuals.
            <div className="mt-4"><Button variant="outline" onClick={loadExample}><FlaskConical /> Try an example refactor</Button></div>
          </EmptyState>
        </Card>
      )}
      {merged && (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label="Visuals affected" value={merged.visuals.length} tone="brand" />
            <Stat label="Visuals breaking" value={merged.visuals.filter((h) => h.impact === 'breaks').length} tone="red" />
            <Stat label="Model objects" value={merged.objects.length} sub="measures, calc cols, RLS…" />
            <Stat label="RLS roles" value={merged.objects.filter((h) => h.e.type === 'rls_role').length} tone={merged.objects.some((h) => h.e.type === 'rls_role') ? 'red' : 'green'} />
          </div>
          <div className="grid gap-6 lg:grid-cols-2">
            {[['Affected visuals', merged.visuals], ['Affected measures, calc columns & RLS', merged.objects]].map(([title, list]) => (
              <Card key={title as string}>
                <CardHeader title={title as string} />
                <div className="max-h-[460px] overflow-y-auto px-3 pb-3 scrollbar-thin">
                  {(list as Hit[]).length === 0 && <div className="px-2 text-sm text-muted-foreground">None</div>}
                  {(list as Hit[]).map((h) => (
                    <button key={h.e.id} onClick={() => openNode(h.e.id)} className="flex w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-left hover:bg-muted/60">
                      <TypeIcon type={h.e.type} className="size-6" />
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-[13px] font-medium">{h.e.name}</div>
                        <div className="truncate text-[11px] text-muted-foreground">{h.e.container} · {h.e.parent} · from {h.causes.join(', ')}</div>
                      </div>
                      <ImpactBadge impact={h.impact} />
                    </button>
                  ))}
                </div>
              </Card>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

function DiffPanel() {
  const { openNode } = useApp()
  const [oldP, setOld] = React.useState('')
  const [newP, setNew] = React.useState('')
  const [res, setRes] = React.useState<DiffResult | null>(null)
  const [loading, setLoading] = React.useState(false)
  const [err, setErr] = React.useState<string | null>(null)
  const [copied, setCopied] = React.useState(false)
  const run = async (body: { old?: string; new?: string; sample?: boolean }) => {
    setLoading(true); setErr(null)
    try { setRes(await api.diff(body)) } catch (e: any) { setErr(String(e.message)) }
    setLoading(false)
  }
  return (
    <div className="space-y-5">
      <Card className="p-4">
        <div className="mb-3 text-sm text-muted-foreground">
          Compare two dbt builds (paths to <span className="font-mono text-foreground">target/manifest.json</span>, a dbt project folder, a LineageLens config <span className="font-mono">.yml</span> or a saved scan <span className="font-mono">.db</span>).
          Leave <i>Old</i> empty to compare against the current scan. Same engine as <span className="font-mono">lineagelens diff</span> in CI.
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          <label className="space-y-1"><span className="text-xs font-medium">Old (baseline)</span><Input value={oldP} onChange={(e) => setOld(e.target.value)} placeholder="(current scan)" className="font-mono text-xs" /></label>
          <label className="space-y-1"><span className="text-xs font-medium">New (proposed)</span><Input value={newP} onChange={(e) => setNew(e.target.value)} placeholder="C:\repo\feature-branch\target\manifest.json" className="font-mono text-xs" /></label>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <Button onClick={() => run({ old: oldP || undefined, new: newP })} disabled={!newP || loading}>{loading ? <Spinner /> : <GitCompareArrows />} Compare</Button>
          <Button variant="outline" onClick={() => run({ sample: true })} disabled={loading}><Play /> Run sample diff</Button>
        </div>
      </Card>
      {err && <ErrorBox error={err} />}
      {res && (
        <>
          <div className={cn('flex items-center gap-3 rounded-lg border px-4 py-3', res.breaking ? 'border-red-500/30 bg-red-500/[0.07]' : 'border-emerald-500/30 bg-emerald-500/[0.07]')}>
            {res.breaking ? <AlertOctagon className="size-6 text-red-600" /> : <CheckCircle2 className="size-6 text-emerald-600" />}
            <div>
              <div className="font-semibold">{res.breaking ? 'Breaking changes detected' : 'No breaking changes'}</div>
              <div className="text-sm text-muted-foreground">{res.summary.changes} column change{res.summary.changes === 1 ? '' : 's'} ({res.summary.added} added) · {res.summary.visuals} visuals affected, {res.summary.visuals_breaking} breaking · {res.summary.objects} model objects</div>
            </div>
          </div>
          <Card>
            <CardHeader title="Column changes" description="Detected by comparing column lineage, SQL expressions and data types" />
            <div className="overflow-x-auto px-5 pb-4">
              <table className="w-full text-sm">
                <thead className="text-left text-[11px] uppercase tracking-wide text-muted-foreground"><tr><th className="py-2 font-medium">Change</th><th className="font-medium">Column</th><th className="font-medium">Detail</th><th className="text-right font-medium">Visuals</th><th className="text-right font-medium">PBI objects</th></tr></thead>
                <tbody>
                  {res.changes.map((c) => (
                    <tr key={c.id + c.change} className="border-t align-top">
                      <td className="py-2.5"><Badge className={cn('capitalize', CHANGE_STYLE[c.change])}>{c.change}</Badge></td>
                      <td className="py-2.5 font-mono text-[12.5px]"><button onClick={() => c.change !== 'add' && openNode(c.id)} className="hover:underline">{c.display}</button></td>
                      <td className="max-w-md py-2.5 text-[12.5px] text-muted-foreground">{c.detail}</td>
                      <td className="py-2.5 text-right tabular-nums">{c.impact?.summary.visuals ?? '–'}</td>
                      <td className="py-2.5 text-right tabular-nums">{c.pbi_objects ?? '–'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader title="Affected visuals & model objects" />
              <div className="max-h-[480px] overflow-y-auto px-3 pb-3 scrollbar-thin">
                {[...res.visuals, ...res.objects].map((h) => (
                  <button key={h.id} onClick={() => openNode(h.id)} className="flex w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-left hover:bg-muted/60">
                    <TypeIcon type={h.type} className="size-6" />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-[13px] font-medium">{h.name}</div>
                      <div className="truncate text-[11px] text-muted-foreground">{h.container} · caused by <span className="font-mono">{h.cause}</span> ({h.cause_change})</div>
                    </div>
                    {h.confidence !== 'high' && <ConfidenceBadge c={h.confidence} />}
                    <ImpactBadge impact={h.impact} />
                  </button>
                ))}
                {res.visuals.length + res.objects.length === 0 && <div className="px-2 text-sm text-muted-foreground">None</div>}
              </div>
            </Card>
            <Card>
              <CardHeader title="PR comment (Markdown)" description="Paste into the pull request, or let CI post it" action={
                <Button size="sm" variant="outline" onClick={() => { navigator.clipboard?.writeText(res.markdown); setCopied(true); setTimeout(() => setCopied(false), 1500) }}><ClipboardCopy />{copied ? 'Copied' : 'Copy'}</Button>
              } />
              <div className="max-h-[480px] overflow-y-auto px-5 pb-4 scrollbar-thin"><pre className="whitespace-pre-wrap rounded-lg bg-muted/50 p-3 font-mono text-[11.5px] leading-relaxed">{res.markdown}</pre></div>
            </Card>
          </div>
        </>
      )}
      {!res && !loading && <Card><EmptyState icon={<GitCompareArrows />} title="No comparison yet">Click <b>Run sample diff</b> to see a renamed, a dropped, a retyped and a logic-changed column in the bundled sample.</EmptyState></Card>}
    </div>
  )
}

export default function Simulator() {
  const [tab, setTab] = React.useState<'whatif' | 'diff'>('whatif')
  return (
    <div className="space-y-5">
      <PageHeader icon={<FlaskConical />} title="Change Simulator" description="Simulate a set of planned column changes, or diff two dbt builds to get a PR-ready impact report." />
      <Card className="overflow-hidden"><Tabs value={tab} onChange={setTab} tabs={[{ value: 'whatif', label: 'What-if change set' }, { value: 'diff', label: 'Compare dbt builds (diff)' }]} /></Card>
      {tab === 'whatif' ? <WhatIf /> : <DiffPanel />}
    </div>
  )
}

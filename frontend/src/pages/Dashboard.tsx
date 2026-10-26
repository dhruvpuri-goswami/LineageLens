import * as React from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  AlertTriangle, ArrowRight, BarChart3, Boxes, ChevronDown, Clock, Database, FileBarChart2, FileDown, CheckCircle2,
  HardDriveUpload, Info, Radar, RefreshCw, ScanLine, ShieldCheck, Sigma, Snowflake, Table2, Trash2, X,
} from 'lucide-react'
import { api, type Summary } from '@/lib/api'
import { useApp } from '@/lib/store'
import { cn, fmtTime, plural } from '@/lib/utils'
import { getRecent } from '@/lib/recent'
import { Badge, Button, Card, EmptyState, ErrorBox, GLOSSARY, InfoTip, Spinner, Tip, TypeIcon, useAsync } from '@/components/ui'
import { NodeSearch } from '@/components/NodeSearch'

const GUIDE_KEY = 'll-guide-dismissed'

export default function Dashboard() {
  const { version } = useApp()
  const nav = useNavigate()
  const { data: s, error, loading } = useAsync(() => api.summary(), [version])
  if (error) return <ErrorBox error={error} />
  if (loading || !s) return <div className="flex h-64 items-center justify-center"><Spinner className="size-6" /></div>
  const total = Object.values(s.counts).reduce((a, b) => a + b, 0)
  if (!total) {
    return (
      <Card className="mx-auto mt-10 max-w-2xl">
        <EmptyState icon={<ScanLine />} title="No lineage yet">
          Scan your dbt project and Power BI files to see what depends on each column.
          <div className="mt-5 flex justify-center gap-2">
            <Button onClick={() => nav('/load')}><HardDriveUpload /> Load your data</Button>
            <Button variant="outline" onClick={() => nav('/settings')}><ScanLine /> Settings</Button>
          </div>
        </EmptyState>
        <div className="border-t px-6 py-5"><HowItWorks compact /></div>
      </Card>
    )
  }
  return (
    <div className="space-y-4">
      <Hero s={s} />
      <Guide isSample={s.is_sample} />
      <Insights s={s} />
      <ScanDetails s={s} />
    </div>
  )
}

/* ------------------------------------------------------------------ hero */

function Hero({ s }: { s: Summary }) {
  const nav = useNavigate()
  const { byId } = useApp()
  const go = (id: string) => nav(`/impact?id=${encodeURIComponent(id)}`)
  const recent = getRecent().map((id) => byId.get(id)).filter(Boolean).slice(0, 4) as NonNullable<ReturnType<typeof byId.get>>[]
  const suggested = s.top_columns.filter((t) => !recent.some((r) => r.id === t.id)).slice(0, recent.length ? 3 : 5)
  return (
    <section className="rounded-lg border bg-card">
      <div className="grid gap-6 px-6 py-6 lg:grid-cols-[1fr_auto]">
        <div className="max-w-2xl">
          <div className="flex flex-wrap items-center gap-2 text-[12px] font-medium text-muted-foreground">
            <span>{s.project_name}</span>
            {s.is_sample && <Badge className="text-muted-foreground">Synthetic sample{s.sample_name === 'large' ? ' · large' : ''}</Badge>}
            {s.is_upload && <Badge className="text-muted-foreground">Uploaded data</Badge>}
          </div>
          <h1 className="mt-2 text-[22px] font-semibold leading-tight tracking-[-0.015em]">Which column are you changing?</h1>
          <p className="mt-1.5 text-[14px] leading-relaxed text-muted-foreground">
            Pick a dbt, Snowflake or Power BI column. LineageLens shows every measure, RLS role, report and visual that
            <Tip text={GLOSSARY.breaks}><span className="mx-1 cursor-help font-medium text-red-600 underline decoration-dotted underline-offset-2 dark:text-red-400">breaks</span></Tip>
            or
            <Tip text={GLOSSARY.may}><span className="mx-1 cursor-help font-medium text-amber-600 underline decoration-dotted underline-offset-2 dark:text-amber-400">may change</span></Tip>
            before you ship.
          </p>
          <NodeSearch size="lg" className="mt-4 max-w-xl" placeholder="Search a column, e.g. fct_sales.NET_AMOUNT" onSelect={(n) => go(n.id)} />
          <div className="mt-4 space-y-2">
            {recent.length > 0 && (
              <ChipRow icon={<Clock />} label="Recent">
                {recent.map((n) => <ColumnChip key={n.id} type={n.type} label={n.display} onClick={() => go(n.id)} />)}
              </ChipRow>
            )}
            {suggested.length > 0 && (
              <ChipRow icon={<BarChart3 />} label="Most used">
                {suggested.map((t) => <ColumnChip key={t.id} type={t.type} label={t.display} meta={`${t.visuals} visuals`} onClick={() => go(t.id)} />)}
              </ChipRow>
            )}
          </div>
        </div>
        <div className="flex flex-col items-start gap-1 text-xs text-muted-foreground lg:items-end lg:text-right">
          <span>Last scan</span>
          <span className="text-sm font-medium text-foreground">{fmtTime(s.meta.scanned_at)}</span>
          {s.meta.duration !== undefined && <span>{s.meta.duration}s · {s.edges.toLocaleString()} lineage links</span>}
          <div className="mt-2 flex flex-wrap gap-2 lg:justify-end">
            {s.is_sample && <Button size="sm" onClick={() => nav('/load')} title="Upload your dbt, Snowflake and Power BI files"><HardDriveUpload /> Load your data</Button>}
            <Button variant="outline" size="sm" onClick={() => nav('/settings')}><RefreshCw /> Re-scan</Button>
          </div>
        </div>
      </div>
    </section>
  )
}

function ChipRow({ icon, label, children }: { icon: React.ReactNode; label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="mr-1 inline-flex w-[84px] items-center gap-1.5 text-[11.5px] font-medium text-muted-foreground [&_svg]:size-3.5">{icon}{label}</span>
      {children}
    </div>
  )
}

function ColumnChip({ type, label, meta, onClick }: { type: string; label: string; meta?: string; onClick: () => void }) {
  return (
    <button onClick={onClick} className="inline-flex items-center gap-1.5 rounded-md border bg-background py-0.5 pl-0.5 pr-2 text-[12px] transition-colors hover:border-foreground/25 hover:bg-muted">
      <TypeIcon type={type} className="size-5 rounded [&_svg]:size-3" />
      <span className="font-mono">{label}</span>
      {meta && <span className="text-muted-foreground">· {meta}</span>}
    </button>
  )
}

/* ------------------------------------------------------------------ guide */

function Guide({ isSample }: { isSample: boolean }) {
  const [hidden, setHidden] = React.useState(() => { try { return localStorage.getItem(GUIDE_KEY) === '1' } catch { return false } })
  if (hidden) return null
  const dismiss = () => { try { localStorage.setItem(GUIDE_KEY, '1') } catch { /* ignore */ } setHidden(true) }
  return (
    <Card className="relative px-5 py-4">
      <button onClick={dismiss} title="Hide this guide" className="absolute right-3 top-3 rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground"><X className="size-4" /></button>
      <div className="mb-4 flex flex-wrap items-baseline gap-x-3">
        <h2 className="text-sm font-semibold">How it works</h2>
        <span className="text-xs text-muted-foreground">{isSample ? 'You are looking at synthetic sample data. Point LineageLens at your own files when ready.' : 'Three steps, all on this machine.'}</span>
      </div>
      <HowItWorks />
    </Card>
  )
}

function HowItWorks({ compact }: { compact?: boolean }) {
  const nav = useNavigate()
  const steps = [
    { icon: FileDown, title: 'Export your files', body: <>Run <code className="rounded bg-muted px-1 font-mono text-[11.5px]">dbt docs generate</code> for <span className="font-mono">manifest.json</span> + <span className="font-mono">catalog.json</span>, and save Power BI reports as <b>PBIP</b> (TMDL + PBIR).</>, cta: null },
    { icon: ScanLine, title: 'Upload and scan', body: <>Drop the files on <b>Load your data</b> and press <b>Scan</b>. SQL, DAX and M are parsed with fixed rules, so results are repeatable.</>, cta: { label: 'Load your data', to: '/load' } },
    { icon: Radar, title: 'Ask impact', body: <>Search the column you plan to change and see what <b>breaks</b> or <b>may change</b>, down to each visual.</>, cta: { label: 'Try an example', to: '/impact' } },
  ]
  return (
    <ol className={cn('grid gap-3', compact ? 'sm:grid-cols-3' : 'md:grid-cols-3')}>
      {steps.map((st, i) => (
        <li key={st.title} className="relative flex gap-3 rounded-md border p-3">
          <span className="flex size-6 shrink-0 items-center justify-center rounded border bg-muted font-mono text-[11px] font-medium text-muted-foreground">{i + 1}</span>
          <div className="min-w-0">
            <div className="flex items-center gap-1.5 text-[13px] font-semibold"><st.icon className="size-3.5 text-muted-foreground" />{st.title}</div>
            <p className="mt-1 text-[12.5px] leading-relaxed text-muted-foreground">{st.body}</p>
            {st.cta && !compact && <button onClick={() => nav(st.cta!.to)} className="mt-1.5 inline-flex items-center gap-1 text-[12px] font-medium text-primary hover:underline">{st.cta.label}<ArrowRight className="size-3" /></button>}
          </div>
        </li>
      ))}
    </ol>
  )
}

/* ------------------------------------------------------------------ insights */

function InsightCard({ icon, tone, title, value, valueSub, why, children, to, cta }: {
  icon: React.ReactNode; tone: string; title: string; value: React.ReactNode; valueSub?: React.ReactNode; why: string; children?: React.ReactNode; to: string; cta: string
}) {
  return (
    <Card className="group flex flex-col p-4">
      <div className="flex items-center gap-2.5">
        <span className={cn('text-muted-foreground [&_svg]:size-4', tone)}>{icon}</span>
        <h3 className="text-[13px] font-semibold">{title}</h3>
      </div>
      <div className="mt-3 flex items-baseline gap-2">
        <span className="text-2xl font-semibold leading-none tabular-nums tracking-tight">{value}</span>
        {valueSub && <span className="text-xs text-muted-foreground">{valueSub}</span>}
      </div>
      <p className="mt-2 text-[12.5px] leading-snug text-muted-foreground">{why}</p>
      {children && <div className="mt-3 flex-1">{children}</div>}
      <Link to={to} className="mt-4 inline-flex items-center gap-1 self-start text-[12.5px] font-medium text-primary hover:underline">{cta}<ArrowRight className="size-3.5" /></Link>
    </Card>
  )
}

function Insights({ s }: { s: Summary }) {
  const nav = useNavigate()
  const { openNode } = useApp()
  const cov = s.pbi_column_coverage
  const covPct = cov.total ? Math.round((cov.matched / cov.total) * 100) : 100
  const low = s.confidence.low ?? 0
  const review = cov.unmatched + low
  const unused = s.unused_gold_columns.length + s.unused_pbi_objects.length
  const c = s.counts
  const top = s.top_columns.slice(0, 3)
  const maxV = Math.max(1, ...top.map((t) => t.visuals))
  return (
    <section>
      <div className="mb-2 flex items-baseline justify-between">
        <h2 className="text-sm font-semibold">Insights</h2>
        <span className="text-xs text-muted-foreground">From the last scan</span>
      </div>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <InsightCard icon={<AlertTriangle />} tone="" title="Most depended-on columns"
          value={top[0]?.visuals ?? 0} valueSub={top[0] ? `visuals depend on ${top[0].display.split('.').pop()}` : 'no usage found'}
          why="Changing these breaks the most report visuals. Check them before any rename or drop."
          to={top[0] ? `/impact?id=${encodeURIComponent(top[0].id)}` : '/catalog?kind=warehouse'} cta={top[0] ? 'See what breaks' : 'Open catalog'}>
          <div className="space-y-1.5">
            {top.map((t) => (
              <button key={t.id} onClick={() => nav(`/impact?id=${encodeURIComponent(t.id)}`)} className="block w-full rounded-md px-1.5 py-1 text-left hover:bg-muted/70">
                <div className="flex items-center justify-between gap-2 text-[12px]"><span className="truncate font-mono">{t.display}</span><span className="shrink-0 tabular-nums text-muted-foreground">{t.visuals}</span></div>
                <div className="mt-1 h-1 overflow-hidden rounded-full bg-muted"><div className="h-full rounded-full bg-red-500/80" style={{ width: `${(t.visuals / maxV) * 100}%` }} /></div>
              </button>
            ))}
          </div>
        </InsightCard>

        <InsightCard icon={<CheckCircle2 />} tone="" title="Lineage coverage"
          value={`${covPct}%`} valueSub="of Power BI columns traced to the warehouse"
          why="Untraced columns are blind spots: impact analysis cannot see past them."
          to={cov.unmatched ? '/catalog?kind=pbi' : '/settings'} cta={review ? `Review ${plural(review, 'item')}` : 'View scan warnings'}>
          <div className="h-1.5 overflow-hidden rounded-full bg-muted"><div className="h-full rounded-full bg-emerald-500" style={{ width: `${covPct}%` }} /></div>
          <ul className="mt-3 space-y-1 text-[12px]">
            <li className="flex items-center justify-between"><span className="text-muted-foreground">Traced</span><span className="tabular-nums">{cov.matched} / {cov.total}</span></li>
            <li className="flex items-center justify-between"><span className="text-muted-foreground">Unmatched columns</span><span className={cn('tabular-nums', cov.unmatched && 'text-amber-600 dark:text-amber-400')}>{cov.unmatched}</span></li>
            <li className="flex items-center justify-between"><span className="inline-flex items-center gap-1 text-muted-foreground">Low-confidence links<InfoTip text={GLOSSARY.confidence} /></span><span className={cn('tabular-nums', low && 'text-amber-600 dark:text-amber-400')}>{low}</span></li>
          </ul>
          {cov.unmatched_list.slice(0, 1).map((u) => (
            <button key={u.id} onClick={() => openNode(u.id)} className="mt-2 w-full truncate rounded-md bg-amber-500/10 px-2 py-1 text-left font-mono text-[11.5px] text-amber-700 dark:text-amber-300">{u.display}</button>
          ))}
        </InsightCard>

        <InsightCard icon={<Trash2 />} tone="" title="Clean-up candidates"
          value={unused} valueSub="objects not used by any visual or RLS role"
          why="Unused columns and measures add cost and confusion. Review them for removal."
          to={s.unused_gold_columns.length ? '/catalog?unused=gold' : '/catalog?unused=pbi'} cta="Review candidates">
          <ul className="space-y-1 text-[12px]">
            <li className="flex items-center justify-between"><span className="text-muted-foreground">Warehouse columns</span><Link to="/catalog?unused=gold" className="tabular-nums hover:text-primary">{s.unused_gold_columns.length}</Link></li>
            <li className="flex items-center justify-between"><span className="text-muted-foreground">PBI columns & measures</span><Link to="/catalog?unused=pbi" className="tabular-nums hover:text-primary">{s.unused_pbi_objects.length}</Link></li>
          </ul>
        </InsightCard>

        <InsightCard icon={<FileBarChart2 />} tone="" title="Reports scanned"
          value={s.reports.length} valueSub={`${plural(c.page ?? 0, 'page')} · ${plural(c.visual ?? 0, 'visual')}`}
          why="Impact is only as complete as the reports you scan. Add every PBIP that uses this model."
          to="/catalog?kind=visuals" cta="Browse reports">
          <ul className="space-y-1 text-[12px]">
            {s.reports.slice(0, 4).map((r) => (
              <li key={r.id} className="flex items-center justify-between gap-2"><span className="truncate">{r.name}</span><span className="shrink-0 tabular-nums text-muted-foreground">{r.visuals}</span></li>
            ))}
            {s.reports.length > 4 && <li className="text-muted-foreground">+{s.reports.length - 4} more</li>}
          </ul>
        </InsightCard>
      </div>
    </section>
  )
}

/* ------------------------------------------------------------------ scan details */

function ScanDetails({ s }: { s: Summary }) {
  const [open, setOpen] = React.useState(false)
  const c = s.counts
  const conf = s.confidence
  const confTotal = (conf.high ?? 0) + (conf.medium ?? 0) + (conf.low ?? 0) || 1
  const warn = s.warnings.filter((w) => w.level !== 'info')
  const stats: [string, number, React.ReactNode, string][] = [
    ['Source columns', c.dbt_source_column ?? 0, <Database />, 'dbt sources'],
    ['dbt model columns', c.dbt_model_column ?? 0, <Boxes />, 'staging, intermediate, marts'],
    ['Snowflake columns', (c.snowflake_view_column ?? 0) + (c.snowflake_table_column ?? 0), <Snowflake />, 'views and tables'],
    ['Power BI columns', (c.pbi_model_column ?? 0) + (c.calc_column ?? 0), <Table2 />, `${c.calc_column ?? 0} calculated`],
    ['Measures', c.measure ?? 0, <Sigma />, `${c.calc_group_item ?? 0} calc items · ${c.field_parameter ?? 0} field params`],
    ['RLS roles', c.rls_role ?? 0, <ShieldCheck />, 'row-level security'],
    ['Visuals', c.visual ?? 0, <BarChart3 />, `${c.page ?? 0} pages`],
    ['Semantic models', s.models.length, <FileBarChart2 />, `${c.report ?? 0} reports`],
  ]
  return (
    <Card>
      <button onClick={() => setOpen((o) => !o)} className="flex w-full items-center justify-between px-4 py-3 text-left" aria-expanded={open}>
        <span className="flex items-center gap-2 text-[13px] font-semibold"><Info className="size-4 text-muted-foreground" />Scan details
          <span className="font-normal text-muted-foreground">{s.edges.toLocaleString()} links · {warn.length ? plural(warn.length, 'warning') : 'no warnings'}</span>
        </span>
        <ChevronDown className={cn('size-4 text-muted-foreground transition-transform', open && 'rotate-180')} />
      </button>
      {open && (
        <div className="space-y-5 border-t px-4 py-4 animate-fade-in">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            {stats.map(([label, v, icon, sub]) => (
              <div key={label} className="rounded-md border px-3 py-2.5">
                <div className="flex items-center justify-between text-[11px] font-medium text-muted-foreground"><span>{label}</span><span className="[&_svg]:size-3.5">{icon}</span></div>
                <div className="mt-1 text-xl font-semibold tabular-nums">{v.toLocaleString()}</div>
                <div className="text-[11px] text-muted-foreground">{sub}</div>
              </div>
            ))}
          </div>
          <div className="grid gap-6 md:grid-cols-2">
            <div>
              <div className="mb-2 flex items-center gap-1.5 text-xs font-medium">Match confidence <InfoTip text={GLOSSARY.confidence} /></div>
              <div className="flex h-2 overflow-hidden rounded-full bg-muted">
                <div className="bg-emerald-500" style={{ width: `${((conf.high ?? 0) / confTotal) * 100}%` }} />
                <div className="bg-yellow-400" style={{ width: `${((conf.medium ?? 0) / confTotal) * 100}%` }} />
                <div className="bg-red-500" style={{ width: `${((conf.low ?? 0) / confTotal) * 100}%` }} />
              </div>
              <div className="mt-2 flex gap-4 text-xs text-muted-foreground">
                <span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-emerald-500" />High {conf.high ?? 0}</span>
                <span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-yellow-400" />Medium {conf.medium ?? 0}</span>
                <span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-red-500" />Low {conf.low ?? 0}</span>
              </div>
            </div>
            <div>
              <div className="mb-2 text-xs font-medium">Scan warnings</div>
              {warn.length === 0 ? <div className="text-xs text-muted-foreground">None.</div> : (
                <div className="space-y-1">
                  {warn.slice(0, 4).map((w, i) => (
                    <div key={i} className="flex gap-2 text-xs"><AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-amber-500" /><span className="text-muted-foreground"><span className="font-mono text-foreground/80">{w.source}</span> {w.message}</span></div>
                  ))}
                  {warn.length > 4 && <Link to="/settings" className="text-xs text-primary hover:underline">View all {warn.length}</Link>}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </Card>
  )
}

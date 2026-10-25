import * as React from 'react'
import { ChevronDown, ChevronRight, Filter, LayoutPanelTop, FileBarChart2, ShieldAlert, Workflow } from 'lucide-react'
import type { ImpactEntry, ImpactResult } from '@/lib/api'
import { useApp } from '@/lib/store'
import { meta } from '@/lib/types'
import { cn, plural } from '@/lib/utils'
import { Card, ConfidenceBadge, EmptyState, ImpactBadge, Stat, Tabs, TypeIcon } from './ui'
import { LineageGraph } from './LineageGraph'

export function ImpactStats({ r }: { r: ImpactResult }) {
  const s = r.summary
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
      <Stat label="Impacted objects" value={s.total} sub={`${s.breaks} break · ${s.values_may_change} may change`} tone="brand" />
      <Stat label="Visuals" value={s.visuals} sub={`${s.visuals_breaking} will break`} tone={s.visuals_breaking ? 'red' : undefined} />
      <Stat label="Reports / pages" value={`${s.reports} / ${s.pages}`} sub="containing impacted visuals" />
      <Stat label="Measures" value={s.measures} sub={`${s.calc_columns} calc cols · ${s.calc_group_items} calc items`} />
      <Stat label="RLS roles" value={s.rls_roles} sub={s.rls_roles ? 'security filters affected' : 'none affected'} tone={s.rls_roles ? 'red' : 'green'} />
      <Stat label="Confidence" value={s.low_confidence ? `${s.low_confidence} low` : s.medium_confidence ? `${s.medium_confidence} med` : 'High'}
        sub={s.low_confidence || s.medium_confidence ? 'naming / fuzzy matches on path' : 'all exact matches'} tone={s.low_confidence ? 'amber' : 'green'} />
    </div>
  )
}

function Row({ e, sub, right }: { e: ImpactEntry; sub?: React.ReactNode; right?: React.ReactNode }) {
  const { openNode } = useApp()
  return (
    <button onClick={() => openNode(e.id)} className="group flex w-full items-start gap-3 rounded-md px-2.5 py-2 text-left hover:bg-muted/60">
      <TypeIcon type={e.type} className="mt-0.5 size-6" />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate text-[13px] font-medium">{e.name}</span>
          {right}
        </div>
        <div className="truncate text-[11.5px] text-muted-foreground" title={e.path.join(' → ')}>{sub ?? e.path.slice(1, -1).join(' → ') ?? e.parent}</div>
      </div>
      <div className="flex shrink-0 items-center gap-1.5 pt-0.5">
        {e.confidence !== 'high' && <ConfidenceBadge c={e.confidence} />}
        <ImpactBadge impact={e.impact} />
      </div>
    </button>
  )
}

function ReportsTree({ r }: { r: ImpactResult }) {
  const [closed, setClosed] = React.useState<Set<string>>(new Set())
  const toggle = (id: string) => setClosed((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n })
  if (!r.reports.length) return <EmptyState icon={<FileBarChart2 />} title="No report visuals affected">Nothing in the scanned reports uses this column, directly or via measures.</EmptyState>
  return (
    <div className="space-y-3 p-3">
      {r.reports.map((rep) => (
        <div key={rep.id} className="rounded-lg border">
          <button onClick={() => toggle(rep.id)} className="flex w-full items-center gap-2.5 px-3 py-2.5 text-left">
            {closed.has(rep.id) ? <ChevronRight className="size-4 text-muted-foreground" /> : <ChevronDown className="size-4 text-muted-foreground" />}
            <TypeIcon type="report" className="size-6" />
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-semibold">{rep.name}</div>
              <div className="text-[11px] text-muted-foreground">{plural(rep.visual_count, 'visual')} on {plural(rep.pages.length, 'page')} · model {rep.model}</div>
            </div>
            {rep.report_filter && <span className="flex items-center gap-1 rounded bg-muted px-1.5 py-0.5 text-[10.5px]"><Filter className="size-3" />report filter</span>}
            <ImpactBadge impact={rep.impact} />
          </button>
          {!closed.has(rep.id) && (
            <div className="border-t px-2 py-2">
              {rep.pages.map((p) => (
                <div key={p.id} className="mb-1">
                  <div className="flex items-center gap-2 px-2 py-1.5 text-xs font-medium text-muted-foreground">
                    <LayoutPanelTop className="size-3.5" />{p.name}
                    <span className="font-normal">· {p.visuals.length}/{p.total_visuals} visuals</span>
                    {p.page_filter && <span className="ml-1 flex items-center gap-1 rounded bg-amber-500/10 px-1.5 py-0.5 text-[10.5px] text-amber-700 dark:text-amber-400"><Filter className="size-3" />page filter {p.page_filter.impact === 'breaks' ? 'breaks' : 'affected'}</span>}
                  </div>
                  <div className="ml-3 border-l pl-2">
                    {p.visuals.map((v) => (
                      <Row key={v.id} e={v}
                        right={<span className="rounded bg-muted px-1.5 text-[10.5px] text-muted-foreground">{v.visual_type}</span>}
                        sub={<>via <span className="font-mono">{v.via_display}</span>{v.usage && <> · used as <b className="font-medium text-foreground/80">{v.usage}</b></>}</>} />
                    ))}
                    {!p.visuals.length && <div className="px-2.5 py-1.5 text-xs text-muted-foreground">Only the page filter is affected (all visuals on the page are filtered by it).</div>}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

const MODEL_GROUPS: [string, string][] = [
  ['rls_role', 'Row-level security roles'], ['measure', 'Measures'], ['calc_column', 'Calculated columns'],
  ['calc_group_item', 'Calculation group items'], ['field_parameter', 'Field parameters'], ['pbi_model_column', 'Power BI model columns'],
]
const WH_GROUPS: [string, string][] = [
  ['snowflake_view_column', 'Snowflake view columns'], ['dbt_model_column', 'dbt model columns'], ['snowflake_table_column', 'Snowflake table columns'],
]

function GroupList({ r, groups }: { r: ImpactResult; groups: [string, string][] }) {
  const present = groups.filter(([t]) => r.groups[t]?.length)
  if (!present.length) return <EmptyState icon={<Workflow />} title="Nothing here" />
  return (
    <div className="space-y-4 p-3">
      {present.map(([t, label]) => (
        <div key={t}>
          <div className={cn('mb-1 flex items-center gap-2 px-2 text-xs font-semibold uppercase tracking-wide', t === 'rls_role' ? 'text-rose-600 dark:text-rose-400' : 'text-muted-foreground')}>
            {t === 'rls_role' && <ShieldAlert className="size-3.5" />}{label} <span className="font-normal">({r.groups[t].length})</span>
          </div>
          {r.groups[t].map((e) => <Row key={e.id} e={e} sub={e.type === 'measure' || e.type === 'calc_column' ? `${e.parent} · ${e.path.length - 1} hop${e.path.length > 2 ? 's' : ''} · ${e.reason || 'reference'}` : undefined} />)}
        </div>
      ))}
    </div>
  )
}

export function ImpactBody({ r }: { r: ImpactResult }) {
  const [tab, setTab] = React.useState<'reports' | 'model' | 'warehouse'>('reports')
  const modelCount = MODEL_GROUPS.reduce((a, [t]) => a + (r.groups[t]?.length ?? 0), 0)
  const whCount = WH_GROUPS.reduce((a, [t]) => a + (r.groups[t]?.length ?? 0), 0)
  return (
    <div className="grid gap-6">
      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b px-4 py-3">
          <div>
            <div className="text-sm font-semibold">Lineage map</div>
            <div className="text-xs text-muted-foreground">{r.graph.nodes.length} objects{r.graph.truncated && ` (nearest ${r.graph.nodes.length} of ${r.graph.total})`} in swim-lanes from warehouse to visuals. Groups collapse automatically; click a count to expand.</div>
          </div>
        </div>
        <LineageGraph graph={r.graph} mode="impact" height={Math.min(760, Math.max(540, 160 + r.graph.nodes.length * 9))} />
      </Card>
      <Card className="flex max-h-[720px] flex-col">
        <Tabs value={tab} onChange={setTab} tabs={[
          { value: 'reports', label: 'Reports & visuals', count: r.summary.visuals },
          { value: 'model', label: 'Semantic model', count: modelCount },
          { value: 'warehouse', label: 'Warehouse', count: whCount },
        ]} />
        <div className="min-h-0 flex-1 overflow-y-auto scrollbar-thin">
          {tab === 'reports' && <ReportsTree r={r} />}
          {tab === 'model' && <GroupList r={r} groups={MODEL_GROUPS} />}
          {tab === 'warehouse' && <GroupList r={r} groups={WH_GROUPS} />}
        </div>
      </Card>

    </div>
  )
}

export function StartChip({ e, onRemove }: { e: ImpactEntry; onRemove?: () => void }) {
  const m = meta(e.type)
  return (
    <span className="inline-flex items-center gap-2 rounded-lg border bg-card py-1 pl-1 pr-2 shadow-soft">
      <TypeIcon type={e.type} className="size-6" />
      <span className="text-left leading-tight">
        <span className="block font-mono text-[12.5px] font-semibold">{e.display}</span>
        <span className="block text-[10.5px] text-muted-foreground">{m.label}</span>
      </span>
      {onRemove && <button onClick={onRemove} className="ml-1 text-muted-foreground hover:text-foreground">×</button>}
    </span>
  )
}

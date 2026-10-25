import * as React from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { BarChart3, ChevronDown, ChevronRight, Database, LayoutPanelTop, Radar, Route as RouteIcon } from 'lucide-react'
import { api, type UpstreamResult } from '@/lib/api'
import { useApp } from '@/lib/store'
import { meta } from '@/lib/types'
import { cn } from '@/lib/utils'
import { Button, Card, CardHeader, ConfidenceBadge, EmptyState, ErrorBox, PageHeader, Spinner, Stat, TypeIcon, useAsync } from '@/components/ui'
import { NodeSearch } from '@/components/NodeSearch'
import { LineageGraph } from '@/components/LineageGraph'

const ORDER = ['visual', 'page', 'report', 'rls_role', 'field_parameter', 'calc_group_item', 'measure', 'calc_column', 'pbi_model_column', 'snowflake_view_column', 'dbt_model_column', 'snowflake_table_column', 'dbt_source_column']

function ReportPicker({ selected, onPick }: { selected: string | null; onPick: (id: string) => void }) {
  const { data, loading } = useAsync(() => api.reports(), [])
  const [open, setOpen] = React.useState<Set<string>>(new Set())
  React.useEffect(() => {
    if (data) setOpen(new Set(data.flatMap((r) => [r.id, ...r.pages.slice(0, 1).map((p) => p.id)])))
  }, [data])
  const toggle = (id: string) => setOpen((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n })
  if (loading) return <div className="p-6"><Spinner /></div>
  return (
    <div className="space-y-1 p-2 text-[13px]">
      {data?.map((r) => (
        <div key={r.id}>
          <div className="flex items-center">
            <button onClick={() => toggle(r.id)} className="p-1 text-muted-foreground">{open.has(r.id) ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}</button>
            <button onClick={() => onPick(r.id)} className={cn('flex flex-1 items-center gap-2 rounded px-1.5 py-1 text-left font-semibold hover:bg-muted', selected === r.id && 'bg-accent text-accent-foreground')}>
              <TypeIcon type="report" className="size-5" /> {r.name}
            </button>
          </div>
          {open.has(r.id) && r.pages.map((p) => (
            <div key={p.id} className="ml-5">
              <div className="flex items-center">
                <button onClick={() => toggle(p.id)} className="p-1 text-muted-foreground">{open.has(p.id) ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}</button>
                <button onClick={() => onPick(p.id)} className={cn('flex flex-1 items-center gap-2 rounded px-1.5 py-1 text-left hover:bg-muted', selected === p.id && 'bg-accent text-accent-foreground')}>
                  <LayoutPanelTop className="size-3.5 text-muted-foreground" /> {p.name} <span className="text-[11px] text-muted-foreground">{p.visuals.length}</span>
                </button>
              </div>
              {open.has(p.id) && (
                <div className="ml-6 border-l pl-1.5">
                  {p.visuals.map((v) => (
                    <button key={v.id} onClick={() => onPick(v.id)} className={cn('flex w-full items-center gap-2 rounded px-1.5 py-1 text-left hover:bg-muted', selected === v.id && 'bg-accent font-medium text-accent-foreground')}>
                      <BarChart3 className="size-3.5 text-muted-foreground" /> <span className="truncate">{v.name}</span>
                      <span className="ml-auto shrink-0 text-[10.5px] text-muted-foreground">{v.visual_type}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}

export default function Upstream() {
  const [params, setParams] = useSearchParams()
  const id = params.get('id')
  const { version, openNode } = useApp()
  const nav = useNavigate()
  const [res, setRes] = React.useState<UpstreamResult | null>(null)
  const [err, setErr] = React.useState<string | null>(null)
  const [loading, setLoading] = React.useState(false)
  React.useEffect(() => {
    if (!id) { setRes(null); return }
    setLoading(true); setErr(null)
    api.upstream(id).then((r) => { setRes(r); setLoading(false) }, (e) => { setErr(String(e.message)); setLoading(false) })
  }, [id, version])
  const pick = (v: string) => setParams({ id: v })

  return (
    <div className="space-y-5">
      <PageHeader icon={<RouteIcon />} title="Upstream Trace" description="Where does this visual, measure or column really come from? Walks back through DAX, Power Query, Snowflake views and dbt to the raw sources." />
      <div className="grid gap-6 xl:grid-cols-12">
        <Card className="flex max-h-[760px] flex-col xl:col-span-3">
          <div className="border-b p-3"><NodeSearch placeholder="Search any object…" onSelect={(n) => pick(n.id)} /></div>
          <div className="px-4 pt-3 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Reports</div>
          <div className="min-h-0 flex-1 overflow-y-auto scrollbar-thin"><ReportPicker selected={id} onPick={pick} /></div>
        </Card>
        <div className="space-y-5 xl:col-span-9">
          {err && <ErrorBox error={err} />}
          {!id && <Card><EmptyState icon={<RouteIcon />} title="Pick a visual, page or report">Choose from the report tree on the left, or search for any measure or column.</EmptyState></Card>}
          {id && loading && !res && <div className="flex h-64 items-center justify-center"><Spinner className="size-6" /></div>}
          {res && res.start && (
            <>
              <Card className="flex flex-wrap items-center gap-4 p-4">
                <TypeIcon type={res.start.type} className="size-10" />
                <div className="min-w-0 flex-1">
                  <div className="text-xs text-muted-foreground">{meta(res.start.type).label} · {res.start.container}</div>
                  <div className="truncate text-lg font-semibold">{res.start.display}</div>
                </div>
                <Button variant="outline" onClick={() => openNode(res.start!.id)}>Details</Button>
                {res.roots.length > 0 && <Button onClick={() => nav(`/impact?id=${encodeURIComponent(res.roots[0].id)}`)}><Radar /> Impact of a root column</Button>}
              </Card>
              <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
                <Stat label="Upstream objects" value={res.summary.total} tone="brand" />
                <Stat label="Measures" value={res.summary.measures} />
                <Stat label="PBI columns" value={res.summary.pbi_columns} />
                <Stat label="View columns" value={res.summary.view_columns} />
                <Stat label="dbt columns" value={res.summary.dbt_columns} />
                <Stat label="Source columns" value={res.summary.source_columns} />
              </div>
              <div className="grid gap-6 lg:grid-cols-2">
                <Card>
                  <CardHeader icon={<Database />} title="Root sources" description="Furthest-upstream columns (dbt sources / raw tables)" />
                  <div className="max-h-96 overflow-y-auto px-3 pb-3 scrollbar-thin">
                    {res.roots.length === 0 && <div className="px-2 pb-2 text-sm text-muted-foreground">None found</div>}
                    {res.roots.map((e) => (
                      <button key={e.id} onClick={() => openNode(e.id)} className="flex w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-left hover:bg-muted/60">
                        <TypeIcon type={e.type} className="size-6" />
                        <span className="font-mono text-[12.5px]">{e.display}</span>
                        <span className="ml-auto"><ConfidenceBadge c={e.confidence} /></span>
                      </button>
                    ))}
                  </div>
                </Card>
                <Card>
                  <CardHeader icon={<RouteIcon />} title="Everything upstream" description="Grouped by layer" />
                  <div className="max-h-96 space-y-3 overflow-y-auto px-3 pb-3 scrollbar-thin">
                    {ORDER.filter((t) => res.groups[t]?.length).map((t) => (
                      <div key={t}>
                        <div className="px-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{meta(t).label} ({res.groups[t].length})</div>
                        {res.groups[t].map((e) => (
                          <button key={e.id} onClick={() => openNode(e.id)} className="flex w-full items-center gap-2.5 rounded-md px-2 py-1 text-left hover:bg-muted/60">
                            <TypeIcon type={e.type} className="size-5" />
                            <span className="truncate text-[12.5px]">{e.display}</span>
                            <span className="ml-auto shrink-0 text-[11px] text-muted-foreground">{e.depth} hop{e.depth === 1 ? '' : 's'}</span>
                          </button>
                        ))}
                      </div>
                    ))}
                  </div>
                </Card>
              </div>
            </>
          )}
        </div>
      </div>
      {res && res.start && (
        <Card className="overflow-hidden">
          <div className="border-b px-4 py-3">
            <div className="text-sm font-semibold">Upstream lineage map</div>
            <div className="text-xs text-muted-foreground">{res.graph.nodes.length} objects feeding <span className="font-mono">{res.start.display}</span>, from sources on the left to the selected object on the right.</div>
          </div>
          <LineageGraph graph={res.graph} mode="upstream" height={Math.min(720, Math.max(420, 160 + res.graph.nodes.length * 10))} focusId={res.start.id} />
        </Card>
      )}
    </div>
  )
}

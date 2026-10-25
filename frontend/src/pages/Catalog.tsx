import * as React from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { ArrowDown, ArrowUp, Library, Radar, Route as RouteIcon, Search, Unplug } from 'lucide-react'
import { api, type CatalogRow } from '@/lib/api'
import { useApp } from '@/lib/store'
import { meta } from '@/lib/types'
import { cn } from '@/lib/utils'
import { Badge, Card, ErrorBox, Input, PageHeader, Spinner, TypeIcon, useAsync } from '@/components/ui'

const KINDS: { value: string; label: string; types: string[] | null }[] = [
  { value: 'all', label: 'All', types: null },
  { value: 'warehouse', label: 'Warehouse', types: ['dbt_source_column', 'dbt_model_column', 'snowflake_view_column', 'snowflake_table_column'] },
  { value: 'pbi', label: 'PBI columns', types: ['pbi_model_column', 'calc_column'] },
  { value: 'measures', label: 'Measures & calc', types: ['measure', 'calc_group_item', 'field_parameter'] },
  { value: 'rls', label: 'RLS', types: ['rls_role'] },
  { value: 'visuals', label: 'Visuals', types: ['visual', 'page', 'report'] },
]
type SortKey = 'display' | 'type_label' | 'container' | 'downstream_visuals' | 'downstream_measures' | 'upstream'

export default function Catalog() {
  const { version, openNode } = useApp()
  const nav = useNavigate()
  const [params, setParams] = useSearchParams()
  const { data, error, loading } = useAsync(() => api.catalog(), [version])
  const { data: summary } = useAsync(() => api.summary(), [version])
  const kind = params.get('kind') ?? 'all'
  const unused = params.get('unused')
  const [q, setQ] = React.useState('')
  const [sort, setSort] = React.useState<{ k: SortKey; desc: boolean }>({ k: 'downstream_visuals', desc: true })

  const rows = React.useMemo(() => {
    if (!data) return []
    let r: CatalogRow[] = data.rows
    const kt = KINDS.find((k) => k.value === kind)?.types
    if (kt) r = r.filter((x) => kt.includes(x.type))
    if (unused && summary) {
      const set = new Set((unused === 'gold' ? summary.unused_gold_columns : summary.unused_pbi_objects).map((u) => u.id))
      r = r.filter((x) => set.has(x.id))
    }
    if (q.trim()) {
      const terms = q.toLowerCase().split(/\s+/)
      r = r.filter((x) => { const h = `${x.display} ${x.container} ${x.description} ${x.data_type} ${x.visual_type}`.toLowerCase(); return terms.every((t) => h.includes(t)) })
    }
    const { k, desc } = sort
    return [...r].sort((a, b) => {
      const va = a[k], vb = b[k]
      const c = typeof va === 'number' ? (va as number) - (vb as number) : String(va).localeCompare(String(vb))
      return desc ? -c : c
    })
  }, [data, kind, q, sort, unused, summary])

  const counts = React.useMemo(() => Object.fromEntries(KINDS.map((k) => [k.value, data ? (k.types ? data.rows.filter((r) => k.types!.includes(r.type)).length : data.rows.length) : 0])), [data])
  const Th = ({ k, children, right }: { k: SortKey; children: React.ReactNode; right?: boolean }) => (
    <th className={cn('cursor-pointer select-none py-2.5 font-medium hover:text-foreground', right && 'text-right')} onClick={() => setSort((s) => ({ k, desc: s.k === k ? !s.desc : k !== 'display' }))}>
      <span className="inline-flex items-center gap-1">{children}{sort.k === k && (sort.desc ? <ArrowDown className="size-3" /> : <ArrowUp className="size-3" />)}</span>
    </th>
  )
  const setKind = (v: string) => { const p = new URLSearchParams(params); p.set('kind', v); p.delete('unused'); setParams(p) }

  return (
    <div className="space-y-5">
      <PageHeader icon={<Library />} title="Catalog" description="Every object LineageLens found, with how much depends on it." />
      <Card>
        <div className="flex flex-wrap items-center gap-3 border-b px-4 py-3">
          <div className="flex flex-wrap gap-1">
            {KINDS.map((k) => (
              <button key={k.value} onClick={() => setKind(k.value)} className={cn('rounded-md px-3 py-1.5 text-[13px] font-medium', kind === k.value && !unused ? 'bg-accent text-accent-foreground' : 'text-muted-foreground hover:bg-muted')}>
                {k.label} <span className="ml-0.5 text-[11px] opacity-70">{counts[k.value]}</span>
              </button>
            ))}
          </div>
          {unused && <Badge className="border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-400">Unused {unused === 'gold' ? 'warehouse columns' : 'PBI objects'} <button className="ml-1" onClick={() => setKind(kind)}>×</button></Badge>}
          <div className="relative ml-auto w-72">
            <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter…" className="pl-8" />
          </div>
        </div>
        {error && <div className="p-4"><ErrorBox error={error} /></div>}
        {loading && <div className="flex h-40 items-center justify-center"><Spinner /></div>}
        {data && (
          <div className="max-h-[calc(100vh-260px)] overflow-auto scrollbar-thin">
            <table className="w-full text-sm">
              <thead className="sticky top-0 z-10 bg-card text-left text-[11px] uppercase tracking-wide text-muted-foreground shadow-[0_1px_0_hsl(var(--border))]">
                <tr><th className="w-10" /><Th k="display">Object</Th><Th k="type_label">Type</Th><Th k="container">Container</Th><th className="font-medium">Details</th><Th k="upstream" right>Upstream</Th><Th k="downstream_measures" right>Measures</Th><Th k="downstream_visuals" right>Visuals</Th><th className="w-20" /></tr>
              </thead>
              <tbody>
                {rows.slice(0, 600).map((r) => (
                  <tr key={r.id} className="group cursor-pointer border-t hover:bg-muted/40" onClick={() => openNode(r.id)}>
                    <td className="py-2 pl-4"><TypeIcon type={r.type} className="size-6" /></td>
                    <td className="max-w-xs py-2"><div className="truncate font-mono text-[12.5px] font-medium">{r.display}</div>{r.description && <div className="truncate text-[11px] text-muted-foreground">{r.description}</div>}</td>
                    <td className="whitespace-nowrap text-[12.5px]" style={{ color: meta(r.type).hex }}>{r.type_label}</td>
                    <td className="text-[12.5px] text-muted-foreground">{r.container}</td>
                    <td className="max-w-[16rem] text-[12px] text-muted-foreground">
                      <div className="flex flex-wrap gap-1">
                        {r.data_type && <Badge className="bg-muted font-mono">{r.data_type}</Badge>}
                        {r.visual_type && <Badge className="bg-muted">{r.visual_type}</Badge>}
                        {r.transform && <Badge className="bg-muted">{r.transform}</Badge>}
                        {r.match_method && <Badge className="bg-muted">match: {r.match_method}</Badge>}
                        {r.unmatched && <Badge className="border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-400"><Unplug className="mr-1 size-3" />unmatched</Badge>}
                      </div>
                    </td>
                    <td className="text-right tabular-nums text-muted-foreground">{r.upstream}</td>
                    <td className="text-right tabular-nums">{r.downstream_measures || <span className="text-muted-foreground/50">0</span>}</td>
                    <td className="text-right font-medium tabular-nums">{r.downstream_visuals || <span className="font-normal text-muted-foreground/50">0</span>}</td>
                    <td className="pr-3 text-right">
                      <span className="invisible inline-flex gap-1 group-hover:visible">
                        <button title="Impact" className="rounded p-1 hover:bg-background" onClick={(e) => { e.stopPropagation(); nav(`/impact?id=${encodeURIComponent(r.id)}`) }}><Radar className="size-3.5" /></button>
                        <button title="Upstream" className="rounded p-1 hover:bg-background" onClick={(e) => { e.stopPropagation(); nav(`/upstream?id=${encodeURIComponent(r.id)}`) }}><RouteIcon className="size-3.5" /></button>
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {rows.length > 600 && <div className="p-3 text-center text-xs text-muted-foreground">Showing 600 of {rows.length}. Refine the filter.</div>}
            {rows.length === 0 && <div className="p-10 text-center text-sm text-muted-foreground">No objects match.</div>}
          </div>
        )}
      </Card>
    </div>
  )
}

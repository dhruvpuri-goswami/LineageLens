import * as React from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowDownRight, ArrowUpLeft, FileCode2, Radar, Route, X, ChevronRight } from 'lucide-react'
import { useApp } from '@/lib/store'
import { api, type LinkRef, type NodeDetail } from '@/lib/api'
import { meta } from '@/lib/types'
import { Button, ConfidenceBadge, ImpactBadge, Spinner, TypeBadge, TypeIcon, ErrorBox } from './ui'
import { Code } from './Code'

const LABELS: Record<string, string> = {
  data_type: 'Data type', transform: 'Transform', expression: 'Expression', relation: 'Relation', materialized: 'Materialization',
  source_column: 'Source column (M)', upstream_relation: 'Upstream relation', upstream_column: 'Upstream column', match_method: 'Match method',
  m_connector: 'Connector', storage_mode: 'Storage mode', format_string: 'Format string', display_folder: 'Display folder',
  visual_type: 'Visual type', page: 'Page', report: 'Report', model: 'Semantic model', format: 'Format', ordinal: 'Page order',
  hidden: 'Hidden', sort_by: 'Sort by column', model_description: 'Model description', view_kind: 'Object kind', tables: 'Tables', roles: 'Roles',
}
const HIDE = new Set(['layer', 'fields', 'filters', 'position', 'page_id', 'dbt_unique_id', 'schema', 'database', 'table', 'relationships', 'resource_type', 'external', 'model_ref_kind'])

function LinkList({ title, icon, links }: { title: string; icon: React.ReactNode; links: LinkRef[] }) {
  const { openNode } = useApp()
  if (!links.length) return null
  return (
    <section>
      <h4 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground [&_svg]:size-3.5">{icon}{title} <span className="font-normal">({links.length})</span></h4>
      <div className="divide-y rounded-md border">
        {links.map((l) => (
          <button key={l.id} onClick={() => openNode(l.id)} className="flex w-full items-center gap-2.5 px-3 py-2 text-left hover:bg-muted/60">
            <TypeIcon type={l.type} className="size-6" />
            <div className="min-w-0 flex-1">
              <div className="truncate text-[13px] font-medium">{l.display}</div>
              {l.reason && <div className="truncate text-[11px] text-muted-foreground">{l.reason}</div>}
            </div>
            {l.confidence !== 'high' && <ConfidenceBadge c={l.confidence} />}
            {l.impact !== 'breaks' && <span className="text-[10px] text-amber-600 dark:text-amber-400">filter</span>}
            <ChevronRight className="size-3.5 text-muted-foreground" />
          </button>
        ))}
      </div>
    </section>
  )
}

export function DetailDrawer() {
  const { drawerId, openNode } = useApp()
  const nav = useNavigate()
  const [d, setD] = React.useState<NodeDetail | null>(null)
  const [err, setErr] = React.useState<string | null>(null)
  React.useEffect(() => {
    if (!drawerId) return
    setD(null)
    setErr(null)
    api.node(drawerId).then(setD, (e) => setErr(String(e.message)))
  }, [drawerId])
  React.useEffect(() => {
    const h = (e: KeyboardEvent) => e.key === 'Escape' && openNode(null)
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [openNode])
  if (!drawerId) return null

  const terms = d ? [d.name, ...d.upstream.map((u) => u.display.split(/[.[\]]/).filter(Boolean).pop() ?? '')] : []
  const extra = d ? Object.entries(d.data).filter(([k, v]) => !HIDE.has(k) && v !== '' && v !== null && v !== undefined && typeof v !== 'object') : []
  const lang = d?.code_lang === 'm' ? 'm' : d?.code_lang === 'dax' ? 'dax' : d?.code_lang === 'json' ? 'json' : 'sql'
  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/20 animate-fade-in" onClick={() => openNode(null)} />
      <aside className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[600px] flex-col border-l bg-background shadow-2xl animate-slide-in">
        <div className="flex items-start gap-3 border-b px-5 py-4">
          {d ? <TypeIcon type={d.type} className="size-9 [&_svg]:size-4" /> : <Spinner />}
          <div className="min-w-0 flex-1">
            <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{d ? meta(d.type).label : 'Loading'}</div>
            <h2 className="truncate text-base font-semibold" title={d?.display}>{d?.name ?? drawerId}</h2>
            {d && <div className="truncate text-xs text-muted-foreground">{d.type === 'visual' ? `${d.container} › ${d.parent}` : d.data.relation ?? d.parent}</div>}
          </div>
          <Button variant="ghost" size="icon" onClick={() => openNode(null)}><X /></Button>
        </div>
        {err && <div className="p-5"><ErrorBox error={err} /></div>}
        {d && (
          <div className="flex-1 space-y-5 overflow-y-auto px-5 py-4 scrollbar-thin">
            <div className="flex flex-wrap items-center gap-2">
              <TypeBadge type={d.type} />
              {d.data.match_method && d.data.match_method !== 'exact' && <ConfidenceBadge c={d.data.match_method.includes('fuzzy') ? 'low' : d.data.match_method.includes('case') ? 'high' : 'medium'} />}
              {d.data.unmatched && <ImpactBadge impact="values_may_change" className="!text-xs" />}
              {(d.counts.visuals ?? 0) > 0 && <span className="text-xs text-muted-foreground">feeds <b className="text-foreground">{d.counts.visuals}</b> visuals · <b className="text-foreground">{d.counts.measures ?? 0}</b> measures</span>}
            </div>
            <div className="flex gap-2">
              <Button size="sm" onClick={() => { openNode(null); nav(`/impact?id=${encodeURIComponent(d.id)}`) }}><Radar /> Impact analysis</Button>
              <Button size="sm" variant="outline" onClick={() => { openNode(null); nav(`/upstream?id=${encodeURIComponent(d.id)}`) }}><Route /> Trace upstream</Button>
            </div>
            {d.description && <p className="rounded-md bg-muted/50 px-3 py-2 text-sm">{d.description}</p>}
            {extra.length > 0 && (
              <dl className="grid grid-cols-[150px_1fr] gap-x-3 gap-y-1.5 text-[13px]">
                {extra.map(([k, v]) => (
                  <React.Fragment key={k}>
                    <dt className="text-muted-foreground">{LABELS[k] ?? k.replace(/_/g, ' ')}</dt>
                    <dd className="break-words font-mono text-[12px]">{String(v)}</dd>
                  </React.Fragment>
                ))}
              </dl>
            )}
            {d.type === 'visual' && Array.isArray(d.data.fields) && (
              <section>
                <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Fields used</h4>
                <div className="overflow-hidden rounded-md border">
                  <table className="w-full text-[12.5px]">
                    <thead className="bg-muted/50 text-left text-[11px] uppercase text-muted-foreground"><tr><th className="px-3 py-1.5">Field</th><th className="px-3 py-1.5">Kind</th><th className="px-3 py-1.5">Used as</th></tr></thead>
                    <tbody>
                      {d.data.fields.map((f: any, i: number) => (
                        <tr key={i} className="border-t"><td className="px-3 py-1.5 font-mono">{f.entity}[{f.property}]</td><td className="px-3 py-1.5">{f.kind}{f.aggregation ? ` · ${f.aggregation}` : ''}</td><td className="px-3 py-1.5">{f.usage}</td></tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            )}
            {Array.isArray(d.data.filters) && d.data.filters.length > 0 && (
              <div className="text-[13px]"><span className="text-muted-foreground">Filters: </span><span className="font-mono text-[12px]">{d.data.filters.join(', ')}</span></div>
            )}
            {d.type === 'rls_role' && d.data.filters && typeof d.data.filters === 'object' && (
              <section className="space-y-2">
                <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Table filters</h4>
                {Object.entries(d.data.filters as Record<string, string>).map(([t, expr]) => (
                  <div key={t}><div className="mb-1 text-xs font-medium">{t}</div><Code code={expr} lang="dax" highlight={terms} /></div>
                ))}
              </section>
            )}
            {d.code && d.type !== 'rls_role' && (
              <section>
                <h4 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground"><FileCode2 className="size-3.5" />
                  {lang === 'dax' ? 'DAX' : lang === 'm' ? 'Power Query (M)' : lang === 'json' ? 'Visual definition' : 'SQL'}
                </h4>
                <Code code={d.code} lang={lang} highlight={terms} maxHeight={420} />
              </section>
            )}
            <LinkList title="Upstream" icon={<ArrowUpLeft />} links={d.upstream} />
            <LinkList title="Downstream" icon={<ArrowDownRight />} links={d.downstream} />
            {d.file && <div className="break-all border-t pt-3 font-mono text-[11px] text-muted-foreground">{d.file}</div>}
          </div>
        )}
      </aside>
    </>
  )
}

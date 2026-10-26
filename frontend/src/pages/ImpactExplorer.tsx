import * as React from 'react'
import { useSearchParams } from 'react-router-dom'
import { Download, FileJson, FileSpreadsheet, FileText, Globe, Pencil, Radar, Trash2, Type, Calculator } from 'lucide-react'
import { api, type ChangeType, type ImpactResult } from '@/lib/api'
import { useApp } from '@/lib/store'
import { Button, Card, EmptyState, ErrorBox, PageHeader, Segmented, Spinner, TypeIcon } from '@/components/ui'
import { NodeSearch } from '@/components/NodeSearch'
import { ImpactBody, ImpactStats, StartChip } from '@/components/ImpactView'
import { WAREHOUSE } from '@/lib/types'
import { pushRecent } from '@/lib/recent'

export const CHANGE_OPTIONS: { value: ChangeType; label: React.ReactNode; hint: string }[] = [
  { value: 'drop', label: <><Trash2 />Drop</>, hint: 'Column removed: every dependent object breaks' },
  { value: 'rename', label: <><Pencil />Rename</>, hint: 'Column renamed: references break unless updated' },
  { value: 'type', label: <><Type />Type change</>, hint: 'Data type changes: values / formatting may change' },
  { value: 'logic', label: <><Calculator />Logic change</>, hint: 'Calculation changes: downstream values change' },
]

function ExportMenu({ ids, change }: { ids: string[]; change: ChangeType }) {
  const [open, setOpen] = React.useState(false)
  const items = [
    { f: 'html', label: 'HTML report', icon: Globe, desc: 'Self-contained, shareable' },
    { f: 'xlsx', label: 'Excel workbook', icon: FileSpreadsheet, desc: 'Sheets per object type' },
    { f: 'csv', label: 'CSV', icon: FileText, desc: 'Flat list of impacted objects' },
    { f: 'json', label: 'JSON', icon: FileJson, desc: 'Full result for automation' },
  ]
  return (
    <div className="relative">
      <Button variant="outline" onClick={() => setOpen((o) => !o)} onBlur={() => setTimeout(() => setOpen(false), 150)}><Download /> Export</Button>
      {open && (
        <div className="absolute right-0 z-30 mt-1.5 w-60 rounded-lg border bg-popover p-1 shadow-xl animate-fade-in">
          {items.map(({ f, label, icon: Icon, desc }) => (
            <a key={f} href={api.exportUrl(ids, change, f)} className="flex items-center gap-3 rounded-md px-2.5 py-2 hover:bg-muted">
              <Icon className="size-4 text-muted-foreground" />
              <div><div className="text-sm font-medium">{label}</div><div className="text-[11px] text-muted-foreground">{desc}</div></div>
            </a>
          ))}
        </div>
      )}
    </div>
  )
}

export default function ImpactExplorer() {
  const [params, setParams] = useSearchParams()
  const { byId, version } = useApp()
  const ids = params.getAll('id')
  const change = (params.get('change') as ChangeType) || 'drop'
  const [res, setRes] = React.useState<ImpactResult | null>(null)
  const [err, setErr] = React.useState<string | null>(null)
  const [loading, setLoading] = React.useState(false)
  const key = ids.join('|') + change + version

  React.useEffect(() => {
    if (!ids.length) { setRes(null); return }
    setLoading(true)
    setErr(null)
    ids.forEach((i) => pushRecent(i))
    api.impact(ids, change).then((r) => { setRes(r); setLoading(false) }, (e) => { setErr(String(e.message)); setLoading(false) })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  const update = (nextIds: string[], nextChange = change) => {
    const p = new URLSearchParams()
    nextIds.forEach((i) => p.append('id', i))
    p.set('change', nextChange)
    setParams(p)
  }
  const suggestions = React.useMemo(() => [...byId.values()].filter((n) => WAREHOUSE.includes(n.type) && (n.visuals ?? 0) > 0).sort((a, b) => (b.visuals ?? 0) - (a.visuals ?? 0)).slice(0, 6), [byId])

  return (
    <div className="space-y-5">
      <PageHeader icon={<Radar />} title="Impact Explorer" description="What breaks downstream if this column changes? Traverses dbt → Snowflake → Power BI columns → measures → RLS → visuals."
        actions={ids.length > 0 && <ExportMenu ids={ids} change={change} />} />
      <Card className="p-4">
        <div className="flex flex-wrap items-center gap-3">
          <NodeSearch className="w-full max-w-md" placeholder={ids.length ? 'Add another column…' : 'Search a column, e.g. dim_store.SALES_REGION'} onSelect={(n) => update(ids.includes(n.id) ? ids : [...ids, n.id])} autoFocus={!ids.length} />
          <Segmented value={change} onChange={(v) => update(ids, v)} options={CHANGE_OPTIONS} />
        </div>
        {res && res.start.length > 0 && (
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className="text-xs text-muted-foreground">Changing:</span>
            {res.start.map((s) => <StartChip key={s.id} e={s} onRemove={() => update(ids.filter((i) => i !== s.id))} />)}
            <span className="ml-1 text-xs text-muted-foreground">({res.change_label.toLowerCase()})</span>
          </div>
        )}
      </Card>

      {err && <ErrorBox error={err} />}
      {!ids.length && (
        <Card>
          <EmptyState icon={<Radar />} title="Pick a column to analyse">
            Search above for any dbt, Snowflake or Power BI object. Try one of the most used columns:
          </EmptyState>
          <div className="-mt-6 flex flex-wrap justify-center gap-2 px-6 pb-10">
            {suggestions.map((n) => (
              <button key={n.id} onClick={() => update([n.id])} className="flex items-center gap-2 rounded-md border bg-card px-3 py-2 text-left hover:border-primary/40 hover:bg-accent">
                <TypeIcon type={n.type} className="size-6" />
                <div><div className="font-mono text-[12.5px] font-medium">{n.display}</div><div className="text-[11px] text-muted-foreground">{n.visuals} visuals downstream</div></div>
              </button>
            ))}
          </div>
        </Card>
      )}
      {loading && !res && <div className="flex h-64 items-center justify-center"><Spinner className="size-6" /></div>}
      {res && ids.length > 0 && (
        <div className={loading ? 'pointer-events-none opacity-60 transition-opacity' : 'transition-opacity'}>
          <div className="space-y-5">
            <ImpactStats r={res} />
            <ImpactBody r={res} />
          </div>
        </div>
      )}
    </div>
  )
}

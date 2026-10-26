import * as React from 'react'
import { useNavigate } from 'react-router-dom'
import {
  AlertTriangle, ArrowRight, CheckCircle2, FileArchive, FileBraces, FileCode2, FolderUp, HardDriveUpload, Loader2, Lock,
  Play, Trash2, Upload, XCircle,
} from 'lucide-react'
import { api, uploadFiles, type ScanStatus, type UploadItem, type UploadResult, type UploadSlot, type UploadState } from '@/lib/api'
import { useApp } from '@/lib/store'
import { cn, fmtTime } from '@/lib/utils'
import { Badge, Button, Card, ErrorBox, Input, PageHeader, Spinner } from '@/components/ui'

interface ZoneDef {
  slot: UploadSlot
  title: string
  need: 'Required for dbt' | 'Recommended' | 'Optional'
  icon: React.ReactNode
  what: React.ReactNode
  accept: string
  multiple: boolean
  folder?: boolean
}

const ZONES: ZoneDef[] = [
  { slot: 'manifest', title: 'dbt manifest.json', need: 'Required for dbt', icon: <FileBraces />, accept: '.json', multiple: false,
    what: <>Models, sources and compiled SQL. Run <Code>dbt compile</Code>, then take <Code>target/manifest.json</Code>.</> },
  { slot: 'catalog', title: 'dbt catalog.json', need: 'Recommended', icon: <FileBraces />, accept: '.json', multiple: false,
    what: <>Column names and types from the warehouse. Run <Code>dbt docs generate</Code>, then take <Code>target/catalog.json</Code>.</> },
  { slot: 'sql', title: 'Snowflake view DDL', need: 'Optional', icon: <FileCode2 />, accept: '.sql', multiple: true,
    what: <>Views outside dbt: one or more <Code>.sql</Code> files with <Code>CREATE VIEW</Code>, e.g. from <Code>SELECT GET_DDL('VIEW', …)</Code>.</> },
  { slot: 'powerbi', title: 'Power BI project (PBIP)', need: 'Optional', icon: <FolderUp />, accept: '.zip', multiple: true, folder: true,
    what: <>In Power BI Desktop use <b className="font-medium text-foreground">File › Save as › .pbip</b>, then choose that folder or a <Code>.zip</Code> of it. Gives measures, RLS and visuals.</> },
  { slot: 'pbix', title: 'Power BI .pbix (fallback)', need: 'Optional', icon: <FileArchive />, accept: '.pbix', multiple: true,
    what: <>Legacy report layout only: pages and visuals. Measures, RLS and model columns need the PBIP project.</> },
]

function Code({ children }: { children: React.ReactNode }) {
  return <span className="rounded bg-muted px-1 py-px font-mono text-[11px] text-foreground/90">{children}</span>
}

const fmtSize = (n: number) => (n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1048576).toFixed(1)} MB`)

/** Read every file below dropped folders (drag and drop gives entries, not a flat list). */
async function filesFromDrop(dt: DataTransfer): Promise<UploadItem[]> {
  const entries = Array.from(dt.items ?? []).map((i) => (i.webkitGetAsEntry ? i.webkitGetAsEntry() : null)).filter(Boolean) as FileSystemEntry[]
  if (!entries.length) return Array.from(dt.files).map((f) => ({ file: f, path: f.name }))
  const out: UploadItem[] = []
  const walk = async (e: FileSystemEntry, prefix: string): Promise<void> => {
    if (e.isFile) {
      const f = await new Promise<File>((res, rej) => (e as FileSystemFileEntry).file(res, rej))
      out.push({ file: f, path: prefix + e.name })
    } else if (e.isDirectory) {
      const reader = (e as FileSystemDirectoryEntry).createReader()
      for (;;) {
        const batch = await new Promise<FileSystemEntry[]>((res, rej) => reader.readEntries(res, rej))
        if (!batch.length) break
        for (const c of batch) await walk(c, `${prefix}${e.name}/`)
      }
    }
  }
  for (const e of entries) await walk(e, '')
  return out
}

export default function LoadData() {
  const { refresh } = useApp()
  const nav = useNavigate()
  const [st, setSt] = React.useState<UploadState | null>(null)
  const [err, setErr] = React.useState<string | null>(null)
  const [last, setLast] = React.useState<Partial<Record<UploadSlot, UploadResult[]>>>({})
  const [busy, setBusy] = React.useState<Partial<Record<UploadSlot, number>>>({})
  const [name, setName] = React.useState('')
  const [db, setDb] = React.useState('')
  const [schema, setSchema] = React.useState('')
  const [scan, setScan] = React.useState<ScanStatus | null>(null)
  const [msg, setMsg] = React.useState<{ ok: boolean; text: string } | null>(null)
  const [confirm, setConfirm] = React.useState(false)
  const watching = React.useRef(false)

  const load = React.useCallback(() => api.uploadState().then((s) => { setSt(s); setErr(null) }).catch((e) => setErr(String(e.message))), [])
  React.useEffect(() => { load() }, [load])
  React.useEffect(() => {
    if (st?.workspace && !name) {
      setName(st.workspace.project_name ?? '')
      setDb(st.workspace.default_database ?? '')
      setSchema(st.workspace.default_schema ?? '')
    }
  }, [st?.workspace]) // eslint-disable-line react-hooks/exhaustive-deps

  React.useEffect(() => {
    let alive = true
    const tick = async () => {
      try {
        const s = await api.scanStatus()
        if (!alive) return
        setScan(s)
        if (watching.current && !s.running) {
          watching.current = false
          refresh()
          load()
          setMsg(s.error ? { ok: false, text: s.error } : { ok: true, text: s.message })
        }
      } catch { /* ignore */ }
    }
    tick()
    const t = setInterval(tick, 600)
    return () => { alive = false; clearInterval(t) }
  }, [refresh, load])

  const send = async (slot: UploadSlot, items: UploadItem[]) => {
    if (!st) return
    let list = items
    if (slot === 'powerbi') {
      // Skip what LineageLens never reads (images, the .pbi cache) so it is not uploaded at all.
      const ok = new Set(st.pbip_extensions)
      list = items.filter((it) => {
        const p = it.path.toLowerCase()
        const base = p.split('/').pop() ?? ''
        const ext = base.includes('.') ? base.slice(base.lastIndexOf('.')) : ''
        return !p.split('/').includes('.pbi') && (ext === '.zip' || ok.has(ext) || ok.has(base))
      })
      if (!list.length) {
        setLast((l) => ({ ...l, [slot]: [{ name: items[0]?.path.split('/')[0] ?? 'folder', size: 0, status: 'error', detected: '', message: 'No PBIP files found. Choose the folder that contains the .pbip file.' }] }))
        return
      }
    }
    const total = list.reduce((a, b) => a + b.file.size, 0)
    if (total > st.max_upload_mb * 1048576) {
      setLast((l) => ({ ...l, [slot]: [{ name: list.length === 1 ? list[0].path : `${list.length} files`, size: total, status: 'error', detected: '', message: `Larger than the ${st.max_upload_mb} MB upload limit (LINEAGELENS_MAX_UPLOAD_MB).` }] }))
      return
    }
    setMsg(null)
    setBusy((b) => ({ ...b, [slot]: 0 }))
    try {
      const r = await uploadFiles(slot, list, (f) => setBusy((b) => ({ ...b, [slot]: f })))
      setSt(r.state)
      setLast((l) => ({ ...l, [slot]: r.results.filter((x) => x.status === 'error') }))
    } catch (e: any) {
      setLast((l) => ({ ...l, [slot]: [{ name: list.length === 1 ? list[0].path : `${list.length} files`, size: total, status: 'error', detected: '', message: String(e.message) }] }))
    } finally {
      setBusy((b) => { const n = { ...b }; delete n[slot]; return n })
    }
  }
  const clear = async (slot: UploadSlot) => {
    try { const r = await api.clearUpload(slot); setSt(r.state); setLast((l) => ({ ...l, [slot]: [] })) } catch (e: any) { setErr(String(e.message)) }
  }
  const startScan = async () => {
    setMsg(null)
    try {
      const r = await api.scanUpload({ project_name: name.trim(), default_database: db.trim(), default_schema: schema.trim() })
      setSt(r.state)
      setLast({})
      watching.current = true
    } catch (e: any) { setMsg({ ok: false, text: String(e.message) }) }
  }
  const remove = async () => {
    setConfirm(false)
    setMsg(null)
    try {
      const r = await api.removeUpload()
      setSt(r.state)
      setName(''); setDb(''); setSchema(''); setLast({})
      if (r.rescanning) watching.current = true
      setMsg({ ok: true, text: 'Your uploaded files were deleted.' + (r.rescanning ? ' Loading the default data again.' : '') })
    } catch (e: any) { setMsg({ ok: false, text: String(e.message) }) }
  }
  const activate = async () => {
    setMsg(null)
    try { const r = await api.activateUpload(); setSt(r.state); watching.current = true } catch (e: any) { setMsg({ ok: false, text: String(e.message) }) }
  }

  if (err && !st) return <ErrorBox error={err} />
  if (!st) return <div className="flex h-64 items-center justify-center"><Spinner className="size-6" /></div>

  const staged = Object.values(st.staging).some((x) => x.length > 0)
  const running = !!scan?.running
  const uploading = Object.keys(busy).length > 0
  const pct = scan ? (scan.pct <= 1 ? scan.pct * 100 : scan.pct) : 0
  const ws = st.workspace
  const canScan = staged && !!name.trim() && !running && !uploading && st.allowed

  return (
    <div className="space-y-5">
      <PageHeader title="Load your data" description="Upload your own dbt, Snowflake and Power BI files and scan them. Files are stored on this machine only and never leave it." />
      {!st.allowed && (
        <Card className="flex items-start gap-3 p-4 text-[13px]">
          <Lock className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
          <div>Uploads are turned off on this server (<Code>LINEAGELENS_ALLOW_UPLOAD=false</Code>). Use a <Code>lineagelens.yml</Code> in the inputs folder instead.</div>
        </Card>
      )}
      {ws && (
        <Card className="flex flex-wrap items-center gap-4 p-4">
          <div className="flex size-9 items-center justify-center rounded-md border bg-muted text-muted-foreground"><HardDriveUpload className="size-4" /></div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2 text-[13.5px] font-semibold">
              {ws.project_name || ws.project}
              {ws.active && st.is_upload ? <Badge className="border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400">In use</Badge> : <Badge className="text-muted-foreground">Not in use</Badge>}
            </div>
            <div className="mt-0.5 truncate text-[12px] text-muted-foreground">
              Uploaded {fmtTime(ws.created)} · {fmtSize(ws.bytes)} · <span className="font-mono">{ws.path}</span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {!(ws.active && st.is_upload) && <Button variant="outline" size="sm" onClick={activate} disabled={running}>Use my data</Button>}
            {st.is_upload && <Button variant="outline" size="sm" onClick={() => nav('/')}>Open dashboard <ArrowRight /></Button>}
            {confirm ? (
              <span className="flex items-center gap-2 rounded-md border border-red-500/30 bg-red-500/5 px-2 py-1 text-[12px]">
                Delete all uploaded files{st.is_upload ? ' and go back to the default data' : ''}?
                <Button variant="destructive" size="sm" onClick={remove}>Delete</Button>
                <Button variant="ghost" size="sm" onClick={() => setConfirm(false)}>Cancel</Button>
              </span>
            ) : (
              <Button variant="outline" size="sm" onClick={() => setConfirm(true)} disabled={running} className="text-red-600 dark:text-red-400"><Trash2 /> Remove my data</Button>
            )}
          </div>
        </Card>
      )}
      <div className="grid gap-5 xl:grid-cols-[1fr_340px]">
        <div className="space-y-3">
          {ZONES.map((z) => (
            <DropZone key={z.slot} def={z} disabled={!st.allowed || running} progress={busy[z.slot]}
              staged={st.staging[z.slot]} errors={last[z.slot] ?? []} onFiles={(items) => send(z.slot, items)} onClear={() => clear(z.slot)} />
          ))}
        </div>
        <div className="space-y-4">
          <Card className="space-y-3 p-4 xl:sticky xl:top-4">
            <div>
              <h3 className="text-sm font-semibold">Project</h3>
              <p className="mt-0.5 text-xs text-muted-foreground">Used for the generated <span className="font-mono">lineagelens.yml</span>.</p>
            </div>
            <Field label="Project name" hint="Shown in the sidebar and reports.">
              <Input id="proj-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Sales analytics" maxLength={80} />
            </Field>
            <Field label="Snowflake default database" hint="For view SQL that names tables without a database.">
              <Input id="proj-db" value={db} onChange={(e) => setDb(e.target.value)} placeholder="e.g. ANALYTICS" className="font-mono text-xs" />
            </Field>
            <Field label="Snowflake default schema" hint="For view SQL that names tables without a schema.">
              <Input id="proj-schema" value={schema} onChange={(e) => setSchema(e.target.value)} placeholder="e.g. REPORTING" className="font-mono text-xs" />
            </Field>
            <Button className="w-full" onClick={startScan} disabled={!canScan}>
              {running ? <Loader2 className="animate-spin" /> : <Play />}{running ? 'Scanning…' : ws ? 'Replace my data and scan' : 'Scan'}
            </Button>
            {!staged && !running && <p className="text-[11.5px] text-muted-foreground">Add at least one file to scan.{ws ? ' Scanning replaces the data uploaded before.' : ''}</p>}
            {staged && !name.trim() && <p className="text-[11.5px] text-muted-foreground">Enter a project name to scan.</p>}
            {running && (
              <div>
                <div className="mb-1 flex justify-between text-[11.5px]"><span className="truncate pr-2 text-muted-foreground">{scan?.message}</span><span className="tabular-nums">{Math.round(pct)}%</span></div>
                <div className="h-1.5 overflow-hidden rounded-full bg-muted"><div className={cn('h-full rounded-full transition-all', scan?.error ? 'bg-red-500' : 'bg-primary')} style={{ width: `${pct}%` }} /></div>
              </div>
            )}
            {msg && (
              <div className={cn('flex items-start gap-1.5 text-[12.5px]', msg.ok ? 'text-emerald-700 dark:text-emerald-400' : 'text-red-600 dark:text-red-400')}>
                {msg.ok ? <CheckCircle2 className="mt-0.5 size-3.5 shrink-0" /> : <XCircle className="mt-0.5 size-3.5 shrink-0" />}<span>{msg.text}</span>
              </div>
            )}
            {msg?.ok && st.is_upload && !running && <Button variant="outline" className="w-full" onClick={() => nav('/')}>Open dashboard <ArrowRight /></Button>}
          </Card>
          <Card className="p-4 text-[12px] text-muted-foreground">
            <div className="mb-1.5 flex items-center gap-1.5 text-[13px] font-semibold text-foreground"><Lock className="size-3.5" /> Stays on this machine</div>
            <ul className="list-disc space-y-1 pl-4">
              <li>Files are saved in LineageLens's data folder (<span className="font-mono">workspace/</span>), not sent anywhere.</li>
              <li>Up to {st.max_upload_mb} MB per upload. Zips may expand to {st.max_unzipped_mb} MB.</li>
              <li>Your data stays in use after a restart until you remove it or load a sample.</li>
            </ul>
          </Card>
        </div>
      </div>
    </div>
  )
}

function Field({ label, hint, children }: { label: string; hint: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-1">
      <span className="text-xs font-medium">{label}</span>
      {children}
      <span className="block text-[11px] text-muted-foreground">{hint}</span>
    </label>
  )
}

function StatusIcon({ s }: { s: UploadResult['status'] }) {
  if (s === 'ok') return <CheckCircle2 className="size-3.5 shrink-0 text-emerald-600 dark:text-emerald-400" />
  if (s === 'warning') return <AlertTriangle className="size-3.5 shrink-0 text-amber-500" />
  return <XCircle className="size-3.5 shrink-0 text-red-600 dark:text-red-400" />
}

function DropZone({ def, staged, errors, progress, disabled, onFiles, onClear }: {
  def: ZoneDef; staged: UploadResult[]; errors: UploadResult[]; progress?: number; disabled: boolean
  onFiles: (items: UploadItem[]) => void; onClear: () => void
}) {
  const fileRef = React.useRef<HTMLInputElement>(null)
  const dirRef = React.useRef<HTMLInputElement>(null)
  const [over, setOver] = React.useState(false)
  const uploading = progress !== undefined
  const rows = [...staged, ...errors]
  React.useEffect(() => { dirRef.current?.setAttribute('webkitdirectory', ''); dirRef.current?.setAttribute('directory', '') }, [])
  const pick = (list: FileList | null) => {
    if (!list || !list.length) return
    onFiles(Array.from(list).map((f) => ({ file: f, path: (f as any).webkitRelativePath || f.name })))
  }
  const needCls = def.need === 'Required for dbt' ? 'border-primary/30 bg-primary/10 text-primary' : 'text-muted-foreground'
  return (
    <Card data-slot={def.slot} className={cn('overflow-hidden transition-colors', over && 'border-primary ring-1 ring-primary/40')}
      onDragOver={(e) => { if (!disabled) { e.preventDefault(); setOver(true) } }} onDragLeave={() => setOver(false)}
      onDrop={async (e) => { e.preventDefault(); setOver(false); if (!disabled) onFiles(await filesFromDrop(e.dataTransfer)) }}>
      <div className="flex flex-wrap items-start gap-3 p-4">
        <div className="flex size-9 shrink-0 items-center justify-center rounded-md border bg-muted/60 text-muted-foreground [&_svg]:size-4">{def.icon}</div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-[13.5px] font-semibold">{def.title}</h3>
            <Badge className={needCls}>{def.need}</Badge>
          </div>
          <p className="mt-0.5 text-[12px] leading-relaxed text-muted-foreground">{def.what}</p>
        </div>
        <div className="flex items-center gap-2">
          {(staged.length > 0 || errors.length > 0) && !uploading && <Button variant="ghost" size="sm" onClick={onClear} disabled={disabled} title="Remove these files"><Trash2 /> Clear</Button>}
          {def.folder && <Button variant="outline" size="sm" disabled={disabled || uploading} onClick={() => dirRef.current?.click()}><FolderUp /> Choose folder</Button>}
          <Button variant="outline" size="sm" disabled={disabled || uploading} onClick={() => fileRef.current?.click()}>
            <Upload /> {def.folder ? 'Choose .zip' : def.multiple ? 'Choose files' : 'Choose file'}
          </Button>
        </div>
        <input ref={fileRef} type="file" hidden accept={def.accept} multiple={def.multiple} data-testid={`file-${def.slot}`}
          onChange={(e) => { pick(e.target.files); e.target.value = '' }} />
        {def.folder && <input ref={dirRef} type="file" hidden multiple data-testid={`dir-${def.slot}`} onChange={(e) => { pick(e.target.files); e.target.value = '' }} />}
      </div>
      {uploading ? (
        <div className="border-t bg-muted/30 px-4 py-3">
          <div className="mb-1 flex justify-between text-[11.5px] text-muted-foreground"><span>{progress! >= 1 ? 'Checking files…' : 'Uploading…'}</span><span className="tabular-nums">{Math.round(progress! * 100)}%</span></div>
          <div className="h-1.5 overflow-hidden rounded-full bg-muted"><div className="h-full rounded-full bg-primary transition-all" style={{ width: `${progress! * 100}%` }} /></div>
        </div>
      ) : rows.length > 0 ? (
        <ul className="divide-y border-t">
          {rows.map((r, i) => (
            <li key={`${r.name}-${i}`} className="flex items-start gap-2.5 px-4 py-2 text-[12px]">
              <span className="mt-0.5"><StatusIcon s={r.status} /></span>
              <span className="min-w-0 flex-1">
                <span className="flex flex-wrap items-baseline gap-x-2">
                  <span className="truncate font-mono text-[11.5px] text-foreground">{r.name}</span>
                  {r.detected && <span className="text-muted-foreground">{r.detected}</span>}
                </span>
                {r.message && <span className={cn('block', r.status === 'error' ? 'text-red-600 dark:text-red-400' : r.status === 'warning' ? 'text-amber-700 dark:text-amber-400' : 'text-muted-foreground')}>{r.message}</span>}
              </span>
              {r.size > 0 && <span className="shrink-0 tabular-nums text-muted-foreground">{fmtSize(r.size)}</span>}
              <Badge className={cn('shrink-0', r.status === 'ok' ? 'border-emerald-500/30 text-emerald-700 dark:text-emerald-400' : r.status === 'warning' ? 'border-amber-500/30 text-amber-700 dark:text-amber-400' : 'border-red-500/30 text-red-600 dark:text-red-400')}>
                {r.status === 'ok' ? 'OK' : r.status === 'warning' ? 'Warning' : 'Error'}
              </Badge>
            </li>
          ))}
        </ul>
      ) : (
        <button type="button" disabled={disabled} onClick={() => (def.folder ? dirRef : fileRef).current?.click()}
          className="flex w-full items-center justify-center gap-2 border-t border-dashed bg-muted/20 px-4 py-3 text-[12px] text-muted-foreground transition-colors hover:bg-muted/50 disabled:opacity-60">
          <Upload className="size-3.5" /> Drop {def.folder ? 'the PBIP folder or a .zip' : def.multiple ? 'files' : 'the file'} here, or click to choose
        </button>
      )}
    </Card>
  )
}

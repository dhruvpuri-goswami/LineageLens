export type Impact = 'breaks' | 'values_may_change'
export type Confidence = 'high' | 'medium' | 'low'
export type ChangeType = 'drop' | 'rename' | 'type' | 'logic'

export interface NodeLite {
  id: string
  type: string
  name: string
  parent: string
  container: string
  display: string
  relation?: string
  visuals?: number
}

export interface ImpactEntry extends NodeLite {
  type_label: string
  impact: Impact
  confidence: Confidence
  depth: number
  via: string | null
  reason: string
  path: string[]
  role?: string
}

export interface VisualHit extends ImpactEntry {
  visual_type: string
  usage: string
  via_display: string
  field_count: number
}

export interface PageHit {
  id: string
  name: string
  ordinal: number
  page_filter: ImpactEntry | null
  visuals: VisualHit[]
  total_visuals: number
}

export interface ReportHit {
  id: string
  name: string
  model: string
  report_filter: ImpactEntry | null
  pages: PageHit[]
  impact: Impact
  confidence: Confidence
  visual_count: number
}

export interface GraphNode {
  id: string
  type: string
  name: string
  parent: string
  container: string
  display: string
  impact: Impact | null
  confidence: Confidence | null
  depth: number
  start: boolean
  lane: number
  lane_key: string
  lane_label: string
  sublevel: number
  group: string
  group_label: string
  group_kind: string
  visual_type?: string
  page_id?: string
  page_name?: string
  page_ordinal?: number
  page_visuals_total?: number
  report_id?: string
  report_name?: string
}
export interface GraphEdge {
  source: string
  target: string
  confidence: Confidence
  impact: Impact
  reason: string
}
export interface SubGraph {
  nodes: GraphNode[]
  edges: GraphEdge[]
  truncated: boolean
  total?: number
  lanes?: { index: number; key: string; label: string }[]
}

export interface ImpactSummary {
  total: number
  breaks: number
  values_may_change: number
  visuals: number
  visuals_breaking: number
  measures: number
  rls_roles: number
  reports: number
  pages: number
  calc_columns: number
  calc_group_items: number
  field_parameters: number
  pbi_columns: number
  warehouse_columns: number
  low_confidence: number
  medium_confidence: number
}

export interface ImpactResult {
  change: ChangeType
  change_label: string
  start: ImpactEntry[]
  summary: ImpactSummary
  reports: ReportHit[]
  groups: Record<string, ImpactEntry[]>
  graph: SubGraph
}

export interface UpstreamResult {
  start: ImpactEntry | null
  groups: Record<string, ImpactEntry[]>
  roots: ImpactEntry[]
  summary: { total: number; source_columns: number; dbt_columns: number; view_columns: number; pbi_columns: number; measures: number }
  graph: SubGraph
}

export interface Warning {
  level: string
  source: string
  message: string
  object?: string
}

export interface Summary {
  counts: Record<string, number>
  edges: number
  confidence: Record<string, number>
  pbi_column_coverage: { total: number; matched: number; unmatched: number; unmatched_list: { id: string; display: string; source_column: string }[] }
  top_columns: { id: string; display: string; type: string; visuals: number; measures: number }[]
  unused_gold_columns: { id: string; display: string }[]
  unused_pbi_objects: { id: string; display: string; type: string }[]
  reports: { id: string; name: string; format: string; model: string; pages: number; visuals: number; model_resolved?: boolean }[]
  models: { id: string; name: string; format: string; tables: number; roles: number }[]
  warnings: Warning[]
  meta: { scanned_at?: number; duration?: number; project_name?: string; config_path?: string; stats?: any; sources?: any }
  project_name: string
  is_upload?: boolean
  is_sample: boolean
  sample_name?: string | null
}

export interface LinkRef {
  id: string
  type: string
  display: string
  confidence: Confidence
  impact: Impact
  reason: string
}

export interface NodeDetail {
  id: string
  type: string
  type_label: string
  name: string
  parent: string
  container: string
  display: string
  file: string
  code: string
  code_lang: string
  description: string
  data: Record<string, any>
  upstream: LinkRef[]
  downstream: LinkRef[]
  children: { id: string; type: string; display: string }[]
  counts: { visuals?: number; measures?: number }
}

export interface CatalogRow {
  id: string
  type: string
  type_label: string
  name: string
  parent: string
  container: string
  display: string
  description: string
  data_type: string
  transform: string
  match_method: string
  unmatched: boolean
  visual_type: string
  downstream_visuals: number
  downstream_measures: number
  upstream: number
  downstream: number
}

export interface ReportTree {
  id: string
  name: string
  format: string
  model: string
  pages: { id: string; name: string; ordinal: number; visuals: { id: string; name: string; visual_type: string; fields: number }[] }[]
}

export interface ScanStatus {
  running: boolean
  pct: number
  step: string
  message: string
  log: { t: number; step: string; pct: number; message: string }[]
  error: string | null
  started: number | null
  finished: number | null
}

export interface ConfigInfo {
  path: string
  is_sample: boolean
  yaml: string
  config: any
  samples_dir: string
  sample_name?: string | null
  samples?: { name: string; description: string; path: string }[]
}

export type UploadSlot = 'manifest' | 'catalog' | 'sql' | 'powerbi' | 'pbix'
export interface UploadResult {
  name: string
  size: number
  status: 'ok' | 'warning' | 'error'
  detected: string
  message: string
  files?: number
  models?: string[]
  reports?: string[]
}
export interface UploadWorkspace {
  project: string
  project_name?: string
  created?: number
  default_database?: string
  default_schema?: string
  path: string
  config_path: string
  active: boolean
  bytes: number
}
export interface UploadState {
  allowed: boolean
  max_upload_mb: number
  max_unzipped_mb: number
  max_zip_files: number
  pbip_extensions: string[]
  staging: Record<UploadSlot, UploadResult[]>
  workspace: UploadWorkspace | null
  is_upload: boolean
}
export interface UploadResponse { slot: UploadSlot; results: UploadResult[]; skipped: number; state: UploadState }
export interface UploadItem { file: File; path: string }

export interface DiffChange {
  id: string
  display: string
  type: string
  change: 'drop' | 'rename' | 'type' | 'logic' | 'add'
  detail: string
  breaking?: boolean
  pbi_objects?: number
  impact?: { summary: ImpactSummary } | null
  old?: string
  new?: string
}
export interface DiffHit extends ImpactEntry {
  cause: string
  cause_change: string
}
export interface DiffResult {
  changes: DiffChange[]
  breaking: boolean
  summary: { changes: number; added: number; visuals: number; visuals_breaking: number; objects: number; objects_breaking: number }
  visuals: DiffHit[]
  objects: DiffHit[]
  markdown: string
  old: string
  new: string
}

async function req<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, { headers: { 'Content-Type': 'application/json' }, ...init })
  if (!r.ok) {
    let msg = `${r.status} ${r.statusText}`
    try {
      const j = await r.json()
      if (j.detail) msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail)
    } catch {
      /* ignore */
    }
    throw new Error(msg)
  }
  return r.json() as Promise<T>
}

/** Upload endpoints need this header (blocks cross-site form posts; see security.py). */
const UPLOAD_HEADERS = { 'X-Requested-With': 'LineageLens' }
const ureq = <T,>(url: string, init: RequestInit = {}) =>
  req<T>(url, { ...init, headers: { 'Content-Type': 'application/json', ...UPLOAD_HEADERS, ...(init.headers || {}) } })

/** Upload files with progress (XHR: fetch has no upload progress). Relative paths are kept for folders. */
export function uploadFiles(slot: UploadSlot, items: UploadItem[], onProgress?: (fraction: number) => void): Promise<UploadResponse> {
  return new Promise((resolve, reject) => {
    const fd = new FormData()
    for (const it of items) {
      fd.append('path', it.path)
      fd.append('file', it.file, it.path)
    }
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `/api/upload/files/${slot}`)
    Object.entries(UPLOAD_HEADERS).forEach(([k, v]) => xhr.setRequestHeader(k, v))
    xhr.upload.onprogress = (e) => { if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total) }
    xhr.onload = () => {
      let body: any = null
      try { body = JSON.parse(xhr.responseText) } catch { /* ignore */ }
      if (xhr.status >= 200 && xhr.status < 300 && body) resolve(body as UploadResponse)
      else reject(new Error(body?.detail ? String(body.detail) : `${xhr.status} ${xhr.statusText || 'Upload failed'}`))
    }
    xhr.onerror = () => reject(new Error('Upload failed: the server could not be reached.'))
    xhr.send(fd)
  })
}

const qs = (ids: string[], extra: Record<string, string> = {}) => {
  const p = new URLSearchParams()
  ids.forEach((i) => p.append('id', i))
  Object.entries(extra).forEach(([k, v]) => p.set(k, v))
  return p.toString()
}

export interface Health { ok: boolean; version: string; nodes: number; links?: { buymeacoffee_url: string; github_repo_url: string } }

export const api = {
  health: () => req<Health>('/api/health'),
  summary: () => req<Summary>('/api/summary'),
  nodes: () => req<{ nodes: NodeLite[]; type_labels: Record<string, string> }>('/api/nodes'),
  node: (id: string) => req<NodeDetail>(`/api/node/${encodeURIComponent(id)}`),
  impact: (ids: string[], change: ChangeType) => req<ImpactResult>(`/api/impact?${qs(ids, { change })}`),
  upstream: (id: string) => req<UpstreamResult>(`/api/upstream?id=${encodeURIComponent(id)}`),
  reports: () => req<ReportTree[]>('/api/reports'),
  catalog: () => req<{ rows: CatalogRow[]; type_labels: Record<string, string> }>('/api/catalog'),
  scan: () => req<{ started: boolean }>('/api/scan', { method: 'POST' }),
  scanStatus: () => req<ScanStatus>('/api/scan/status'),
  config: () => req<ConfigInfo>('/api/config'),
  saveConfig: (path: string, yaml?: string) => req<{ ok: boolean }>('/api/config', { method: 'PUT', body: JSON.stringify({ path, yaml }) }),
  useSample: (name: 'standard' | 'large' = 'standard') => req<{ ok: boolean }>('/api/config/sample', { method: 'POST', body: JSON.stringify({ name }) }),
  diff: (body: { old?: string; new?: string; sample?: boolean }) => req<DiffResult>('/api/diff', { method: 'POST', body: JSON.stringify(body) }),
  uploadState: () => req<UploadState>('/api/upload'),
  clearUpload: (slot: UploadSlot) => ureq<{ ok: boolean; state: UploadState }>(`/api/upload/files/${slot}`, { method: 'DELETE' }),
  scanUpload: (body: { project_name: string; default_database: string; default_schema: string }) =>
    ureq<{ ok: boolean; state: UploadState }>('/api/upload/scan', { method: 'POST', body: JSON.stringify(body) }),
  activateUpload: () => ureq<{ ok: boolean; state: UploadState }>('/api/upload/activate', { method: 'POST' }),
  removeUpload: () => ureq<{ ok: boolean; rescanning: boolean; state: UploadState }>('/api/upload/workspace', { method: 'DELETE' }),
  exportUrl: (ids: string[], change: ChangeType, format: string) => `/api/export?${qs(ids, { change, format })}`,
}

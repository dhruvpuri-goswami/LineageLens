/**
 * LineageLens graph model: turns an impact / upstream sub-graph into a clean, layered swim-lane layout.
 *
 *  - fixed lanes (Sources -> dbt staging -> dbt marts -> Snowflake views -> PBI columns -> measures -> RLS -> reports)
 *  - grouping / collapsing (dbt model, PBI table, measures per table, RLS per model, report > page > visual)
 *  - filters (type / impact / confidence / depth / isolate path) with edge bridging through hidden objects
 *  - merged parallel edges, long edges routed through reserved "dummy" slots (never behind a node),
 *    bundled per source, barycenter ordering and optimal (isotonic) vertical placement.
 *
 * Pure functions only (no React) so it can be unit-tested.
 */
import type { Confidence, GraphEdge, GraphNode, Impact, SubGraph } from './api'

export type Detail = 'reports' | 'pages' | 'visuals'

export interface ViewOptions {
  detail: Detail
  /** key -> collapsed? (overrides the defaults). keys: `group:<g>`, `page:<page id>`, `report:<report id>` */
  overrides: Record<string, boolean>
  hiddenTypes: string[]
  impacts: Impact[] // allowed impacts ([] = all)
  confidences: Confidence[] // allowed ([] = all)
  maxDepth: number // Infinity = all
  isolate: string[] | null // real node ids: keep only their upstream + downstream paths
  overview: boolean // collapse every group (Sankey-like summary)
}

export type ItemKind = 'node' | 'group' | 'page' | 'report' | 'dummy'

export interface Item {
  id: string
  kind: ItemKind
  label: string
  sub: string
  type: string
  members: string[]
  count: number
  impact: Impact | null
  confidence: Confidence | null
  start: boolean
  depth: number
  lane: number
  sublevel: number
  col: number
  container: string | null
  /** key toggled when this aggregate is expanded */
  toggleKey?: string
  x: number
  y: number
  w: number
  h: number
}

export interface Container {
  key: string
  toggleKey: string
  label: string
  sub: string
  kind: string
  col: number
  x: number
  y: number
  w: number
  h: number
  count: number
  type: string
}

export interface VEdge {
  id: string
  source: string
  target: string
  count: number
  impact: Impact
  confidence: Confidence
  reasons: string[]
  points: [number, number][]
}

export interface LaneBand {
  lane: number
  label: string
  x: number
  w: number
  count: number
}

export interface View {
  items: Item[]
  containers: Container[]
  edges: VEdge[]
  lanes: LaneBand[]
  width: number
  height: number
  byId: Map<string, Item>
  /** real node id -> visible item id */
  visibleOf: Map<string, string>
  hiddenCount: number
  totalNodes: number
  maxDepth: number
}

export const NODE_W = 212
export const NODE_H = 46
const ITEM_GAP = 8
const PAD = 8
const HEADER = 30
const BLOCK_GAP = 18
const DUMMY_H = 4
const SUB_GAP = 52
const LANE_GAP = 96

export const LANE_LABELS = [
  'Sources',
  'dbt staging & intermediate',
  'dbt marts (gold)',
  'Snowflake views',
  'Power BI columns',
  'Measures & calc columns',
  'Row-level security',
  'Reports, pages & visuals',
]

const GROUP_NOUN: Record<string, [string, string]> = {
  'source table': ['column', 'columns'],
  table: ['column', 'columns'],
  'dbt model': ['column', 'columns'],
  view: ['column', 'columns'],
  measures: ['measure', 'measures'],
  roles: ['role', 'roles'],
  page: ['visual', 'visuals'],
  report: ['page', 'pages'],
}

export function plural(n: number, [one, many]: [string, string]) {
  return `${n} ${n === 1 ? one : many}`
}

const impactRank = (i: Impact | null | undefined) => (i === 'breaks' ? 2 : i ? 1 : 0)
const confRank = (c: Confidence | null | undefined) => (c === 'high' ? 3 : c === 'medium' ? 2 : c === 'low' ? 1 : 4)
const worstImpact = (a: Impact | null, b: Impact | null): Impact | null => (impactRank(a) >= impactRank(b) ? a : b)
const minConf = (a: Confidence | null, b: Confidence | null): Confidence | null => (confRank(a) <= confRank(b) ? a : b)

export function defaultOptions(sub: SubGraph): ViewOptions {
  const visuals = sub.nodes.filter((n) => n.type === 'visual').length
  const pages = new Set(sub.nodes.filter((n) => n.type === 'visual').map((n) => n.page_id)).size
  const detail: Detail = visuals <= 6 ? 'visuals' : pages <= 14 ? 'pages' : 'reports'
  return { detail, overrides: {}, hiddenTypes: [], impacts: [], confidences: [], maxDepth: Infinity, isolate: null, overview: false }
}

/** Upstream + downstream closure of `ids` over the given edges (inclusive). */
export function pathClosure(ids: string[], edges: { source: string; target: string }[]): Set<string> {
  const out = new Map<string, string[]>()
  const inc = new Map<string, string[]>()
  for (const e of edges) {
    ;(out.get(e.source) ?? out.set(e.source, []).get(e.source)!).push(e.target)
    ;(inc.get(e.target) ?? inc.set(e.target, []).get(e.target)!).push(e.source)
  }
  const keep = new Set(ids)
  for (const adj of [out, inc]) {
    const stack = [...ids]
    const seen = new Set(ids)
    while (stack.length) {
      const cur = stack.pop()!
      for (const nx of adj.get(cur) ?? []) {
        if (!seen.has(nx)) {
          seen.add(nx)
          keep.add(nx)
          stack.push(nx)
        }
      }
    }
  }
  return keep
}

interface Rep {
  id: string
  kind: ItemKind
  container: string | null
  containerToggle?: string
  toggleKey?: string
}

export function isCollapsedKey(key: string, opts: ViewOptions, dflt: boolean) {
  return key in opts.overrides ? opts.overrides[key] : dflt
}

/** All toggle keys present in a sub-graph (for expand / collapse all). */
export function allToggleKeys(sub: SubGraph): string[] {
  const keys = new Set<string>()
  for (const n of sub.nodes) {
    if (n.lane === 7) {
      if (n.report_id) keys.add(`report:${n.report_id}`)
      if (n.page_id) keys.add(`page:${n.page_id}`)
    } else keys.add(`group:${n.group}`)
  }
  return [...keys]
}

export function buildView(sub: SubGraph, opts: ViewOptions): View {
  const all = new Map(sub.nodes.map((n) => [n.id, n]))
  // ---------------------------------------------------------------- isolate + filters
  let pool = sub.nodes
  if (opts.isolate?.length) {
    const keep = pathClosure(opts.isolate.filter((i) => all.has(i)), sub.edges)
    pool = pool.filter((n) => keep.has(n.id))
  }
  const poolSet = new Set(pool.map((n) => n.id))
  const hidden = new Set(opts.hiddenTypes)
  const visible = (n: GraphNode) =>
    n.start ||
    (!hidden.has(n.type) &&
      (!opts.impacts.length || (n.impact && opts.impacts.includes(n.impact))) &&
      (!opts.confidences.length || (n.confidence && opts.confidences.includes(n.confidence))) &&
      n.depth <= opts.maxDepth)
  const shown = pool.filter(visible)
  const shownSet = new Set(shown.map((n) => n.id))
  // bridge edges through hidden (but in-pool) nodes
  const succ = new Map<string, GraphEdge[]>()
  for (const e of sub.edges) {
    if (!poolSet.has(e.source) || !poolSet.has(e.target)) continue
    ;(succ.get(e.source) ?? succ.set(e.source, []).get(e.source)!).push(e)
  }
  const edges: { source: string; target: string; impact: Impact; confidence: Confidence; reason: string }[] = []
  for (const s of shown) {
    const stack: { id: string; impact: Impact; conf: Confidence; reason: string }[] = []
    const seen = new Set<string>([s.id])
    for (const e of succ.get(s.id) ?? []) stack.push({ id: e.target, impact: e.impact, conf: e.confidence, reason: e.reason })
    while (stack.length) {
      const cur = stack.pop()!
      if (seen.has(cur.id)) continue
      seen.add(cur.id)
      if (shownSet.has(cur.id)) {
        edges.push({ source: s.id, target: cur.id, impact: cur.impact, confidence: cur.conf, reason: cur.reason })
        continue
      }
      for (const e of succ.get(cur.id) ?? [])
        stack.push({
          id: e.target,
          impact: cur.impact === 'breaks' && e.impact === 'breaks' ? 'breaks' : 'values_may_change',
          conf: minConf(cur.conf, e.confidence) as Confidence,
          reason: cur.reason,
        })
    }
  }

  // ---------------------------------------------------------------- grouping / collapsing
  const groupSize = new Map<string, number>()
  const startGroups = new Set<string>()
  for (const n of shown) {
    if (n.lane === 7) continue
    groupSize.set(n.group, (groupSize.get(n.group) ?? 0) + 1)
    if (n.start) startGroups.add(n.group)
  }
  const bigGraph = shown.length > 70
  const repOf = (n: GraphNode): Rep => {
    if (n.lane === 7) {
      const rid = n.report_id || `rpt:${n.container}`
      const rKey = `report:${rid}`
      if (n.type === 'report' || isCollapsedKey(rKey, opts, opts.detail === 'reports' || opts.overview)) {
        return { id: `R:${rid}`, kind: 'report', container: null, toggleKey: rKey }
      }
      const pKey = `page:${n.page_id}`
      if (isCollapsedKey(pKey, opts, opts.detail !== 'visuals' || opts.overview)) {
        return { id: `P:${n.page_id}`, kind: 'page', container: `C:${rKey}`, containerToggle: rKey, toggleKey: pKey }
      }
      return { id: n.id, kind: 'node', container: `C:${pKey}`, containerToggle: pKey }
    }
    const size = groupSize.get(n.group) ?? 1
    if (size <= 1) return { id: n.id, kind: 'node', container: null }
    const gKey = `group:${n.group}`
    const dflt = startGroups.has(n.group) ? false : opts.overview || (bigGraph && size > 8)
    if (isCollapsedKey(gKey, opts, dflt)) return { id: `G:${n.group}`, kind: 'group', container: null, toggleKey: gKey }
    return { id: n.id, kind: 'node', container: `C:${gKey}`, containerToggle: gKey }
  }

  const items = new Map<string, Item>()
  const visibleOf = new Map<string, string>()
  const containerMeta = new Map<string, { toggleKey: string; label: string; kind: string; sub: string; type: string; sort: string }>()
  const reportPages = new Map<string, Set<string>>()
  const reportVisuals = new Map<string, number>()
  for (const n of shown) {
    if (n.lane === 7 && n.report_id) {
      if (n.page_id) (reportPages.get(n.report_id) ?? reportPages.set(n.report_id, new Set()).get(n.report_id)!).add(n.page_id)
      if (n.type === 'visual') reportVisuals.set(n.report_id, (reportVisuals.get(n.report_id) ?? 0) + 1)
    }
  }
  for (const n of shown) {
    const r = repOf(n)
    visibleOf.set(n.id, r.id)
    let it = items.get(r.id)
    if (!it) {
      it = {
        id: r.id, kind: r.kind, label: '', sub: '', type: n.type, members: [], count: 0, impact: null, confidence: null,
        start: false, depth: Infinity, lane: n.lane, sublevel: 0, col: 0, container: r.container, toggleKey: r.toggleKey,
        x: 0, y: 0, w: NODE_W, h: NODE_H,
      }
      items.set(r.id, it)
    }
    it.members.push(n.id)
    it.impact = worstImpact(it.impact, n.impact)
    it.confidence = minConf(it.confidence, n.confidence)
    it.start = it.start || n.start
    it.depth = Math.min(it.depth, n.depth)
    if (r.container && r.containerToggle && !containerMeta.has(r.container)) {
      if (n.lane === 7 && r.kind === 'page') {
        containerMeta.set(r.container, { toggleKey: r.containerToggle, label: n.report_name || n.container, kind: 'report', sub: 'Report', type: 'report', sort: `${n.report_name}` })
      } else if (n.lane === 7) {
        containerMeta.set(r.container, {
          toggleKey: r.containerToggle, label: n.page_name || n.parent, kind: 'page', sub: n.report_name || n.container, type: 'page',
          sort: `${n.report_name}|${String(n.page_ordinal ?? 0).padStart(4, '0')}`,
        })
      } else {
        containerMeta.set(r.container, { toggleKey: r.containerToggle, label: n.group_label, kind: n.group_kind, sub: containerSub(n), type: n.type, sort: n.group_label })
      }
    }
  }
  for (const it of items.values()) {
    const first = all.get(it.members[0])!
    it.count = it.members.length
    if (it.kind === 'node') {
      it.label = first.name
      it.sub = leafSub(first, !!it.container)
      it.type = first.type
      it.sublevel = first.sublevel
    } else if (it.kind === 'group') {
      it.label = first.group_label
      const types = countBy(it.members.map((m) => all.get(m)!.type))
      it.type = types[0][0]
      it.sub = `${plural(it.count, GROUP_NOUN[first.group_kind] ?? ['object', 'objects'])} · ${containerSub(first)}`
      it.sublevel = Math.min(...it.members.map((m) => all.get(m)!.sublevel))
    } else if (it.kind === 'page') {
      const vis = it.members.filter((m) => all.get(m)!.type === 'visual').length
      it.label = first.page_name || first.parent
      it.type = 'page'
      it.sub = vis ? `${plural(vis, ['visual', 'visuals'])} affected` : 'Page filter'
      if (first.page_visuals_total && vis) it.sub += ` of ${first.page_visuals_total}`
      it.count = vis || 1
    } else if (it.kind === 'report') {
      const rid = first.report_id || ''
      const pages = reportPages.get(rid)?.size ?? 0
      const vis = reportVisuals.get(rid) ?? 0
      it.label = first.report_name || first.container
      it.type = 'report'
      it.sub = vis ? `${plural(pages, ['page', 'pages'])} · ${plural(vis, ['visual', 'visuals'])}` : 'Report filter'
      it.count = vis || 1
    }
  }

  // ---------------------------------------------------------------- visible edges (merged)
  const vedges = new Map<string, VEdge>()
  for (const e of edges) {
    const s = visibleOf.get(e.source)!
    const t = visibleOf.get(e.target)!
    if (!s || !t || s === t) continue
    const key = `${s}→${t}`
    const cur = vedges.get(key)
    if (cur) {
      cur.count++
      cur.impact = worstImpact(cur.impact, e.impact) as Impact
      cur.confidence = minConf(cur.confidence, e.confidence) as Confidence
      if (cur.reasons.length < 4 && e.reason && !cur.reasons.includes(e.reason)) cur.reasons.push(e.reason)
    } else vedges.set(key, { id: key, source: s, target: t, count: 1, impact: e.impact, confidence: e.confidence, reasons: e.reason ? [e.reason] : [], points: [] })
  }

  // ---------------------------------------------------------------- sub-levels on the visible graph
  const itemList = [...items.values()]
  recomputeSublevels(itemList, [...vedges.values()], items)

  // columns
  const colKeys = [...new Set(itemList.map((i) => i.lane * 100 + i.sublevel))].sort((a, b) => a - b)
  const colIndex = new Map(colKeys.map((k, i) => [k, i]))
  for (const it of itemList) it.col = colIndex.get(it.lane * 100 + it.sublevel)!
  const colX: number[] = []
  let x = PAD + 20
  colKeys.forEach((k, i) => {
    if (i > 0) x += NODE_W + (Math.floor(k / 100) !== Math.floor(colKeys[i - 1] / 100) ? LANE_GAP : SUB_GAP)
    colX.push(x)
  })
  for (const it of itemList) it.x = colX[it.col]

  // a container segment with a single member in a column adds noise: render that member as a plain node
  const segCount = new Map<string, number>()
  for (const it of itemList) if (it.container) segCount.set(`${it.container}@${it.col}`, (segCount.get(`${it.container}@${it.col}`) ?? 0) + 1)
  for (const it of itemList) {
    if (it.container && segCount.get(`${it.container}@${it.col}`) === 1 && it.kind === 'node') {
      const n = all.get(it.members[0])!
      it.container = null
      it.sub = leafSub(n, false)
    } else if (it.container && segCount.get(`${it.container}@${it.col}`) === 1 && it.kind === 'page') {
      const n = all.get(it.members[0])!
      it.container = null
      it.sub = `${n.report_name} · ${it.sub}`
    }
  }

  // dummy nodes for long edges (bundled per source and column)
  const dummies = new Map<string, Item>()
  const chain = new Map<string, string[]>() // edge id -> ordered item ids incl. endpoints
  for (const e of vedges.values()) {
    const s = items.get(e.source)!
    const t = items.get(e.target)!
    const ids = [s.id]
    if (t.col > s.col + 1) {
      for (let c = s.col + 1; c < t.col; c++) {
        const did = `D:${s.id}:${c}`
        if (!dummies.has(did)) {
          dummies.set(did, {
            id: did, kind: 'dummy', label: '', sub: '', type: 'dummy', members: [], count: 0, impact: null, confidence: null, start: false,
            depth: 0, lane: -1, sublevel: 0, col: c, container: null, x: colX[c], y: 0, w: NODE_W, h: DUMMY_H,
          })
        }
        ids.push(did)
      }
    }
    ids.push(t.id)
    chain.set(e.id, ids)
  }
  const nodesAll = new Map<string, Item>([...items, ...dummies])
  // adjacency between neighbouring columns (deduplicated)
  const left = new Map<string, Set<string>>()
  const right = new Map<string, Set<string>>()
  for (const ids of chain.values()) {
    for (let i = 0; i + 1 < ids.length; i++) {
      const a = nodesAll.get(ids[i])!
      const b = nodesAll.get(ids[i + 1])!
      if (b.col <= a.col) continue // same-column / backward edges do not drive ordering
      ;(right.get(a.id) ?? right.set(a.id, new Set()).get(a.id)!).add(b.id)
      ;(left.get(b.id) ?? left.set(b.id, new Set()).get(b.id)!).add(a.id)
    }
  }

  // ---------------------------------------------------------------- blocks per column + ordering
  interface Block { key: string; items: Item[]; isDummy: boolean; container: string | null; sort: string; y: number; h: number }
  const columns: Block[][] = colKeys.map(() => [])
  const blockOf = new Map<string, Block>()
  for (const it of nodesAll.values()) {
    const ck = it.container ? `${it.container}@${it.col}` : `I:${it.id}`
    let b = blockOf.get(ck)
    if (!b) {
      const sort = it.container ? containerMeta.get(it.container)?.sort ?? '' : it.kind === 'dummy' ? '' : it.label
      b = { key: ck, items: [], isDummy: it.kind === 'dummy', container: it.container, sort, y: 0, h: 0 }
      blockOf.set(ck, b)
      columns[it.col].push(b)
    }
    b.items.push(it)
    blockOf.set(it.id, b)
  }
  for (const col of columns) {
    col.sort((a, b) => a.sort.localeCompare(b.sort))
    for (const b of col) b.items.sort((p, q) => (q.start ? 1 : 0) - (p.start ? 1 : 0) || p.label.localeCompare(q.label))
  }
  const order = new Map<string, number>()
  const renumber = () => {
    for (const col of columns) {
      let i = 0
      for (const b of col) for (const it of b.items) order.set(it.id, i++)
    }
  }
  renumber()
  const bary = (it: Item, adj: Map<string, Set<string>>) => {
    const ns = adj.get(it.id)
    if (!ns || !ns.size) return null
    let s = 0
    for (const n of ns) s += order.get(n)!
    return s / ns.size
  }
  for (let iter = 0; iter < 8; iter++) {
    const down = iter % 2 === 0
    const seq = down ? columns.map((_, i) => i) : columns.map((_, i) => columns.length - 1 - i)
    for (const ci of seq) {
      const adj = down ? left : right
      const col = columns[ci]
      for (const b of col) {
        const vals = b.items.map((it) => [it, bary(it, adj) ?? bary(it, down ? right : left)] as const)
        const keyed = vals.map(([it, v], idx) => ({ it, v: v ?? order.get(it.id)! + idx * 1e-3 }))
        keyed.sort((p, q) => p.v - q.v)
        b.items = keyed.map((k) => k.it)
      }
      const bv = col.map((b, idx) => {
        const vs = b.items.map((it) => bary(it, adj) ?? bary(it, down ? right : left)).filter((v): v is number => v !== null)
        return { b, v: vs.length ? vs.reduce((a, c) => a + c, 0) / vs.length : idx }
      })
      // keep start node blocks on top-ish by stable sort
      bv.sort((p, q) => p.v - q.v)
      columns[ci] = bv.map((x2) => x2.b)
      renumber()
    }
  }

  // ---------------------------------------------------------------- vertical placement
  for (const col of columns) {
    for (const b of col) {
      if (b.isDummy) {
        b.h = DUMMY_H
        b.items[0].y = 0
        continue
      }
      const top = b.container ? HEADER + PAD : 0
      b.items.forEach((it, i) => (it.y = top + i * (NODE_H + ITEM_GAP)))
      b.h = top + b.items.length * NODE_H + (b.items.length - 1) * ITEM_GAP + (b.container ? PAD : 0)
    }
    let y = 0
    for (const b of col) {
      b.y = y
      y += b.h + BLOCK_GAP
    }
  }
  const center = (it: Item) => blockOf.get(it.id)!.y + it.y + it.h / 2
  const gapBetween = (a: Block, b: Block) => (a.isDummy || b.isDummy ? (a.isDummy && b.isDummy ? 6 : 10) : BLOCK_GAP)
  for (let iter = 0; iter < 10; iter++) {
    const down = iter % 2 === 0
    const seq = down ? columns.map((_, i) => i) : columns.map((_, i) => columns.length - 1 - i)
    for (const ci of seq) {
      const col = columns[ci]
      if (!col.length) continue
      const desired: number[] = []
      const weights: number[] = []
      for (const b of col) {
        let s = 0
        let w = 0
        for (const it of b.items) {
          for (const adj of [left, right]) {
            for (const n of adj.get(it.id) ?? []) {
              s += center(nodesAll.get(n)!) - (it.y + it.h / 2)
              w++
            }
          }
        }
        desired.push(w ? s / w : b.y)
        weights.push(w ? w : 0.05)
      }
      // isotonic regression (pool adjacent violators) => minimal movement without overlaps, order preserved
      const offs: number[] = []
      let acc = 0
      col.forEach((b, i) => {
        offs.push(acc)
        acc += b.h + (i + 1 < col.length ? gapBetween(b, col[i + 1]) : 0)
      })
      const z = pav(desired.map((d, i) => d - offs[i]), weights)
      col.forEach((b, i) => (b.y = z[i] + offs[i]))
    }
  }
  // normalise
  let minY = Infinity
  let maxY = -Infinity
  for (const col of columns) for (const b of col) {
    minY = Math.min(minY, b.y)
    maxY = Math.max(maxY, b.y + b.h)
  }
  const TOP = 56
  const shift = TOP - (isFinite(minY) ? minY : 0)
  for (const col of columns) for (const b of col) {
    b.y += shift
    for (const it of b.items) it.y = b.y + it.y
  }

  // containers
  const containers: Container[] = []
  for (const col of columns) {
    for (const b of col) {
      if (!b.container) continue
      const m = containerMeta.get(b.container)!
      containers.push({
        key: `${b.container}@${b.items[0].col}`, toggleKey: m.toggleKey, label: m.label, sub: m.sub, kind: m.kind, col: b.items[0].col,
        x: colX[b.items[0].col] - PAD, y: b.y, w: NODE_W + 2 * PAD, h: b.h, count: b.items.length, type: m.type,
      })
    }
  }

  // edge routes
  for (const e of vedges.values()) {
    const ids = chain.get(e.id)!
    const pts: [number, number][] = []
    const s = nodesAll.get(ids[0])!
    const t = nodesAll.get(ids[ids.length - 1])!
    if (t.col <= s.col) {
      // same column (rare: cycles) or reports lane: leave right, come back on the right side
      pts.push([s.x + s.w, s.y + s.h / 2], [t.x + t.w, t.y + t.h / 2])
    } else {
      pts.push([s.x + s.w, s.y + s.h / 2])
      for (const d of ids.slice(1, -1)) {
        const it = nodesAll.get(d)!
        pts.push([it.x - PAD, it.y + it.h / 2], [it.x + it.w + PAD, it.y + it.h / 2])
      }
      pts.push([t.x, t.y + t.h / 2])
    }
    e.points = pts
  }

  // lanes
  const lanes: LaneBand[] = []
  colKeys.forEach((k, i) => {
    const lane = Math.floor(k / 100)
    const last = lanes[lanes.length - 1]
    if (last && last.lane === lane) last.w = colX[i] + NODE_W + PAD + 24 - last.x
    else lanes.push({ lane, label: LANE_LABELS[lane] ?? '', x: colX[i] - PAD - 24, w: NODE_W + 2 * PAD + 48, count: 0 })
  })
  for (const it of items.values()) {
    const l = lanes.find((b) => b.lane === it.lane)
    if (l) l.count += it.members.length
  }
  const width = (colX.length ? colX[colX.length - 1] + NODE_W : NODE_W) + PAD + 44
  const height = (isFinite(maxY) ? maxY + shift : 200) + 40
  return {
    items: [...items.values()], containers, edges: [...vedges.values()], lanes, width, height,
    byId: items, visibleOf, hiddenCount: sub.nodes.length - shown.length, totalNodes: sub.nodes.length,
    maxDepth: Math.max(0, ...sub.nodes.map((n) => n.depth)),
  }
}

function recomputeSublevels(list: Item[], edges: VEdge[], items: Map<string, Item>) {
  const succ = new Map<string, string[]>()
  const indeg = new Map<string, number>()
  for (const it of list) if (it.lane !== 7) it.sublevel = 0
  for (const e of edges) {
    const s = items.get(e.source)!
    const t = items.get(e.target)!
    if (s.lane !== t.lane || s.lane === 7) continue
    ;(succ.get(s.id) ?? succ.set(s.id, []).get(s.id)!).push(t.id)
    indeg.set(t.id, (indeg.get(t.id) ?? 0) + 1)
  }
  const q = list.filter((i) => !indeg.get(i.id)).map((i) => i.id)
  while (q.length) {
    const cur = q.pop()!
    const c = items.get(cur)!
    for (const nx of succ.get(cur) ?? []) {
      const n = items.get(nx)!
      n.sublevel = Math.max(n.sublevel, c.sublevel + 1)
      indeg.set(nx, indeg.get(nx)! - 1)
      if (!indeg.get(nx)) q.push(nx)
    }
  }
  for (const it of list) {
    if (it.lane === 7) it.sublevel = 0
    it.sublevel = Math.min(it.sublevel, 5)
  }
}

/** Weighted isotonic regression (non-decreasing) via pool-adjacent-violators. */
export function pav(y: number[], w: number[]): number[] {
  const vals: number[] = []
  const wts: number[] = []
  const cnt: number[] = []
  for (let i = 0; i < y.length; i++) {
    vals.push(y[i])
    wts.push(w[i])
    cnt.push(1)
    while (vals.length > 1 && vals[vals.length - 2] > vals[vals.length - 1]) {
      const v2 = vals.pop()!
      const w2 = wts.pop()!
      const c2 = cnt.pop()!
      const v1 = vals.pop()!
      const w1 = wts.pop()!
      const c1 = cnt.pop()!
      const ww = w1 + w2
      vals.push((v1 * w1 + v2 * w2) / ww)
      wts.push(ww)
      cnt.push(c1 + c2)
    }
  }
  const out: number[] = []
  vals.forEach((v, i) => {
    for (let k = 0; k < cnt[i]; k++) out.push(v)
  })
  return out
}

function countBy(xs: string[]): [string, number][] {
  const m = new Map<string, number>()
  for (const x of xs) m.set(x, (m.get(x) ?? 0) + 1)
  return [...m.entries()].sort((a, b) => b[1] - a[1])
}

function containerSub(n: GraphNode): string {
  switch (n.group_kind) {
    case 'dbt model': return n.lane === 1 ? 'dbt staging / intermediate' : 'dbt model'
    case 'source table': return 'Source table'
    case 'view': return 'Snowflake view'
    case 'table': return n.type === 'snowflake_table_column' ? 'Snowflake table' : `Table · ${n.container}`
    case 'measures': return `Measures · ${n.container}`
    case 'roles': return 'RLS roles'
    default: return n.group_kind
  }
}

const VT: Record<string, string> = {
  card: 'Card', kpi: 'KPI', lineChart: 'Line chart', clusteredColumnChart: 'Column chart', clusteredBarChart: 'Bar chart',
  tableEx: 'Table', pivotTable: 'Matrix', donutChart: 'Donut', slicer: 'Slicer', waterfallChart: 'Waterfall',
  multiRowCard: 'Multi-row card', scatterChart: 'Scatter', areaChart: 'Area chart', map: 'Map', gauge: 'Gauge',
}
export const visualTypeLabel = (t?: string) => (t ? VT[t] ?? t.replace(/([a-z])([A-Z])/g, '$1 $2') : 'Visual')

function leafSub(n: GraphNode, inContainer: boolean): string {
  if (n.type === 'visual') return inContainer ? visualTypeLabel(n.visual_type) : `${visualTypeLabel(n.visual_type)} · ${n.page_name}`
  if (n.type === 'page') return `Page filter · ${n.report_name ?? n.container}`
  if (n.type === 'report') return 'Report filter'
  if (n.type === 'rls_role') return `RLS · ${n.container}`
  if (inContainer) return n.type === 'measure' ? 'Measure' : n.type === 'calc_column' ? 'Calculated column' : n.group_kind === 'dbt model' ? 'dbt column' : 'Column'
  return n.parent ? `${n.parent}${n.container && n.lane >= 4 ? ' · ' + n.container : ''}` : n.container
}

/** Upstream/downstream path of a visible item inside the view (for focus highlighting). */
export function focusSet(view: View, id: string): { nodes: Set<string>; edges: Set<string> } {
  // edges on a directed path through `id`: both ends in ancestors(id)∪{id} or both in descendants(id)∪{id}
  const anc = directed(view.edges, id, 'up')
  const desc = directed(view.edges, id, 'down')
  const edges = new Set<string>()
  for (const e of view.edges) {
    if ((anc.has(e.source) && anc.has(e.target)) || (desc.has(e.source) && desc.has(e.target))) edges.add(e.id)
  }
  return { nodes: new Set([...anc, ...desc]), edges }
}

function directed(edges: VEdge[], id: string, dir: 'up' | 'down'): Set<string> {
  const adj = new Map<string, string[]>()
  for (const e of edges) {
    const [a, b] = dir === 'down' ? [e.source, e.target] : [e.target, e.source]
    ;(adj.get(a) ?? adj.set(a, []).get(a)!).push(b)
  }
  const seen = new Set([id])
  const st = [id]
  while (st.length) {
    const c = st.pop()!
    for (const n of adj.get(c) ?? []) if (!seen.has(n)) {
      seen.add(n)
      st.push(n)
    }
  }
  return seen
}

/** Smooth path through routed points: straight inside reserved column slots, cubic curves across gutters. */
export function edgePath(points: [number, number][]): string {
  if (points.length < 2) return ''
  const [x0, y0] = points[0]
  let d = `M${x0.toFixed(1)},${y0.toFixed(1)}`
  for (let i = 1; i < points.length; i++) {
    const [px, py] = points[i - 1]
    const [x, y] = points[i]
    if (points.length === 2 && x <= px) {
      // backward / same-column edge: loop out to the right
      const bulge = 60
      d += ` C${(px + bulge).toFixed(1)},${py.toFixed(1)} ${(x + bulge).toFixed(1)},${y.toFixed(1)} ${x.toFixed(1)},${y.toFixed(1)}`
    } else if (i % 2 === 0 && points.length > 2 && i < points.length - 1 && Math.abs(y - py) < 0.5) {
      d += ` L${x.toFixed(1)},${y.toFixed(1)}`
    } else {
      const dx = Math.max(24, (x - px) * 0.5)
      d += ` C${(px + dx).toFixed(1)},${py.toFixed(1)} ${(x - dx).toFixed(1)},${y.toFixed(1)} ${x.toFixed(1)},${y.toFixed(1)}`
    }
  }
  return d
}

export function searchItems(view: View, q: string, nodes: Map<string, GraphNode>): string[] {
  const s = q.trim().toLowerCase()
  if (!s) return []
  const out: string[] = []
  for (const it of view.items) {
    if (it.label.toLowerCase().includes(s) || it.members.some((m) => {
      const n = nodes.get(m)
      return n && (n.display.toLowerCase().includes(s) || n.name.toLowerCase().includes(s))
    })) out.push(it.id)
  }
  return out
}

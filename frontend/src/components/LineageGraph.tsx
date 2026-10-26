import * as React from 'react'
import {
  ChevronDown, ChevronRight, Crosshair, Download, Expand, FileBarChart2, Filter, Focus, Keyboard, LayoutPanelTop, Maximize2,
  Minimize2, Minus, Network, Plus, Rows3, ScanSearch, Search, Shrink, Table2, Workflow, X, BarChart3,
} from 'lucide-react'
import type { Confidence, GraphNode, Impact, SubGraph } from '@/lib/api'
import { meta } from '@/lib/types'
import { cn } from '@/lib/utils'
import { useApp } from '@/lib/store'
import {
  allToggleKeys, buildView, defaultOptions, edgePath, focusSet, LANE_LABELS, NODE_H, NODE_W, searchItems, visualTypeLabel,
  type Container, type Detail, type Item, type View, type ViewOptions,
} from '@/lib/graphModel'
import { Badge, ConfidenceBadge, ImpactBadge, Kbd, TypeBadge } from './ui'

type Mode = 'impact' | 'upstream'
type ViewMode = 'graph' | 'overview' | 'table'

// ------------------------------------------------------------------ palette (literal colours so exports look identical)
function palette(dark: boolean) {
  return dark
    ? {
        bg: '#0d0d0f', laneA: 'rgba(161,161,170,0.035)', laneB: 'rgba(161,161,170,0.0)', laneLine: 'rgba(161,161,170,0.10)',
        card: '#151517', cardHover: '#1b1b1e', border: '#2a2a2e', text: '#ededed', muted: '#a1a1aa', container: 'rgba(161,161,170,0.05)',
        containerBorder: '#2a2a2e', primary: '#5c8df6', breaks: '#f87171', may: '#fbbf24', neutral: '#52525b', stack: '#1b1b1e', header: '#a1a1aa',
      }
    : {
        bg: '#fafafa', laneA: 'rgba(24,24,27,0.022)', laneB: 'rgba(24,24,27,0.0)', laneLine: 'rgba(24,24,27,0.07)',
        card: '#ffffff', cardHover: '#f7f7f8', border: '#e4e4e7', text: '#18181b', muted: '#6b6b74', container: 'rgba(244,244,245,0.8)',
        containerBorder: '#e4e4e7', primary: '#1e66f5', breaks: '#dc2626', may: '#d97706', neutral: '#a1a1aa', stack: '#f4f4f5', header: '#52525b',
      }
}
type Pal = ReturnType<typeof palette>

// ------------------------------------------------------------------ text measuring / truncation
let _ctx: CanvasRenderingContext2D | null = null
function fit(text: string, px: number, size: number, weight = 400): string {
  if (!_ctx) _ctx = document.createElement('canvas').getContext('2d')
  if (!_ctx) return text
  _ctx.font = `${weight} ${size}px "Inter Variable", Inter, "Segoe UI", system-ui, sans-serif`
  if (_ctx.measureText(text).width <= px) return text
  let lo = 0
  let hi = text.length
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1
    if (_ctx.measureText(text.slice(0, mid) + '…').width <= px) lo = mid
    else hi = mid - 1
  }
  return text.slice(0, lo) + '…'
}

const edgeColor = (p: Pal, mode: Mode, impact: Impact) => (mode === 'upstream' ? p.primary : impact === 'breaks' ? p.breaks : p.may)

// ------------------------------------------------------------------ SVG pieces
function NodeBox({ it, p, state, onClick, onDouble, onEnter, onLeave, onToggle }: {
  it: Item; p: Pal; state: { dim: boolean; match: boolean; selected: boolean; hot: boolean }
  onClick: (e: React.MouseEvent) => void; onDouble: () => void; onEnter: () => void; onLeave: () => void; onToggle?: () => void
}) {
  const m = meta(it.type)
  const Icon = it.kind === 'report' ? FileBarChart2 : it.kind === 'page' ? LayoutPanelTop : m.icon
  const agg = it.kind !== 'node'
  const hex = it.kind === 'report' ? meta('report').hex : it.kind === 'page' ? meta('page').hex : m.hex
  const ring = state.selected ? p.primary : state.match ? p.may : it.start ? p.primary : null
  const textW = NODE_W - 50 - (agg ? 44 : 18)
  return (
    <g
      transform={`translate(${it.x},${it.y})`}
      opacity={state.dim ? 0.16 : 1}
      style={{ cursor: 'pointer', transition: 'opacity .15s' }}
      onClick={onClick}
      onDoubleClick={(e) => { e.stopPropagation(); onDouble() }}
      onMouseEnter={onEnter}
      onMouseLeave={onLeave}
      data-id={it.id}
    >
      <title>{`${it.label}\n${it.sub}${agg ? '\nDouble-click to expand' : '\nDouble-click for details'}`}</title>
      {agg && (
        <>
          <rect x={6} y={-6} width={NODE_W - 12} height={NODE_H} rx={6} fill={p.stack} stroke={p.border} />
          <rect x={3} y={-3} width={NODE_W - 6} height={NODE_H} rx={6} fill={p.stack} stroke={p.border} />
        </>
      )}
      {ring && <rect x={-3} y={-3} width={NODE_W + 6} height={NODE_H + 6} rx={8} fill="none" stroke={ring} strokeOpacity={state.selected || state.match ? 0.9 : 0.55} strokeWidth={state.selected || state.match ? 2 : 1.5} />}
      <rect width={NODE_W} height={NODE_H} rx={6} fill={state.hot ? p.cardHover : p.card} stroke={p.border} />
      <rect x={0.5} y={9} width={3} height={NODE_H - 18} rx={1.5} fill={hex} />
      <rect x={11} y={11} width={24} height={24} rx={4} fill={hex} fillOpacity={0.12} />
      <Icon x={16} y={16} width={14} height={14} color={hex} strokeWidth={2.1} />
      <text x={44} y={19.5} fontSize={12.5} fontWeight={600} fill={p.text}>{fit(it.label, textW, 12.5, 600)}</text>
      <text x={44} y={35} fontSize={11} fill={p.muted}>{fit(it.sub, textW + (agg ? 0 : 6), 11)}</text>
      {it.impact && !agg && <circle cx={NODE_W - 13} cy={14} r={3.5} fill={it.impact === 'breaks' ? p.breaks : p.may} />}
      {agg && (
        <g
          onClick={(e) => { e.stopPropagation(); onToggle?.() }}
          style={{ cursor: 'pointer' }}
        >
          <rect x={NODE_W - 42} y={12} width={32} height={22} rx={4} fill={hex} fillOpacity={0.12} />
          <text x={NODE_W - 31} y={27} fontSize={11} fontWeight={700} fill={hex} textAnchor="middle">{it.count > 99 ? '99+' : it.count}</text>
          <ChevronRight x={NODE_W - 23} y={16} width={12} height={14} color={hex} strokeWidth={2.4} />
        </g>
      )}
    </g>
  )
}

function ContainerBox({ c, p, dim, onToggle }: { c: Container; p: Pal; dim: boolean; onToggle: () => void }) {
  const hex = meta(c.type).hex
  return (
    <g transform={`translate(${c.x},${c.y})`} opacity={dim ? 0.35 : 1} style={{ transition: 'opacity .15s' }}>
      <rect width={c.w} height={c.h} rx={8} fill={p.container} stroke={p.containerBorder} />
      <g style={{ cursor: 'pointer' }} onClick={(e) => { e.stopPropagation(); onToggle() }}>
        <title>{`${c.label}\n${c.sub}\nClick to collapse`}</title>
        <rect width={c.w} height={28} rx={8} fill="transparent" />
        <ChevronDown x={9} y={8} width={13} height={13} color={p.muted} strokeWidth={2.2} />
        <circle cx={28} cy={14.5} r={3} fill={hex} />
        <text x={36} y={18.5} fontSize={11.5} fontWeight={600} fill={p.header}>{fit(c.label, c.w - 92, 11.5, 600)}</text>
        <text x={c.w - 10} y={18.5} fontSize={10.5} fontWeight={600} fill={p.muted} textAnchor="end">{c.count}</text>
      </g>
    </g>
  )
}

// ------------------------------------------------------------------ pan / zoom
interface T { x: number; y: number; k: number }
function useSize(ref: React.RefObject<HTMLElement>) {
  const [s, set] = React.useState({ w: 800, h: 500 })
  React.useLayoutEffect(() => {
    if (!ref.current) return
    const ro = new ResizeObserver(([e]) => set({ w: e.contentRect.width, h: e.contentRect.height }))
    ro.observe(ref.current)
    return () => ro.disconnect()
  }, [ref])
  return s
}
const initT = (v: { width: number; height: number }, s: { w: number; h: number }, alignRight = false): T => {
  const k = Math.max(0.58, Math.min(1, (s.w - 40) / v.width, (s.h - 30) / v.height))
  return {
    k,
    x: v.width * k < s.w ? (s.w - v.width * k) / 2 : alignRight ? s.w - v.width * k - 8 : 8,
    y: v.height * k < s.h ? Math.max(4, (s.h - v.height * k) / 2 - 4) : 0,
  }
}
const fitT = (v: { width: number; height: number }, s: { w: number; h: number }): T => {
  const k = Math.max(0.18, Math.min(1.05, (s.w - 40) / v.width, (s.h - 30) / v.height))
  return { k, x: (s.w - v.width * k) / 2, y: Math.max(4, (s.h - v.height * k) / 2 - 4) }
}

// ------------------------------------------------------------------ export
function downloadBlob(blob: Blob, name: string) {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = name
  a.click()
  setTimeout(() => URL.revokeObjectURL(a.href), 2000)
}
function svgString(svg: SVGSVGElement, view: View, bg: string) {
  const clone = svg.cloneNode(true) as SVGSVGElement
  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
  clone.setAttribute('width', String(Math.ceil(view.width)))
  clone.setAttribute('height', String(Math.ceil(view.height)))
  clone.setAttribute('viewBox', `0 0 ${Math.ceil(view.width)} ${Math.ceil(view.height)}`)
  clone.removeAttribute('class')
  clone.removeAttribute('style')
  const root = clone.querySelector('[data-root]')
  root?.removeAttribute('transform')
  root?.removeAttribute('style')
  clone.querySelectorAll('[data-export-only]').forEach((n) => n.removeAttribute('display'))
  const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect')
  rect.setAttribute('width', '100%')
  rect.setAttribute('height', '100%')
  rect.setAttribute('fill', bg)
  clone.insertBefore(rect, clone.firstChild)
  return new XMLSerializer().serializeToString(clone)
}
async function exportPng(svg: SVGSVGElement, view: View, bg: string, name: string) {
  const s = svgString(svg, view, bg)
  const img = new Image()
  const url = URL.createObjectURL(new Blob([s], { type: 'image/svg+xml;charset=utf-8' }))
  await new Promise<void>((res, rej) => { img.onload = () => res(); img.onerror = rej; img.src = url })
  const scale = Math.min(2, 16000 / Math.max(view.width, view.height))
  const c = document.createElement('canvas')
  c.width = Math.ceil(view.width * scale)
  c.height = Math.ceil(view.height * scale)
  const ctx = c.getContext('2d')!
  ctx.scale(scale, scale)
  ctx.drawImage(img, 0, 0)
  URL.revokeObjectURL(url)
  c.toBlob((b) => b && downloadBlob(b, name))
}

// ------------------------------------------------------------------ small UI bits
function TB({ active, title, onClick, children, className }: { active?: boolean; title: string; onClick: () => void; children: React.ReactNode; className?: string }) {
  return (
    <button
      title={title}
      onClick={onClick}
      className={cn(
        'inline-flex h-8 items-center gap-1.5 rounded-md px-2.5 text-xs font-medium transition-colors [&_svg]:size-3.5',
        active ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:bg-muted hover:text-foreground',
        className,
      )}
    >
      {children}
    </button>
  )
}
function Seg<T extends string>({ value, onChange, options }: { value: T; onChange: (v: T) => void; options: { value: T; label: React.ReactNode; title?: string }[] }) {
  return (
    <div className="inline-flex rounded-lg border bg-muted/60 p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          title={o.title}
          onClick={() => onChange(o.value)}
          className={cn(
            'inline-flex h-7 items-center gap-1.5 rounded-md px-2.5 text-xs font-medium transition-all [&_svg]:size-3.5',
            value === o.value ? 'bg-card text-foreground shadow-soft' : 'text-muted-foreground hover:text-foreground',
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}
function Chip({ on, onClick, children, color }: { on: boolean; onClick: () => void; children: React.ReactNode; color?: string }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'inline-flex h-7 items-center gap-1.5 rounded-md border px-2 text-[11.5px] font-medium transition-colors',
        on ? 'bg-card text-foreground' : 'border-dashed text-muted-foreground/70 line-through decoration-muted-foreground/40 hover:text-foreground',
      )}
    >
      {color && <span className="size-2 rounded-full" style={{ background: color }} />}
      {children}
    </button>
  )
}

// ------------------------------------------------------------------ main component
export function LineageGraph({ graph, mode, height = 600 }: { graph: SubGraph; mode: Mode; height?: number; focusId?: string | null }) {
  const { theme, openNode } = useApp()
  const p = palette(theme === 'dark')
  const [opts, setOpts] = React.useState<ViewOptions>(() => defaultOptions(graph))
  const [viewMode, setViewMode] = React.useState<ViewMode>('graph')
  const [selected, setSelected] = React.useState<string | null>(null)
  const [hover, setHover] = React.useState<string | null>(null)
  const [query, setQuery] = React.useState('')
  const [matchIdx, setMatchIdx] = React.useState(0)
  const [showFilters, setShowFilters] = React.useState(false)
  const [full, setFull] = React.useState(false)
  const [showKeys, setShowKeys] = React.useState(false)
  const [t, setT] = React.useState<T>({ x: 0, y: 0, k: 1 })
  const [animate, setAnimate] = React.useState(false)
  const wrap = React.useRef<HTMLDivElement>(null)
  const svgRef = React.useRef<SVGSVGElement>(null)
  const searchRef = React.useRef<HTMLInputElement>(null)
  const size = useSize(wrap)
  const nodeMap = React.useMemo(() => new Map(graph.nodes.map((n) => [n.id, n])), [graph])

  React.useEffect(() => {
    setOpts(defaultOptions(graph))
    setSelected(null)
    setQuery('')
    setViewMode('graph')
  }, [graph])

  const effOpts = React.useMemo(() => ({ ...opts, overview: viewMode === 'overview' }), [opts, viewMode])
  const view = React.useMemo(() => buildView(graph, effOpts), [graph, effOpts])

  // fit when the layout changes
  const fitNow = React.useCallback((anim = true) => {
    setAnimate(anim)
    setT(fitT(view, size))
    if (anim) setTimeout(() => setAnimate(false), 320)
  }, [view, size])
  React.useEffect(() => { setT(initT(view, size, mode === 'upstream')) }, [view, size.w, size.h]) // eslint-disable-line react-hooks/exhaustive-deps

  // selection maintenance
  React.useEffect(() => { if (selected && !view.byId.has(selected)) setSelected(null) }, [view, selected])

  const active = hover ?? selected
  const focus = React.useMemo(() => (active && view.byId.has(active) ? focusSet(view, active) : null), [view, active])
  const matches = React.useMemo(() => searchItems(view, query, nodeMap), [view, query, nodeMap])
  const matchSet = React.useMemo(() => new Set(matches), [matches])

  const zoomBy = React.useCallback((f: number, cx = size.w / 2, cy = size.h / 2) => {
    setT((o) => {
      const k = Math.max(0.12, Math.min(2.5, o.k * f))
      return { k, x: cx - ((cx - o.x) * k) / o.k, y: cy - ((cy - o.y) * k) / o.k }
    })
  }, [size])
  const centerOn = React.useCallback((id: string) => {
    const it = view.byId.get(id)
    if (!it) return
    setAnimate(true)
    setT((o) => {
      const k = Math.max(o.k, 0.8)
      return { k, x: size.w / 2 - (it.x + NODE_W / 2) * k, y: size.h / 2 - (it.y + NODE_H / 2) * k }
    })
    setTimeout(() => setAnimate(false), 320)
  }, [view, size])

  // wheel zoom (non-passive)
  React.useEffect(() => {
    const el = wrap.current
    if (!el) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      const r = el.getBoundingClientRect()
      if (e.ctrlKey || e.metaKey || Math.abs(e.deltaY) >= Math.abs(e.deltaX)) {
        if (e.shiftKey) {
          setT((o) => ({ ...o, x: o.x - e.deltaY }))
          return
        }
        zoomBy(Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.0018)), e.clientX - r.left, e.clientY - r.top)
      } else setT((o) => ({ ...o, x: o.x - e.deltaX, y: o.y - e.deltaY }))
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [zoomBy, viewMode])

  // drag pan
  const drag = React.useRef<{ x: number; y: number; moved: boolean } | null>(null)
  const onPointerDown = (e: React.PointerEvent) => {
    if (e.button !== 0) return
    wrap.current?.focus({ preventScroll: true })
    drag.current = { x: e.clientX, y: e.clientY, moved: false }
  }
  const onPointerMove = (e: React.PointerEvent) => {
    const d = drag.current
    if (!d) return
    const dx = e.clientX - d.x
    const dy = e.clientY - d.y
    if (!d.moved && Math.abs(dx) + Math.abs(dy) < 4) return
    d.moved = true
    d.x = e.clientX
    d.y = e.clientY
    setT((o) => ({ ...o, x: o.x + dx, y: o.y + dy }))
  }
  const onPointerUp = () => {
    setTimeout(() => (drag.current = null), 0)
  }
  const wasDrag = () => !!drag.current?.moved

  // option helpers
  const toggleKey = (key: string | undefined, collapsed: boolean) => key && setOpts((o) => ({ ...o, overrides: { ...o.overrides, [key]: collapsed } }))
  const expandAll = () => {
    setViewMode('graph')
    setOpts((o) => ({ ...o, detail: 'visuals', overrides: Object.fromEntries(allToggleKeys(graph).map((k) => [k, false])) }))
  }
  const collapseAll = () => setOpts((o) => ({ ...o, detail: 'reports', overrides: Object.fromEntries(allToggleKeys(graph).filter((k) => k.startsWith('group:')).map((k) => [k, true])) }))
  const setDetail = (d: Detail) => setOpts((o) => ({ ...o, detail: d, overrides: Object.fromEntries(Object.entries(o.overrides).filter(([k]) => k.startsWith('group:'))) }))
  const isolate = (it: Item) => {
    setOpts((o) => ({ ...o, isolate: it.members }))
    setSelected(it.id)
  }
  const exportName = `lineage-${(graph.nodes.find((n) => n.start)?.name ?? 'graph').replace(/[^\w.-]+/g, '_')}`

  const onKey = (e: React.KeyboardEvent) => {
    if ((e.target as HTMLElement).tagName === 'INPUT') {
      if (e.key === 'Escape') { setQuery(''); wrap.current?.focus() }
      return
    }
    const k = e.key.toLowerCase()
    if (k === 'escape') { if (selected) setSelected(null); else if (opts.isolate) setOpts((o) => ({ ...o, isolate: null })); else if (full) setFull(false) }
    else if (k === 'f') fitNow()
    else if (k === '+' || k === '=') zoomBy(1.2)
    else if (k === '-' || k === '_') zoomBy(1 / 1.2)
    else if (k === 'e') expandAll()
    else if (k === 'c') collapseAll()
    else if (k === 's') { e.preventDefault(); searchRef.current?.focus() }
    else if (k === 't') setViewMode((m) => (m === 'table' ? 'graph' : 'table'))
    else if (k === 'o') setViewMode((m) => (m === 'overview' ? 'graph' : 'overview'))
    else if (k === 'i' && selected) { const it = view.byId.get(selected); if (it) isolate(it) }
    else if (k === 'enter' && selected) { const it = view.byId.get(selected); if (it?.kind === 'node') openNode(it.members[0]) }
    else return
    e.preventDefault()
  }

  const typeCounts = React.useMemo(() => {
    const m = new Map<string, number>()
    for (const n of graph.nodes) m.set(n.type, (m.get(n.type) ?? 0) + 1)
    return [...m.entries()].sort((a, b) => (graph.nodes.find((n) => n.type === a[0])!.lane - graph.nodes.find((n) => n.type === b[0])!.lane))
  }, [graph])
  const activeFilters = opts.hiddenTypes.length + opts.impacts.length + opts.confidences.length + (isFinite(opts.maxDepth) ? 1 : 0)
  const sel = selected ? view.byId.get(selected) : null

  const graphH = full ? undefined : height
  const vw = { x: -t.x / t.k, y: -t.y / t.k, w: size.w / t.k, h: size.h / t.k }

  return (
    <div className={cn('flex flex-col bg-card', full && 'fixed inset-0 z-50')}>
      {/* toolbar */}
      <div className="flex flex-wrap items-center gap-2 border-b px-3 py-2">
        <Seg<ViewMode>
          value={viewMode}
          onChange={setViewMode}
          options={[
            { value: 'graph', label: <><Workflow />Graph</>, title: 'Swim-lane graph (G)' },
            { value: 'overview', label: <><Rows3 />Overview</>, title: 'Collapsed, Sankey-like overview (O)' },
            { value: 'table', label: <><Table2 />Table</>, title: 'Table of every object (T)' },
          ]}
        />
        {viewMode !== 'table' && (
          <Seg<Detail>
            value={opts.detail}
            onChange={setDetail}
            options={[
              { value: 'reports', label: <><FileBarChart2 />Reports</>, title: 'Collapse visuals and pages under their report' },
              { value: 'pages', label: <><LayoutPanelTop />Pages</>, title: 'Collapse visuals under their page' },
              { value: 'visuals', label: <><BarChart3 />Visuals</>, title: 'Show every visual' },
            ]}
          />
        )}
        {viewMode !== 'table' && (
          <div className="flex items-center">
            <TB title="Expand everything (E)" onClick={expandAll}><Expand />Expand all</TB>
            <TB title="Collapse groups (C)" onClick={collapseAll}><Shrink />Collapse</TB>
          </div>
        )}
        <div className="relative ml-auto">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            ref={searchRef}
            value={query}
            onChange={(e) => { setQuery(e.target.value); setMatchIdx(0) }}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && matches.length) {
                const id = matches[matchIdx % matches.length]
                setSelected(id)
                centerOn(id)
                setMatchIdx((i) => i + 1)
              }
              if (e.key === 'Escape') setQuery('')
            }}
            placeholder="Find in graph…  (S)"
            className="h-8 w-52 rounded-md border border-input bg-background pl-8 pr-14 text-xs placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring/40"
          />
          {query && <span className="absolute right-2 top-1/2 -translate-y-1/2 text-[10.5px] tabular-nums text-muted-foreground">{matches.length ? `${(matchIdx % matches.length) + 1}/${matches.length}` : '0'}</span>}
        </div>
        <TB active={showFilters || activeFilters > 0} title="Filter by type, impact, confidence and depth" onClick={() => setShowFilters((s) => !s)}>
          <Filter />Filters{activeFilters > 0 && <span className="rounded-full bg-primary px-1.5 text-[10px] text-primary-foreground">{activeFilters}</span>}
        </TB>
        <ExportMenu
          disabled={viewMode === 'table'}
          onSvg={() => svgRef.current && downloadBlob(new Blob([svgString(svgRef.current, view, p.bg)], { type: 'image/svg+xml' }), `${exportName}.svg`)}
          onPng={() => svgRef.current && exportPng(svgRef.current, view, p.bg, `${exportName}.png`)}
        />
        <TB title={full ? 'Exit full screen (Esc)' : 'Full screen'} onClick={() => setFull((f) => !f)}>{full ? <Minimize2 /> : <Maximize2 />}</TB>
      </div>

      {showFilters && (
        <div className="grid gap-3 border-b bg-muted/30 px-4 py-3 text-xs animate-fade-in">
          <FilterRow label="Show">
            {typeCounts.map(([type, n]) => (
              <Chip key={type} color={meta(type).hex} on={!opts.hiddenTypes.includes(type)}
                onClick={() => setOpts((o) => ({ ...o, hiddenTypes: o.hiddenTypes.includes(type) ? o.hiddenTypes.filter((x) => x !== type) : [...o.hiddenTypes, type] }))}>
                {meta(type).label}<span className="text-muted-foreground">{n}</span>
              </Chip>
            ))}
          </FilterRow>
          <div className="flex flex-wrap gap-x-8 gap-y-3">
            {mode === 'impact' && (
              <FilterRow label="Impact">
                {(['breaks', 'values_may_change'] as Impact[]).map((i) => (
                  <Chip key={i} color={i === 'breaks' ? p.breaks : p.may} on={!opts.impacts.length || opts.impacts.includes(i)}
                    onClick={() => setOpts((o) => ({ ...o, impacts: toggleOnly(o.impacts, i, ['breaks', 'values_may_change']) }))}>
                    {i === 'breaks' ? 'Breaks' : 'May change'}
                  </Chip>
                ))}
              </FilterRow>
            )}
            <FilterRow label="Confidence">
              {(['high', 'medium', 'low'] as Confidence[]).map((c) => (
                <Chip key={c} on={!opts.confidences.length || opts.confidences.includes(c)} onClick={() => setOpts((o) => ({ ...o, confidences: toggleOnly(o.confidences, c, ['high', 'medium', 'low']) }))}>
                  {c}
                </Chip>
              ))}
            </FilterRow>
            <FilterRow label="Depth">
              <input type="range" min={1} max={Math.max(1, view.maxDepth)} value={isFinite(opts.maxDepth) ? opts.maxDepth : view.maxDepth}
                onChange={(e) => { const v = Number(e.target.value); setOpts((o) => ({ ...o, maxDepth: v >= view.maxDepth ? Infinity : v })) }}
                className="w-40 accent-[hsl(var(--primary))]" />
              <span className="tabular-nums text-muted-foreground">{isFinite(opts.maxDepth) ? `${opts.maxDepth} hop${opts.maxDepth > 1 ? 's' : ''}` : 'all'} / {view.maxDepth}</span>
            </FilterRow>
            {activeFilters > 0 && (
              <button className="text-primary hover:underline" onClick={() => setOpts((o) => ({ ...o, hiddenTypes: [], impacts: [], confidences: [], maxDepth: Infinity }))}>Reset filters</button>
            )}
          </div>
          <p className="text-[11px] text-muted-foreground">Hidden objects are bridged: lineage through them is still drawn, so paths never disappear.</p>
        </div>
      )}

      {(opts.isolate || view.hiddenCount > 0 || graph.truncated) && viewMode !== 'table' && (
        <div className="flex flex-wrap items-center gap-2 border-b px-3 py-1.5 text-[11.5px] text-muted-foreground">
          {opts.isolate && (
            <Badge className="border-primary/30 bg-primary/10 text-primary">
              <Crosshair /> Showing only the path through {opts.isolate.length === 1 ? nodeMap.get(opts.isolate[0])?.name : `${opts.isolate.length} objects`}
              <button className="ml-1 hover:opacity-70" title="Show everything (Esc)" onClick={() => setOpts((o) => ({ ...o, isolate: null }))}><X /></button>
            </Badge>
          )}
          {view.hiddenCount > 0 && <span>{view.hiddenCount} of {view.totalNodes} objects hidden by filters</span>}
          {graph.truncated && <span>Graph truncated to the nearest {graph.nodes.length} of {graph.total ?? '?'} objects – the lists below have everything.</span>}
        </div>
      )}

      {viewMode === 'table' ? (
        <GraphTable graph={graph} view={view} height={full ? undefined : height} onOpen={openNode} />
      ) : (
        <div
          ref={wrap}
          tabIndex={0}
          onKeyDown={onKey}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerLeave={onPointerUp}
          onClick={() => { if (!wasDrag()) setSelected(null) }}
          className={cn('relative overflow-hidden outline-none select-none', full && 'flex-1')}
          style={{ height: graphH, background: p.bg, cursor: drag.current?.moved ? 'grabbing' : 'grab' }}
        >
          {view.items.length === 0 ? (
            <div className="flex h-full items-center justify-center text-sm text-muted-foreground">Nothing matches the current filters.</div>
          ) : (
            <svg ref={svgRef} width={size.w} height={size.h} className="block" fontFamily='"Inter Variable", Inter, "Segoe UI", system-ui, sans-serif'>
              <defs>
                {[['breaks', p.breaks], ['may', p.may], ['up', p.primary], ['dim', p.neutral]].map(([k, c]) => (
                  <marker key={k} id={`ll-arrow-${k}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse" markerUnits="userSpaceOnUse">
                    <path d="M0,1 L9,5 L0,9 z" fill={c} />
                  </marker>
                ))}
              </defs>
              <g data-root transform={`translate(${t.x},${t.y}) scale(${t.k})`} style={{ transition: animate ? 'transform .3s cubic-bezier(.2,.8,.2,1)' : undefined }}>
                {/* lane stripes */}
                {view.lanes.map((l, i) => (
                  <g key={l.lane}>
                    <rect x={l.x} y={-4000} width={l.w} height={view.height + 8000} fill={i % 2 ? p.laneB : p.laneA} />
                    <line x1={l.x} x2={l.x} y1={-4000} y2={view.height + 4000} stroke={p.laneLine} />
                    <g data-export-only display="none">
                      <text x={l.x + 16} y={26} fontSize={11} fontWeight={700} letterSpacing={0.6} fill={p.header}>{LANE_LABELS[l.lane].toUpperCase()}</text>
                    </g>
                  </g>
                ))}
                {view.containers.map((c) => (
                  <ContainerBox key={c.key} c={c} p={p} dim={!!focus && !view.items.some((i) => i.container && c.key.startsWith(i.container + '@') && focus.nodes.has(i.id))} onToggle={() => toggleKey(c.toggleKey, true)} />
                ))}
                {/* edges: base layer */}
                <g fill="none">
                  {view.edges.map((e) => {
                    const on = focus ? focus.edges.has(e.id) : true
                    const color = focus && !on ? p.neutral : edgeColor(p, mode, e.impact)
                    const mk = focus && !on ? 'dim' : mode === 'upstream' ? 'up' : e.impact === 'breaks' ? 'breaks' : 'may'
                    const w = Math.min(5, 1.3 + Math.log2(e.count) * 0.9) * (focus && on ? 1.35 : 1)
                    return (
                      <path
                        key={e.id}
                        d={edgePath(e.points)}
                        stroke={color}
                        strokeWidth={w}
                        strokeOpacity={focus ? (on ? 0.95 : 0.08) : e.impact === 'breaks' || mode === 'upstream' ? 0.55 : 0.6}
                        strokeDasharray={mode === 'impact' && e.impact !== 'breaks' ? '5 4' : undefined}
                        markerEnd={`url(#ll-arrow-${mk})`}
                        style={{ transition: 'stroke-opacity .15s' }}
                      >
                        <title>{`${view.byId.get(e.source)?.label} → ${view.byId.get(e.target)?.label}${e.count > 1 ? ` (${e.count} links)` : ''}${e.reasons.length ? '\n' + e.reasons.join('\n') : ''}`}</title>
                      </path>
                    )
                  })}
                </g>
                {view.items.map((it) => (
                  <NodeBox
                    key={it.id}
                    it={it}
                    p={p}
                    state={{
                      dim: (!!focus && !focus.nodes.has(it.id)) || (!!query && matches.length > 0 && !matchSet.has(it.id) && !focus),
                      match: matchSet.has(it.id),
                      selected: selected === it.id,
                      hot: hover === it.id,
                    }}
                    onClick={(e) => { e.stopPropagation(); if (!wasDrag()) setSelected((s) => (s === it.id ? null : it.id)) }}
                    onDouble={() => (it.kind === 'node' ? openNode(it.members[0]) : toggleKey(it.toggleKey, false))}
                    onEnter={() => !drag.current && setHover(it.id)}
                    onLeave={() => setHover(null)}
                    onToggle={() => toggleKey(it.toggleKey, false)}
                  />
                ))}
              </g>
            </svg>
          )}

          {/* sticky lane headers */}
          <div className="pointer-events-none absolute inset-x-0 top-0 h-9 overflow-hidden" style={{ background: `linear-gradient(${p.bg}, ${p.bg}ee 70%, transparent)` }}>
            {view.lanes.map((l) => (
              <div key={l.lane} className="absolute top-0 flex h-9 items-center gap-1.5 overflow-hidden whitespace-nowrap px-3 text-[10.5px] font-semibold uppercase tracking-wider"
                style={{ left: l.x * t.k + t.x, width: l.w * t.k, color: p.header, borderLeft: `1px solid ${p.laneLine}` }}>
                <span className="truncate">{LANE_LABELS[l.lane]}</span>
                <span className="rounded-full px-1.5 py-px text-[10px] font-medium normal-case tracking-normal" style={{ background: p.laneLine, color: p.muted }}>{l.count}</span>
              </div>
            ))}
          </div>

          {/* inspector */}
          {sel && <Inspector it={sel} nodeMap={nodeMap} view={view} mode={mode} onClose={() => setSelected(null)} onOpen={openNode}
            onIsolate={() => isolate(sel)} onExpand={() => toggleKey(sel.toggleKey, false)}
            onCollapse={sel.container ? () => toggleKey(view.containers.find((c) => c.key.startsWith(sel.container + '@'))?.toggleKey, true) : undefined} />}

          {/* zoom controls */}
          <div className="absolute bottom-3 left-3 flex flex-col overflow-hidden rounded-lg border bg-card shadow-soft" onClick={(e) => e.stopPropagation()} onPointerDown={(e) => e.stopPropagation()}>
            {[
              [Plus, 'Zoom in (+)', () => zoomBy(1.2)],
              [Minus, 'Zoom out (−)', () => zoomBy(1 / 1.2)],
              [ScanSearch, 'Fit to view (F)', () => fitNow()],
              [Keyboard, 'Keyboard shortcuts', () => setShowKeys((s) => !s)],
            ].map(([I, title, fn], i) => {
              const Ic = I as typeof Plus
              return <button key={i} title={title as string} onClick={fn as () => void} className="flex size-8 items-center justify-center border-b text-muted-foreground last:border-b-0 hover:bg-muted hover:text-foreground"><Ic className="size-3.5" /></button>
            })}
          </div>
          {showKeys && (
            <div className="absolute bottom-3 left-14 w-64 rounded-lg border bg-card p-3 text-[11.5px] shadow-lg animate-fade-in" onClick={(e) => e.stopPropagation()}>
              <div className="mb-2 font-semibold">Keyboard shortcuts</div>
              {[['F', 'Fit to view'], ['+ / −', 'Zoom'], ['E / C', 'Expand all / collapse'], ['S', 'Find in graph'], ['O', 'Overview'], ['T', 'Table view'], ['I', 'Isolate selected path'], ['Enter', 'Open details'], ['Esc', 'Clear selection / isolation']].map(([k, d]) => (
                <div key={k} className="flex items-center justify-between py-0.5"><span className="text-muted-foreground">{d}</span><Kbd>{k}</Kbd></div>
              ))}
              <div className="mt-2 text-muted-foreground">Drag to pan, scroll to zoom, Shift+scroll to pan sideways.</div>
            </div>
          )}

          {/* minimap */}
          {view.items.length > 12 && (
            <Minimap view={view} p={p} vw={vw} onJump={(x, y) => setT((o) => ({ ...o, x: size.w / 2 - x * o.k, y: size.h / 2 - y * o.k }))} />
          )}
        </div>
      )}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t px-3 py-2 text-[11px] text-muted-foreground">
        <GraphLegend mode={mode} />
        <span className="ml-auto hidden lg:inline">Hover to trace · click to focus · double-click to expand or open · <Kbd>F</Kbd> fit</span>
      </div>
    </div>
  )
}

function toggleOnly<T>(cur: T[], v: T, all: T[]): T[] {
  const on = cur.length ? cur : all
  const next = on.includes(v) ? on.filter((x) => x !== v) : [...on, v]
  return next.length === all.length || next.length === 0 ? [] : next
}

function FilterRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="w-20 shrink-0 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{label}</span>
      {children}
    </div>
  )
}

function ExportMenu({ onPng, onSvg, disabled }: { onPng: () => void; onSvg: () => void; disabled?: boolean }) {
  const [open, setOpen] = React.useState(false)
  return (
    <div className="relative">
      <TB title="Export the graph as an image" onClick={() => !disabled && setOpen((o) => !o)} className={disabled ? 'opacity-40' : ''}><Download />Export</TB>
      {open && (
        <div className="absolute right-0 top-9 z-20 w-40 overflow-hidden rounded-lg border bg-popover py-1 text-xs shadow-lg animate-fade-in" onMouseLeave={() => setOpen(false)}>
          <button className="block w-full px-3 py-2 text-left hover:bg-muted" onClick={() => { onPng(); setOpen(false) }}>PNG image (2×)</button>
          <button className="block w-full px-3 py-2 text-left hover:bg-muted" onClick={() => { onSvg(); setOpen(false) }}>SVG (vector)</button>
        </div>
      )}
    </div>
  )
}

function Minimap({ view, p, vw, onJump }: { view: View; p: Pal; vw: { x: number; y: number; w: number; h: number }; onJump: (x: number, y: number) => void }) {
  const W = 190
  const H = Math.max(60, Math.min(140, (W * view.height) / view.width))
  const s = Math.min(W / view.width, H / view.height)
  const jump = (e: React.PointerEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect()
    onJump((e.clientX - r.left) / s, (e.clientY - r.top) / s)
  }
  return (
    <div className="absolute bottom-3 right-3 overflow-hidden rounded-lg border bg-card" onClick={(e) => e.stopPropagation()} onPointerDown={(e) => e.stopPropagation()}>
      <svg width={view.width * s} height={view.height * s} onPointerDown={jump} onPointerMove={(e) => e.buttons === 1 && jump(e)} style={{ cursor: 'crosshair', display: 'block' }}>
        {view.lanes.map((l, i) => <rect key={l.lane} x={l.x * s} y={0} width={l.w * s} height={view.height * s} fill={i % 2 ? 'transparent' : p.laneA} />)}
        {view.containers.map((c) => <rect key={c.key} x={c.x * s} y={c.y * s} width={c.w * s} height={c.h * s} fill={p.container} stroke={p.containerBorder} strokeWidth={0.5} rx={2} />)}
        {view.items.map((it) => <rect key={it.id} x={it.x * s} y={it.y * s} width={it.w * s} height={Math.max(1.5, it.h * s)} rx={1} fill={it.kind === 'report' ? meta('report').hex : it.kind === 'page' ? meta('page').hex : meta(it.type).hex} opacity={0.75} />)}
        <rect x={vw.x * s} y={vw.y * s} width={vw.w * s} height={vw.h * s} fill={p.primary} fillOpacity={0.08} stroke={p.primary} strokeWidth={1.2} rx={2} />
      </svg>
    </div>
  )
}

function Inspector({ it, nodeMap, view, mode, onClose, onOpen, onIsolate, onExpand, onCollapse }: {
  it: Item; nodeMap: Map<string, GraphNode>; view: View; mode: Mode; onClose: () => void; onOpen: (id: string) => void; onIsolate: () => void; onExpand: () => void; onCollapse?: () => void
}) {
  const first = nodeMap.get(it.members[0])
  const incoming = view.edges.filter((e) => e.target === it.id)
  const outgoing = view.edges.filter((e) => e.source === it.id)
  const reasons = [...new Set(incoming.flatMap((e) => e.reasons))].slice(0, 3)
  const typeLabel = it.kind === 'report' ? 'Report (collapsed)' : it.kind === 'page' ? 'Page (collapsed)' : it.kind === 'group' ? 'Group (collapsed)' : meta(it.type).label
  return (
    <div className="absolute right-3 top-11 w-80 rounded-lg border bg-popover shadow-xl animate-fade-in" onClick={(e) => e.stopPropagation()} onPointerDown={(e) => e.stopPropagation()}>
      <div className="flex items-start gap-3 border-b p-3">
        <div className="min-w-0 flex-1">
          <div className="text-[10.5px] font-semibold uppercase tracking-wide text-muted-foreground">{typeLabel}</div>
          <div className="mt-0.5 break-words font-mono text-[13px] font-semibold leading-snug">{it.kind === 'node' ? first?.display : it.label}</div>
          <div className="mt-0.5 text-xs text-muted-foreground">{it.sub}</div>
        </div>
        <button onClick={onClose} className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground" title="Close (Esc)"><X className="size-3.5" /></button>
      </div>
      <div className="space-y-2.5 p-3 text-xs">
        <div className="flex flex-wrap gap-1.5">
          {it.kind === 'node' && <TypeBadge type={it.type} />}
          {mode === 'impact' && <ImpactBadge impact={it.impact} />}
          <ConfidenceBadge c={it.confidence} />
          {first?.type === 'visual' && <Badge>{visualTypeLabel(first.visual_type)}</Badge>}
        </div>
        <div className="flex gap-4 text-muted-foreground">
          <span><b className="text-foreground">{incoming.reduce((s, e) => s + e.count, 0)}</b> in</span>
          <span><b className="text-foreground">{outgoing.reduce((s, e) => s + e.count, 0)}</b> out</span>
          {isFinite(it.depth) && <span><b className="text-foreground">{it.depth}</b> hop{it.depth === 1 ? '' : 's'} from start</span>}
        </div>
        {reasons.length > 0 && <div className="rounded-md bg-muted/60 px-2 py-1.5 font-mono text-[11px] text-muted-foreground">{reasons.map((r) => <div key={r} className="truncate" title={r}>{r}</div>)}</div>}
        {it.kind !== 'node' && (
          <div className="max-h-40 overflow-y-auto rounded-md border scrollbar-thin">
            {it.members.slice(0, 40).map((m) => {
              const n = nodeMap.get(m)!
              return (
                <button key={m} onClick={() => onOpen(m)} className="flex w-full items-center gap-2 px-2 py-1 text-left hover:bg-muted">
                  <span className="size-1.5 shrink-0 rounded-full" style={{ background: meta(n.type).hex }} />
                  <span className="truncate">{n.type === 'visual' ? `${n.name} · ${n.page_name}` : n.name}</span>
                </button>
              )
            })}
            {it.members.length > 40 && <div className="px-2 py-1 text-muted-foreground">+{it.members.length - 40} more</div>}
          </div>
        )}
        <div className="flex flex-wrap gap-1.5 pt-1">
          {it.kind === 'node' && <button onClick={() => onOpen(it.members[0])} className="inline-flex h-7 items-center gap-1 rounded-md bg-primary px-2.5 font-medium text-primary-foreground hover:bg-primary/90"><Focus className="size-3.5" />Details</button>}
          {it.kind !== 'node' && <button onClick={onExpand} className="inline-flex h-7 items-center gap-1 rounded-md bg-primary px-2.5 font-medium text-primary-foreground hover:bg-primary/90"><Expand className="size-3.5" />Expand</button>}
          <button onClick={onIsolate} className="inline-flex h-7 items-center gap-1 rounded-md border px-2.5 font-medium hover:bg-muted" title="Show only the path through this (I)"><Crosshair className="size-3.5" />{first?.type === 'visual' ? 'Only path to this visual' : 'Isolate path'}</button>
          {onCollapse && <button onClick={onCollapse} className="inline-flex h-7 items-center gap-1 rounded-md border px-2.5 font-medium hover:bg-muted"><Shrink className="size-3.5" />Collapse group</button>}
        </div>
      </div>
    </div>
  )
}

function GraphTable({ graph, view, height, onOpen }: { graph: SubGraph; view: View; height?: number; onOpen: (id: string) => void }) {
  const rows = React.useMemo(
    () => graph.nodes.filter((n) => view.visibleOf.has(n.id)).sort((a, b) => a.lane - b.lane || a.sublevel - b.sublevel || a.group_label.localeCompare(b.group_label) || a.name.localeCompare(b.name)),
    [graph, view],
  )
  return (
    <div className="overflow-auto scrollbar-thin" style={{ height }}>
      <table className="w-full text-left text-xs">
        <thead className="sticky top-0 z-10 bg-card shadow-[0_1px_0_hsl(var(--border))]">
          <tr className="text-[11px] uppercase tracking-wide text-muted-foreground">
            {['Layer', 'Object', 'Type', 'Group', 'Impact', 'Confidence', 'Hops'].map((h) => <th key={h} className="px-3 py-2 font-semibold">{h}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((n) => (
            <tr key={n.id} onClick={() => onOpen(n.id)} className={cn('cursor-pointer border-b border-border/60 hover:bg-muted/50', n.start && 'bg-primary/5')}>
              <td className="whitespace-nowrap px-3 py-1.5 text-muted-foreground">{LANE_LABELS[n.lane]}</td>
              <td className="px-3 py-1.5 font-mono font-medium">{n.type === 'visual' ? `${n.name}` : n.display}</td>
              <td className="px-3 py-1.5"><TypeBadge type={n.type} /></td>
              <td className="px-3 py-1.5 text-muted-foreground">{n.type === 'visual' ? `${n.report_name} › ${n.page_name}` : n.group_label}</td>
              <td className="px-3 py-1.5"><ImpactBadge impact={n.impact} /></td>
              <td className="px-3 py-1.5"><ConfidenceBadge c={n.confidence} /></td>
              <td className="px-3 py-1.5 tabular-nums text-muted-foreground">{n.depth}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {!rows.length && <div className="py-10 text-center text-sm text-muted-foreground"><Network className="mx-auto mb-2 size-5" />Nothing matches the current filters.</div>}
    </div>
  )
}

export function GraphLegend({ mode }: { mode: Mode }) {
  const layers: [string, string][] = [
    ['dbt_source_column', 'Source'], ['dbt_model_column', 'dbt'], ['snowflake_view_column', 'Snowflake'],
    ['pbi_model_column', 'PBI column'], ['measure', 'Measure'], ['rls_role', 'RLS'], ['visual', 'Visual'],
  ]
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
      {layers.map(([t, l]) => (
        <span key={t} className="inline-flex items-center gap-1.5"><span className="size-2 rounded-sm" style={{ background: meta(t).hex }} />{l}</span>
      ))}
      <span className="mx-1 h-3 w-px bg-border" />
      {mode === 'impact' ? (
        <>
          <span className="inline-flex items-center gap-1.5" title="The object will error if the column is dropped or renamed"><span className="h-0.5 w-4 rounded bg-red-500" />breaks</span>
          <span className="inline-flex items-center gap-1.5" title="The object still works, but its numbers may differ (filters, joins, aggregations)"><span className="h-0 w-4 border-t-2 border-dashed border-amber-500" />may change</span>
        </>
      ) : (
        <span className="inline-flex items-center gap-1.5"><span className="h-0.5 w-4 rounded bg-primary" />feeds into</span>
      )}
      <span className="inline-flex items-center gap-1.5"><span className="relative inline-block h-3 w-4"><span className="absolute inset-0 translate-x-0.5 -translate-y-0.5 rounded-sm border bg-muted" /><span className="absolute inset-0 rounded-sm border bg-card" /></span>collapsed group</span>
    </div>
  )
}

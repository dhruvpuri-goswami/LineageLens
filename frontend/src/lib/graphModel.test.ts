import { describe, expect, it } from 'vitest'
import type { SubGraph } from './api'
import { allToggleKeys, buildView, defaultOptions, edgePath, focusSet, pav, NODE_H } from './graphModel'
import large from './__fixtures__/large_net_revenue.json'
import standard from './__fixtures__/standard_net_amount.json'
import upstream from './__fixtures__/large_upstream_visual.json'

const L = large as unknown as SubGraph
const S = standard as unknown as SubGraph
const U = upstream as unknown as SubGraph

function noOverlaps(view: ReturnType<typeof buildView>) {
  const byCol = new Map<number, { y: number; h: number; id: string }[]>()
  for (const it of view.items) (byCol.get(it.col) ?? byCol.set(it.col, []).get(it.col)!).push({ y: it.y, h: it.h, id: it.id })
  for (const list of byCol.values()) {
    list.sort((a, b) => a.y - b.y)
    for (let i = 1; i < list.length; i++) expect(list[i].y, `${list[i - 1].id} overlaps ${list[i].id}`).toBeGreaterThanOrEqual(list[i - 1].y + list[i - 1].h - 0.01)
  }
  // containers in a column must not overlap each other
  const cs = new Map<number, typeof view.containers>()
  for (const c of view.containers) (cs.get(c.col) ?? cs.set(c.col, []).get(c.col)!).push(c)
  for (const list of cs.values()) {
    list.sort((a, b) => a.y - b.y)
    for (let i = 1; i < list.length; i++) expect(list[i].y).toBeGreaterThanOrEqual(list[i - 1].y + list[i - 1].h - 0.01)
  }
}

function edgesClearOfNodes(view: ReturnType<typeof buildView>) {
  // every straight in-column edge segment (through a reserved slot) must not cross a node box
  for (const e of view.edges) {
    for (let i = 1; i + 1 < e.points.length; i += 2) {
      const [x1, y] = e.points[i]
      const [x2] = e.points[i + 1]
      for (const it of view.items) {
        if (it.x >= x1 && it.x + it.w <= x2) expect(y < it.y || y > it.y + it.h, `${e.id} crosses ${it.id}`).toBe(true)
      }
    }
  }
}

describe('graph model', () => {
  it('pav keeps order and minimises movement', () => {
    expect(pav([3, 1, 2], [1, 1, 1])).toEqual([2, 2, 2])
    expect(pav([0, 5, 10], [1, 1, 1])).toEqual([0, 5, 10])
  })

  it('collapses a high fan-out column into reports / pages by default', () => {
    const opts = defaultOptions(L)
    expect(opts.detail).not.toBe('visuals')
    const v = buildView(L, opts)
    const visuals = L.nodes.filter((n) => n.type === 'visual').length
    expect(visuals).toBeGreaterThanOrEqual(30)
    expect(v.items.filter((i) => i.kind === 'node' && i.type === 'visual')).toHaveLength(0)
    const pageItems = v.items.filter((i) => i.kind === 'page' || i.kind === 'report')
    expect(pageItems.reduce((s, i) => s + i.members.filter((m) => m.includes(':visual:')).length, 0)).toBe(visuals)
    expect(v.items.length).toBeLessThan(L.nodes.length / 1.5)
    // every real node is represented exactly once
    expect(v.visibleOf.size).toBe(L.nodes.length)
    noOverlaps(v)
    edgesClearOfNodes(v)
  })

  it('expands a page into its visuals inside a container', () => {
    const opts = { ...defaultOptions(L), detail: 'pages' as const }
    const page = L.nodes.find((n) => n.type === 'visual')!.page_id!
    const v = buildView(L, { ...opts, overrides: { [`page:${page}`]: false } })
    const inPage = v.items.filter((i) => i.container === `C:page:${page}`)
    expect(inPage.length).toBeGreaterThan(0)
    expect(inPage.every((i) => i.type === 'visual' || i.type === 'page')).toBe(true)
    expect(v.containers.some((c) => c.toggleKey === `page:${page}`)).toBe(true)
    noOverlaps(v)
  })

  it('expand all shows every object, still without overlaps or edges behind nodes', () => {
    const overrides = Object.fromEntries(allToggleKeys(L).map((k) => [k, false]))
    const v = buildView(L, { ...defaultOptions(L), detail: 'visuals', overrides })
    expect(v.items.filter((i) => i.kind === 'node')).toHaveLength(L.nodes.filter((n) => n.type !== 'report').length)
    noOverlaps(v)
    edgesClearOfNodes(v)
  })

  it('lanes are left-to-right and edges flow forward', () => {
    const v = buildView(L, defaultOptions(L))
    const lanes = v.lanes.map((l) => l.lane)
    expect([...lanes].sort((a, b) => a - b)).toEqual(lanes)
    for (const e of v.edges) {
      const s = v.byId.get(e.source)!
      const t = v.byId.get(e.target)!
      expect(t.col).toBeGreaterThanOrEqual(s.col)
      expect(edgePath(e.points).startsWith('M')).toBe(true)
    }
  })

  it('merges parallel edges', () => {
    const v = buildView(L, { ...defaultOptions(L), detail: 'reports' })
    expect(v.edges.some((e) => e.count > 1)).toBe(true)
    expect(new Set(v.edges.map((e) => e.id)).size).toBe(v.edges.length)
  })

  it('filters bridge edges through hidden objects', () => {
    const v = buildView(S, { ...defaultOptions(S), detail: 'visuals', hiddenTypes: ['measure', 'pbi_model_column', 'calc_column'] })
    expect(v.items.some((i) => i.type === 'measure')).toBe(false)
    const start = v.items.find((i) => i.start)!
    // the start column still reaches visuals
    const f = focusSet(v, start.id)
    expect([...f.nodes].some((id) => v.byId.get(id)?.type === 'visual' || v.byId.get(id)?.kind === 'page')).toBe(true)
    expect(v.hiddenCount).toBeGreaterThan(0)
  })

  it('isolates the path to one visual', () => {
    const vis = L.nodes.find((n) => n.type === 'visual')!
    const v = buildView(L, { ...defaultOptions(L), detail: 'visuals', isolate: [vis.id] })
    const reals = [...v.visibleOf.keys()]
    expect(reals).toContain(vis.id)
    expect(reals.filter((id) => L.nodes.find((n) => n.id === id)!.type === 'visual')).toEqual([vis.id])
  })

  it('overview collapses every group but keeps the start node', () => {
    const v = buildView(L, { ...defaultOptions(L), overview: true })
    expect(v.items.find((i) => i.start)?.kind).toBe('node')
    expect(v.items.length).toBeLessThan(25)
  })

  it('depth slider hides deeper objects', () => {
    const v = buildView(L, { ...defaultOptions(L), maxDepth: 1 })
    expect([...v.visibleOf.keys()].every((id) => L.nodes.find((n) => n.id === id)!.depth <= 1)).toBe(true)
  })

  it('upstream trace lays out with the start visual on the right', () => {
    const v = buildView(U, defaultOptions(U))
    const start = v.items.find((i) => i.start)!
    expect(start.col).toBe(Math.max(...v.items.map((i) => i.col)))
    noOverlaps(v)
    edgesClearOfNodes(v)
  })

  it('standard sample stays compact and readable', () => {
    const v = buildView(S, defaultOptions(S))
    expect(v.items.every((i) => i.h === NODE_H)).toBe(true)
    noOverlaps(v)
    edgesClearOfNodes(v)
  })
})

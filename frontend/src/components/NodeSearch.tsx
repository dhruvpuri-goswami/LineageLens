import * as React from 'react'
import Fuse from 'fuse.js'
import { Search, CornerDownLeft } from 'lucide-react'
import { useApp } from '@/lib/store'
import type { NodeLite } from '@/lib/api'
import { cn } from '@/lib/utils'
import { TypeIcon, Kbd } from './ui'
import { meta } from '@/lib/types'

export function NodeSearch({
  onSelect, types, placeholder = 'Search columns, measures, visuals…', autoFocus, className, size = 'md', shortcut,
}: {
  onSelect: (n: NodeLite) => void
  types?: string[]
  placeholder?: string
  autoFocus?: boolean
  className?: string
  size?: 'md' | 'lg'
  shortcut?: boolean
}) {
  const { nodes } = useApp()
  const [q, setQ] = React.useState('')
  const [open, setOpen] = React.useState(false)
  const [active, setActive] = React.useState(0)
  const inputRef = React.useRef<HTMLInputElement>(null)
  const pool = React.useMemo(() => nodes.filter((n) => n.type !== 'semantic_model' && (!types || types.includes(n.type))), [nodes, types])
  const fuse = React.useMemo(
    () => new Fuse(pool, { keys: [{ name: 'display', weight: 2 }, { name: 'name', weight: 3 }, 'parent', 'relation', 'id'], threshold: 0.38, ignoreLocation: true }),
    [pool],
  )
  const results = React.useMemo(() => {
    if (!q.trim()) return pool.filter((n) => (n.visuals ?? 0) > 0 && ['dbt_model_column', 'snowflake_view_column'].includes(n.type)).sort((a, b) => (b.visuals ?? 0) - (a.visuals ?? 0)).slice(0, 8)
    return fuse.search(q, { limit: 40 }).map((r) => r.item)
  }, [q, fuse, pool])

  React.useEffect(() => setActive(0), [q])
  React.useEffect(() => {
    if (!shortcut) return
    const h = (e: KeyboardEvent) => {
      if ((e.key === 'k' && (e.metaKey || e.ctrlKey)) || (e.key === '/' && !(e.target instanceof HTMLInputElement) && !(e.target instanceof HTMLTextAreaElement))) {
        e.preventDefault()
        inputRef.current?.focus()
        setOpen(true)
      }
    }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [shortcut])

  const choose = (n: NodeLite) => {
    onSelect(n)
    setQ('')
    setOpen(false)
    inputRef.current?.blur()
  }

  return (
    <div className={cn('relative', className)}>
      <div className={cn('flex items-center gap-2 rounded-md border border-input bg-card px-3 focus-within:border-ring focus-within:ring-2 focus-within:ring-ring/20', size === 'lg' ? 'h-10' : 'h-8')}>
        <Search className={cn('shrink-0 text-muted-foreground', size === 'lg' ? 'size-5' : 'size-4')} />
        <input
          ref={inputRef}
          autoFocus={autoFocus}
          value={q}
          placeholder={placeholder}
          onChange={(e) => {
            setQ(e.target.value)
            setOpen(true)
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown') { e.preventDefault(); setActive((a) => Math.min(a + 1, results.length - 1)) }
            else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)) }
            else if (e.key === 'Enter' && results[active]) choose(results[active])
            else if (e.key === 'Escape') { setOpen(false); inputRef.current?.blur() }
          }}
          className={cn('h-full w-full bg-transparent outline-none placeholder:text-muted-foreground', size === 'lg' ? 'text-base' : 'text-sm')}
        />
        {shortcut && !q && <Kbd>Ctrl K</Kbd>}
      </div>
      {open && results.length > 0 && (
        <div className="absolute z-50 mt-1.5 max-h-[420px] w-full min-w-[420px] overflow-auto rounded-lg border bg-popover p-1 shadow-xl scrollbar-thin animate-fade-in">
          {!q.trim() && <div className="px-2.5 pb-1 pt-1.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Most used warehouse columns</div>}
          {results.map((n, i) => (
            <button
              key={n.id}
              onMouseDown={(e) => { e.preventDefault(); choose(n) }}
              onMouseEnter={() => setActive(i)}
              className={cn('flex w-full items-center gap-3 rounded-md px-2.5 py-2 text-left', i === active && 'bg-accent')}
            >
              <TypeIcon type={n.type} />
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-medium">{n.name}</div>
                <div className="truncate text-xs text-muted-foreground">
                  {meta(n.type).label} · {n.type === 'visual' ? `${n.container} › ${n.parent}` : n.relation || n.parent}
                </div>
              </div>
              {(n.visuals ?? 0) > 0 && <span className="text-[11px] text-muted-foreground tabular-nums">{n.visuals} visuals</span>}
              {i === active && <CornerDownLeft className="size-3.5 text-muted-foreground" />}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

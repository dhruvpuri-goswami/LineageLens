import * as React from 'react'
import { HelpCircle, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { meta } from '@/lib/types'
import type { Confidence, Impact } from '@/lib/api'

type BtnVariant = 'default' | 'outline' | 'ghost' | 'secondary' | 'destructive'
export const Button = React.forwardRef<HTMLButtonElement, React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: BtnVariant; size?: 'sm' | 'md' | 'icon' }>(
  ({ className, variant = 'default', size = 'md', ...props }, ref) => (
    <button
      ref={ref}
      className={cn(
        'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-50 [&_svg]:size-4 [&_svg]:shrink-0',
        {
          default: 'bg-primary text-primary-foreground shadow-soft hover:bg-primary/90',
          outline: 'border border-input bg-card hover:bg-muted',
          ghost: 'hover:bg-muted',
          secondary: 'bg-muted text-foreground hover:bg-muted/70',
          destructive: 'bg-red-600 text-white hover:bg-red-600/90',
        }[variant],
        { sm: 'h-8 px-3 text-xs', md: 'h-9 px-4 text-sm', icon: 'h-9 w-9' }[size],
        className,
      )}
      {...props}
    />
  ),
)
Button.displayName = 'Button'

export function Card({ className, ...p }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('rounded-xl border bg-card text-card-foreground shadow-soft', className)} {...p} />
}
export function CardHeader({ title, description, icon, action, className }: { title: React.ReactNode; description?: React.ReactNode; icon?: React.ReactNode; action?: React.ReactNode; className?: string }) {
  return (
    <div className={cn('flex items-start justify-between gap-4 px-5 pt-4 pb-3', className)}>
      <div className="flex items-start gap-3 min-w-0">
        {icon && <div className="mt-0.5 text-muted-foreground [&_svg]:size-4">{icon}</div>}
        <div className="min-w-0">
          <h3 className="text-sm font-semibold leading-tight">{title}</h3>
          {description && <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>}
        </div>
      </div>
      {action}
    </div>
  )
}

export function Badge({ className, ...p }: React.HTMLAttributes<HTMLSpanElement>) {
  return <span className={cn('inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium leading-4 whitespace-nowrap [&_svg]:size-3', className)} {...p} />
}

export function ImpactBadge({ impact, className }: { impact: Impact | null | undefined; className?: string }) {
  if (!impact) return null
  return impact === 'breaks' ? (
    <Badge className={cn('border-red-500/30 bg-red-500/10 text-red-600 dark:text-red-400', className)}>
      <span className="size-1.5 rounded-full bg-red-500" /> Breaks
    </Badge>
  ) : (
    <Badge className={cn('border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-400', className)}>
      <span className="size-1.5 rounded-full bg-amber-500" /> Values may change
    </Badge>
  )
}

export function ConfidenceBadge({ c, className }: { c: Confidence | null | undefined; className?: string }) {
  if (!c) return null
  const cls = {
    high: 'border-emerald-500/30 text-emerald-700 dark:text-emerald-400',
    medium: 'border-yellow-500/40 text-yellow-700 dark:text-yellow-400',
    low: 'border-red-500/30 text-red-600 dark:text-red-400',
  }[c]
  return (
    <Badge className={cn('bg-transparent', cls, className)} title={`${c} confidence match`}>
      <span className="flex gap-[2px]">
        {[0, 1, 2].map((i) => (
          <span key={i} className={cn('h-2 w-[3px] rounded-sm', i < { high: 3, medium: 2, low: 1 }[c] ? 'bg-current' : 'bg-current/20 opacity-25')} />
        ))}
      </span>
      {c}
    </Badge>
  )
}

export function TypeBadge({ type, className }: { type: string; className?: string }) {
  const m = meta(type)
  const Icon = m.icon
  return (
    <Badge className={cn('border-transparent', m.bg, m.color, className)}>
      <Icon /> {m.short}
    </Badge>
  )
}

export function TypeIcon({ type, className }: { type: string; className?: string }) {
  const m = meta(type)
  const Icon = m.icon
  return (
    <span className={cn('inline-flex size-7 shrink-0 items-center justify-center rounded-md', m.bg, m.color, className)}>
      <Icon className="size-3.5" />
    </span>
  )
}

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(({ className, ...p }, ref) => (
  <input
    ref={ref}
    className={cn('h-9 w-full rounded-md border border-input bg-card px-3 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring/40', className)}
    {...p}
  />
))
Input.displayName = 'Input'

export function Segmented<T extends string>({ value, onChange, options, className }: { value: T; onChange: (v: T) => void; options: { value: T; label: React.ReactNode; hint?: string }[]; className?: string }) {
  return (
    <div className={cn('inline-flex rounded-lg border bg-muted/60 p-0.5', className)}>
      {options.map((o) => (
        <button
          key={o.value}
          title={o.hint}
          onClick={() => onChange(o.value)}
          className={cn(
            'inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-all [&_svg]:size-3.5',
            value === o.value ? 'bg-card text-foreground shadow-soft' : 'text-muted-foreground hover:text-foreground',
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

export function Tabs<T extends string>({ value, onChange, tabs, className }: { value: T; onChange: (v: T) => void; tabs: { value: T; label: React.ReactNode; count?: number }[]; className?: string }) {
  return (
    <div className={cn('flex gap-1 border-b px-3', className)}>
      {tabs.map((t) => (
        <button
          key={t.value}
          onClick={() => onChange(t.value)}
          className={cn(
            '-mb-px flex items-center gap-1.5 border-b-2 px-2.5 py-2.5 text-xs font-medium transition-colors',
            value === t.value ? 'border-primary text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground',
          )}
        >
          {t.label}
          {t.count !== undefined && <span className={cn('rounded-full px-1.5 text-[10px]', value === t.value ? 'bg-primary/15 text-primary' : 'bg-muted')}>{t.count}</span>}
        </button>
      ))}
    </div>
  )
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cn('size-4 animate-spin text-muted-foreground', className)} />
}

export function Stat({ label, value, icon, tone, sub, className }: { label: string; value: React.ReactNode; icon?: React.ReactNode; tone?: 'red' | 'amber' | 'brand' | 'green'; sub?: React.ReactNode; className?: string }) {
  const toneCls = { red: 'text-red-600 dark:text-red-400', amber: 'text-amber-600 dark:text-amber-400', brand: 'text-primary', green: 'text-emerald-600 dark:text-emerald-400' }
  return (
    <Card className={cn('px-4 py-3.5', className)}>
      <div className="flex items-center justify-between text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
        {label}
        {icon && <span className="[&_svg]:size-4 opacity-70">{icon}</span>}
      </div>
      <div className={cn('mt-1.5 text-2xl font-semibold tabular-nums tracking-tight', tone && toneCls[tone])}>{value}</div>
      {sub && <div className="mt-0.5 text-xs text-muted-foreground">{sub}</div>}
    </Card>
  )
}

export function EmptyState({ icon, title, children, className }: { icon?: React.ReactNode; title: string; children?: React.ReactNode; className?: string }) {
  return (
    <div className={cn('flex flex-col items-center justify-center px-6 py-14 text-center', className)}>
      {icon && <div className="mb-3 flex size-12 items-center justify-center rounded-xl bg-muted text-muted-foreground [&_svg]:size-6">{icon}</div>}
      <div className="text-sm font-semibold">{title}</div>
      {children && <div className="mt-1 max-w-md text-sm text-muted-foreground">{children}</div>}
    </div>
  )
}

export function ErrorBox({ error }: { error: string }) {
  return <div className="rounded-md border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-700 dark:text-red-300">{error}</div>
}

export function PageHeader({ title, description, actions, icon, eyebrow }: { title: string; description?: React.ReactNode; actions?: React.ReactNode; icon?: React.ReactNode; eyebrow?: string }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4 animate-rise">
      <div className="flex items-start gap-3.5">
        {icon && <div className="mt-0.5 flex size-9 items-center justify-center rounded-lg border bg-card text-primary shadow-soft [&_svg]:size-[18px]">{icon}</div>}
        <div>
          {eyebrow && <div className="mb-0.5 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">{eyebrow}</div>}
          <h1 className="text-[22px] font-semibold leading-tight tracking-tight">{title}</h1>
          {description && <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{description}</p>}
        </div>
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

/** Lightweight CSS tooltip (no portal, no external lib). */
export function Tip({ text, children, side = 'top', className, width = 'w-64' }: { text: React.ReactNode; children: React.ReactNode; side?: 'top' | 'bottom'; className?: string; width?: string }) {
  return (
    <span className={cn('group/tip relative inline-flex', className)}>
      {children}
      <span role="tooltip" className={cn(
        'pointer-events-none absolute left-1/2 z-50 -translate-x-1/2 rounded-md border bg-popover px-2.5 py-1.5 text-left text-[11.5px] font-normal normal-case leading-snug tracking-normal text-popover-foreground opacity-0 shadow-pop transition-opacity duration-150 group-hover/tip:opacity-100 group-focus-within/tip:opacity-100',
        width, side === 'top' ? 'bottom-full mb-1.5' : 'top-full mt-1.5')}>
        {text}
      </span>
    </span>
  )
}

export function InfoTip({ text, className, side }: { text: React.ReactNode; className?: string; side?: 'top' | 'bottom' }) {
  return (
    <Tip text={text} side={side} className={className}>
      <button type="button" tabIndex={0} aria-label="More info" className="inline-flex text-muted-foreground/70 hover:text-foreground"><HelpCircle className="size-3.5" /></button>
    </Tip>
  )
}

/** Plain-language definitions reused across pages. */
export const GLOSSARY = {
  breaks: 'Breaks: the object references this column directly, so it will error (blank visual, broken measure) if the column is dropped or renamed.',
  may: 'May change: the object still works, but its numbers can differ, for example through filters, joins, aggregations or RLS.',
  confidence: 'Confidence shows how sure the match is. High: exact name/source match. Medium: matched after normalising names or naming conventions. Low: heuristic match worth a manual check.',
  lineage: 'Lineage is the chain of dependencies from a warehouse column to everything built on top of it.',
  rls: 'RLS (row-level security) roles filter which rows a user can see in Power BI.',
  calcgroup: 'Calculation groups and field parameters let one measure or column be swapped dynamically in visuals.',
}

export function Kbd({ children }: { children: React.ReactNode }) {
  return <kbd className="rounded border bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">{children}</kbd>
}

export function useAsync<T>(fn: () => Promise<T>, deps: React.DependencyList) {
  const [state, set] = React.useState<{ data?: T; error?: string; loading: boolean }>({ loading: true })
  const [tick, setTick] = React.useState(0)
  React.useEffect(() => {
    let alive = true
    set((s) => ({ ...s, loading: true, error: undefined }))
    fn().then(
      (data) => alive && set({ data, loading: false }),
      (e) => alive && set({ error: String(e.message ?? e), loading: false }),
    )
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick])
  return { ...state, reload: () => setTick((t) => t + 1) }
}

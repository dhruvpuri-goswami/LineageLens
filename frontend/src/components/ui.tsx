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
          default: 'bg-primary text-primary-foreground hover:bg-primary/90',
          outline: 'border border-input bg-card hover:bg-muted',
          ghost: 'hover:bg-muted',
          secondary: 'bg-muted text-foreground hover:bg-muted/70',
          destructive: 'bg-red-600 text-white hover:bg-red-600/90',
        }[variant],
        { sm: 'h-7 px-2.5 text-xs', md: 'h-8 px-3 text-[13px]', icon: 'h-8 w-8' }[size],
        className,
      )}
      {...props}
    />
  ),
)
Button.displayName = 'Button'

export function Card({ className, ...p }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('rounded-lg border bg-card text-card-foreground', className)} {...p} />
}
export function CardHeader({ title, description, icon, action, className }: { title: React.ReactNode; description?: React.ReactNode; icon?: React.ReactNode; action?: React.ReactNode; className?: string }) {
  return (
    <div className={cn('flex items-start justify-between gap-4 px-4 pt-3.5 pb-3', className)}>
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
  return <span className={cn('inline-flex items-center gap-1 rounded border px-1.5 py-px text-[11px] font-medium leading-4 whitespace-nowrap [&_svg]:size-3', className)} {...p} />
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
    <div className={cn('inline-flex rounded-md border bg-muted/60 p-0.5', className)}>
      {options.map((o) => (
        <button
          key={o.value}
          title={o.hint}
          onClick={() => onChange(o.value)}
          className={cn(
            'inline-flex items-center gap-1.5 rounded px-2.5 py-1 text-xs font-medium transition-colors [&_svg]:size-3.5',
            value === o.value ? 'bg-card text-foreground ring-1 ring-border' : 'text-muted-foreground hover:text-foreground',
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
          {t.count !== undefined && <span className={cn('rounded px-1 text-[10px] tabular-nums', value === t.value ? 'bg-muted text-foreground' : 'bg-muted')}>{t.count}</span>}
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
      <div className="flex items-center justify-between text-[12px] font-medium text-muted-foreground">
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
      {icon && <div className="mb-3 flex size-10 items-center justify-center rounded-lg border bg-muted text-muted-foreground [&_svg]:size-5">{icon}</div>}
      <div className="text-sm font-semibold">{title}</div>
      {children && <div className="mt-1 max-w-md text-sm text-muted-foreground">{children}</div>}
    </div>
  )
}

export function ErrorBox({ error }: { error: string }) {
  return <div className="rounded-md border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-700 dark:text-red-300">{error}</div>
}

export function PageHeader({ title, description, actions, eyebrow }: { title: string; description?: React.ReactNode; actions?: React.ReactNode; icon?: React.ReactNode; eyebrow?: string }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4 border-b pb-4">
      <div>
        {eyebrow && <div className="mb-1 text-[12px] font-medium text-muted-foreground">{eyebrow}</div>}
        <h1 className="text-xl font-semibold leading-tight tracking-[-0.01em]">{title}</h1>
        {description && <p className="mt-1 max-w-3xl text-[13px] text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

/** GitHub logo (lucide no longer ships brand icons). */
export function GithubMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={className} fill="currentColor" aria-hidden>
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
    </svg>
  )
}

/** The LineageLens mark: a source node traced along one path to the object it lands on. */
export function BrandMark({ className, mono }: { className?: string; mono?: boolean }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden>
      <rect width="32" height="32" rx="7" className={mono ? 'fill-foreground' : undefined} fill={mono ? undefined : '#1E66F5'} />
      <g className={mono ? 'stroke-background' : undefined} stroke={mono ? undefined : '#fff'} fill="none">
        <circle cx="11" cy="10.5" r="3" strokeWidth="2.5" />
        <path d="M11 14.75V21.5H18.5" strokeWidth="3" strokeLinejoin="round" />
      </g>
      <circle cx="21.5" cy="21.5" r="3.5" className={mono ? 'fill-background' : undefined} fill={mono ? undefined : '#fff'} />
    </svg>
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

export function Kbd({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <kbd className={cn('inline-flex h-5 min-w-5 items-center justify-center whitespace-nowrap rounded-[4px] border border-border bg-muted px-1.5 font-sans text-[11px] font-medium leading-none text-muted-foreground', className)}>
      {children}
    </kbd>
  )
}

/** True on macOS / iOS, where the shortcut modifier is the command key. */
export function isMac(): boolean {
  if (typeof navigator === 'undefined') return false
  const p = (navigator as Navigator & { userAgentData?: { platform?: string } }).userAgentData?.platform || navigator.platform || navigator.userAgent
  return /mac|iphone|ipad|ipod/i.test(p)
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

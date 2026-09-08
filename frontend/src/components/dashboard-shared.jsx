/* eslint-disable react-refresh/only-export-components */
import { ArrowLeft, CircleDot } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'

// Single status style map shared by passenger / driver / admin / inbox.
// Keeps ride, vehicle and job states visually consistent everywhere.
export const STATUS_STYLES = {
  pending: 'border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400',
  clustered: 'border-violet-500/30 bg-violet-500/10 text-violet-600 dark:text-violet-400',
  clustered_status: 'border-violet-500/30 bg-violet-500/10 text-violet-600 dark:text-violet-400',
  assigned: 'border-sky-500/30 bg-sky-500/10 text-sky-600 dark:text-sky-400',
  arriving: 'border-teal-500/30 bg-teal-500/10 text-teal-600 dark:text-teal-300',
  in_progress: 'border-teal-500/30 bg-teal-500/10 text-teal-600 dark:text-teal-300',
  completed: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400',
  solved: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400',
  cancelled: 'border-rose-500/30 bg-rose-500/10 text-rose-600 dark:text-rose-400',
  idle: 'border-slate-500/30 bg-slate-500/10 text-slate-500 dark:text-slate-400',
  active: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400',
  en_route: 'border-sky-500/30 bg-sky-500/10 text-sky-600 dark:text-sky-400',
  offline: 'border-rose-500/30 bg-rose-500/10 text-rose-600 dark:text-rose-400',
  no_pending_requests: 'border-slate-500/30 bg-slate-500/10 text-slate-500 dark:text-slate-400',
}

export function StatusBadge({ status, className }) {
  const key = status || 'pending'
  return (
    <Badge
      variant="outline"
      className={cn('shrink-0 text-[10px] font-bold uppercase tracking-wide', STATUS_STYLES[key] || STATUS_STYLES.pending, className)}
    >
      {String(key).replace(/_/g, ' ')}
    </Badge>
  )
}

export function PageHeader({ title, description, onBack, backLabel = 'Back', actions }) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      {onBack && (
        <Button variant="ghost" size="sm" onClick={onBack} className="gap-1.5">
          <ArrowLeft className="h-4 w-4" /> {backLabel}
        </Button>
      )}
      <div className="min-w-0 flex-1">
        <h1 className="mob-page-title truncate">{title}</h1>
        {description && <p className="mt-0.5 truncate text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

export function StatCard({ icon: Icon, label, value, sub }) {
  return (
    <Card className="shadow-sm">
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-2">
          <p className="mob-section-label">{label}</p>
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10">
            <Icon className="h-4 w-4 text-primary" />
          </span>
        </div>
        <p className="mob-data mt-2 truncate text-2xl font-bold tracking-tight" title={String(value)}>{value}</p>
        {sub && <p className="mt-0.5 truncate text-xs text-muted-foreground">{sub}</p>}
      </CardContent>
    </Card>
  )
}

/* Compact KPI for map overlays / floating panels: label + tabular value,
   no card chrome of its own. */
export function KpiStat({ label, value, sub, className }) {
  return (
    <div className={className}>
      <p className="mob-section-label">{label}</p>
      <p className="mob-data mt-0.5 truncate text-lg font-bold leading-tight tracking-tight" title={String(value)}>{value}</p>
      {sub && <p className="mt-0.5 truncate text-[11px] text-muted-foreground">{sub}</p>}
    </div>
  )
}

/* Density bar: compact horizontal meter for cluster size / demand intensity.
   colorClass sets the fill (e.g. bg-violet-500, bg-primary). */
export function DensityBar({ value, max, colorClass = 'bg-primary', className, label }) {
  const pct = max > 0 ? Math.max(4, Math.min(100, (value / max) * 100)) : 0
  return (
    <div className={cn('min-w-0', className)} role="img" aria-label={label || `${value} of ${max}`}>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div className={cn('h-full rounded-full transition-[width]', colorClass)} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

/* Map legend: floating-friendly key for marker / cluster / heat colors. */
export function MapLegend({ items, className }) {
  return (
    <div className={cn('flex flex-wrap items-center gap-x-3 gap-y-1.5', className)} aria-label="Map legend">
      {items.map((item) => (
        <span key={item.label} className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
          <span
            className="h-2.5 w-2.5 shrink-0 rounded-full border border-white/60 shadow-sm"
            style={{ background: item.color }}
            aria-hidden="true"
          />
          {item.label}
        </span>
      ))}
    </div>
  )
}

export function DashboardEmptyState({ icon: Icon = CircleDot, title, hint, action }) {
  return (
    <Empty className="border border-dashed bg-card py-10">
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <Icon className="h-4 w-4" />
        </EmptyMedia>
        <EmptyTitle>{title}</EmptyTitle>
        {hint && <EmptyDescription>{hint}</EmptyDescription>}
      </EmptyHeader>
      {action}
    </Empty>
  )
}

export function LoadingRows({ count = 3, height = 'h-[68px]' }) {
  return (
    <div className="space-y-2" role="status" aria-label="Loading">
      {Array.from({ length: count }).map((_, i) => (
        <Skeleton key={i} className={cn('w-full', height)} />
      ))}
    </div>
  )
}

export function FieldLabel({ children }) {
  return <p className="mb-1.5 text-[11px] font-bold uppercase tracking-wider text-muted-foreground">{children}</p>
}

export { Card, CardContent, CardDescription, CardHeader, CardTitle }

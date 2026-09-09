/* eslint-disable react-refresh/only-export-components */
import { ArrowLeft, CircleDot } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'

// Shared status styles for all dashboards.
export const STATUS_STYLES = {
  pending: 'border-border bg-muted text-foreground',
  clustered: 'border-border bg-muted text-foreground',
  clustered_status: 'border-border bg-muted text-foreground',
  assigned: 'border-foreground/30 bg-foreground text-background',
  arriving: 'border-foreground/30 bg-foreground text-background',
  in_progress: 'border-foreground/30 bg-foreground text-background',
  completed: 'border-green-600/30 bg-green-600/10 text-green-700 dark:text-green-400',
  solved: 'border-green-600/30 bg-green-600/10 text-green-700 dark:text-green-400',
  cancelled: 'border-destructive/30 bg-destructive/10 text-destructive',
  idle: 'border-border bg-muted text-muted-foreground',
  active: 'border-green-600/30 bg-green-600/10 text-green-700 dark:text-green-400',
  en_route: 'border-foreground/30 bg-foreground text-background',
  offline: 'border-destructive/30 bg-destructive/10 text-destructive',
  no_pending_requests: 'border-border bg-muted text-muted-foreground',
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

/* Compact KPI for map overlays. */
export function KpiStat({ label, value, sub, className }) {
  return (
    <div className={className}>
      <p className="mob-section-label">{label}</p>
      <p className="mob-data mt-0.5 truncate text-lg font-bold leading-tight tracking-tight" title={String(value)}>{value}</p>
      {sub && <p className="mt-0.5 truncate text-[11px] text-muted-foreground">{sub}</p>}
    </div>
  )
}

/* Compact meter for cluster size/demand. */
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

/* Key for marker/cluster/heat colors. */
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

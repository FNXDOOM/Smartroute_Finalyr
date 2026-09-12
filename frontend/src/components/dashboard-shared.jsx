/* eslint-disable react-refresh/only-export-components */
import { ArrowLeft, CircleDot } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'

// Shared status styles — strict neutral + sparing semantic.
// Active / in-motion = solid black. Done = Uber blue. Failed = red. Waiting = neutral gray.
export const STATUS_STYLES = {
  pending: 'border-[#E2E2E2] bg-[#F6F6F6] text-[#333333] dark:border-[#333333] dark:bg-[#2A2A2A] dark:text-[#E2E2E2]',
  clustered: 'border-[#E2E2E2] bg-[#F6F6F6] text-[#333333] dark:border-[#333333] dark:bg-[#2A2A2A] dark:text-[#E2E2E2]',
  clustered_status: 'border-[#E2E2E2] bg-[#F6F6F6] text-[#333333] dark:border-[#333333] dark:bg-[#2A2A2A] dark:text-[#E2E2E2]',
  assigned: 'border-transparent bg-black text-white dark:border-transparent dark:bg-white dark:text-black',
  arriving: 'border-transparent bg-black text-white dark:border-transparent dark:bg-white dark:text-black',
  in_progress: 'border-transparent bg-black text-white dark:border-transparent dark:bg-white dark:text-black',
  completed: 'border-[#276EF1]/25 bg-[#276EF1]/10 text-[#276EF1]',
  solved: 'border-[#276EF1]/25 bg-[#276EF1]/10 text-[#276EF1]',
  cancelled: 'border-[#D93025]/25 bg-[#D93025]/10 text-[#D93025]',
  idle: 'border-[#E2E2E2] bg-transparent text-[#6B6B6B] dark:border-[#333333] dark:text-[#AFAFAF]',
  active: 'border-[#276EF1]/25 bg-[#276EF1]/10 text-[#276EF1]',
  en_route: 'border-transparent bg-black text-white dark:border-transparent dark:bg-white dark:text-black',
  offline: 'border-[#D93025]/25 bg-[#D93025]/10 text-[#D93025]',
  no_pending_requests: 'border-[#E2E2E2] bg-transparent text-[#6B6B6B] dark:border-[#333333] dark:text-[#AFAFAF]',
}

export function StatusBadge({ status, className }) {
  const key = status || 'pending'
  return (
    <Badge
      variant="outline"
      className={cn('shrink-0 text-[10px] font-semibold uppercase tracking-[0.06em]', STATUS_STYLES[key] || STATUS_STYLES.pending, className)}
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
        {description && <p className="mt-1 truncate text-[14px] text-[#6B6B6B] dark:text-[#AFAFAF]">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

export function StatCard({ icon: Icon, label, value, sub }) {
  return (
    <Card className="shadow-none transition-[border-color,box-shadow] duration-200 hover:border-[#D6D6D6] hover:shadow-[0_2px_8px_rgba(0,0,0,0.08)]">
      <CardContent className="p-5">
        <div className="flex items-start justify-between gap-2">
          <p className="mob-section-label">{label}</p>
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-black text-white dark:bg-white dark:text-black">
            <Icon className="h-4 w-4" />
          </span>
        </div>
        <p className="mob-data mt-3 truncate text-[28px] font-bold leading-none tracking-[-0.02em]" title={String(value)}>{value}</p>
        {sub && <p className="mt-1.5 truncate text-[13px] text-[#6B6B6B] dark:text-[#AFAFAF]">{sub}</p>}
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
      {sub && <p className="mt-0.5 truncate text-[11px] text-[#6B6B6B] dark:text-[#AFAFAF]">{sub}</p>}
    </div>
  )
}

/* Compact meter for cluster size/demand — neutral black fill. */
export function DensityBar({ value, max, colorClass = 'bg-black dark:bg-white', className, label }) {
  const pct = max > 0 ? Math.max(4, Math.min(100, (value / max) * 100)) : 0
  return (
    <div className={cn('min-w-0', className)} role="img" aria-label={label || `${value} of ${max}`}>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-[#EEEEEE] dark:bg-[#2A2A2A]">
        <div className={cn('h-full rounded-full transition-[width] duration-200', colorClass)} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

/* Key for marker/cluster/heat colors. */
export function MapLegend({ items, className }) {
  return (
    <div className={cn('flex flex-wrap items-center gap-x-3 gap-y-1.5', className)} aria-label="Map legend">
      {items.map((item) => (
        <span key={item.label} className="flex items-center gap-1.5 text-[11px] font-medium text-[#545454] dark:text-[#AFAFAF]">
          <span
            className="h-2.5 w-2.5 shrink-0 rounded-full border border-white shadow-sm"
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
    <Empty className="border border-dashed border-[#E2E2E2] bg-white py-12 dark:border-[#333333] dark:bg-[#1F1F1F]">
      <EmptyHeader>
        <EmptyMedia variant="icon" className="bg-[#F6F6F6] text-black dark:bg-[#2A2A2A] dark:text-white">
          <Icon className="h-4 w-4" />
        </EmptyMedia>
        <EmptyTitle className="text-[18px] font-semibold tracking-tight">{title}</EmptyTitle>
        {hint && <EmptyDescription className="max-w-[320px]">{hint}</EmptyDescription>}
      </EmptyHeader>
      {action}
    </Empty>
  )
}

export function LoadingRows({ count = 3, height = 'h-[68px]' }) {
  return (
    <div className="space-y-2" role="status" aria-label="Loading">
      {Array.from({ length: count }).map((_, i) => (
        <Skeleton key={i} className={cn('w-full rounded-xl bg-[#EEEEEE] dark:bg-[#2A2A2A]', height)} />
      ))}
    </div>
  )
}

export function FieldLabel({ children }) {
  return <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.06em] text-[#6B6B6B] dark:text-[#AFAFAF]">{children}</p>
}

export { Card, CardContent, CardDescription, CardHeader, CardTitle }

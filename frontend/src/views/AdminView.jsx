import { useState, useEffect, useCallback, useMemo } from 'react'
import {
  Activity, ArrowLeft, ArrowRight, BarChart3, Ban, CarFront, CheckCircle2, CheckCheck,
  ChevronRight, CircleDot, ClipboardList, Clock, FlaskConical, Flame, Gauge, Info,
  Loader2, Navigation, PauseCircle, Play, Plus,
  RefreshCw, Route as RouteIcon, Search, Settings, Sparkles, Truck,
  XCircle, Zap,
} from 'lucide-react'
import {
  ridesApi, vehiclesApi, clusterApi, routeApi,
  analyticsApi, jobsApi, predictApi, authApi,
} from '../services/api.js'
import AppMap from '../components/AppMap'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Separator } from '@/components/ui/separator'
import { Slider } from '@/components/ui/slider'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { KpiStat, DensityBar, MapLegend } from '@/components/dashboard-shared'

// ─── Shared bits ────────────────────────────────────────────────────────────
// One status style map for the whole admin area (rides, vehicles, jobs).
const STATUS_STYLES = {
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

function StatusBadge({ status }) {
  const key = status || 'pending'
  return (
    <Badge variant="outline" className={cn('shrink-0 uppercase tracking-wide', STATUS_STYLES[key] || STATUS_STYLES.pending)}>
      {String(key).replace(/_/g, ' ')}
    </Badge>
  )
}

function StatCard({ icon: Icon, label, value, sub }) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-2">
          <p className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">{label}</p>
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10">
            <Icon className="h-4 w-4 text-primary" />
          </span>
        </div>
        <p className="mt-2 truncate font-display text-2xl font-extrabold tracking-tight" title={String(value)}>{value}</p>
        {sub && <p className="mt-0.5 truncate text-xs text-muted-foreground">{sub}</p>}
      </CardContent>
    </Card>
  )
}

function PageHeader({ title, description, onBack, backLabel = 'Overview', actions }) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      {onBack && (
        <Button variant="ghost" size="sm" onClick={onBack} className="gap-1.5">
          <ArrowLeft className="h-4 w-4" /> {backLabel}
        </Button>
      )}
      <div className="min-w-0 flex-1">
        <h1 className="font-display text-xl font-extrabold tracking-tight md:text-2xl">{title}</h1>
        {description && <p className="mt-0.5 text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

function EmptyState({ icon: Icon = CircleDot, title, hint }) {
  return (
    <div className="flex flex-col items-center gap-1.5 rounded-lg border border-dashed py-10 text-center">
      <Icon className="h-6 w-6 text-muted-foreground" />
      <p className="text-sm font-semibold">{title}</p>
      {hint && <p className="max-w-[300px] text-xs text-muted-foreground">{hint}</p>}
    </div>
  )
}

function LoadingRows({ count = 3, height = 'h-[68px]' }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className={cn('animate-pulse rounded-lg bg-muted/60', height)} />
      ))}
    </div>
  )
}

function Field({ label, children }) {
  return (
    <div className="space-y-1.5">
      <Label className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">{label}</Label>
      {children}
    </div>
  )
}

// Deferred fetch keeps the lint rule happy (no setState synchronously in an effect).
function useDeferredLoad(load) {
  useEffect(() => {
    const timer = setTimeout(() => { void load() }, 0)
    return () => clearTimeout(timer)
  }, [load])
}

// ─── Root admin router (view keys unchanged — the sidebar depends on them) ───
export default function AdminView({ user, view, setView, toast }) {
  const ctx = { setView, toast }
  if (view === 'admin-rides')     return <RidesPanel          {...ctx} />
  if (view === 'admin-vehicles')  return <VehiclesPanel        {...ctx} />
  if (view === 'admin-cluster')   return <ClusterPanel         {...ctx} />
  if (view === 'admin-routes')    return <RoutesPanel          {...ctx} />
  if (view === 'admin-analytics') return <AnalyticsPanel       {...ctx} />
  if (view === 'admin-jobs')      return <JobsPanel            {...ctx} />
  if (view === 'admin-heatmap')   return <HeatmapPanel         {...ctx} />
  if (view === 'admin-drivers')   return <PendingDriversPanel  {...ctx} />
  return <OverviewPanel user={user} {...ctx} />
}

// ─── Overview — the calm starting point, not a copy of every other page ─────
const QUICK_LINKS = [
  { v: 'admin-rides', Icon: ClipboardList, label: 'Rides', desc: 'Track & move every booking' },
  { v: 'admin-vehicles', Icon: Truck, label: 'Fleet', desc: 'Vehicles & capacity' },
  { v: 'admin-drivers', Icon: CarFront, label: 'Drivers', desc: 'Approve new drivers' },
  { v: 'admin-cluster', Icon: FlaskConical, label: 'Grouping', desc: 'Pool nearby requests' },
  { v: 'admin-routes', Icon: RouteIcon, label: 'Routes', desc: 'Multi-stop route plans' },
  { v: 'admin-analytics', Icon: BarChart3, label: 'Analytics', desc: 'Demand & performance' },
  { v: 'admin-jobs', Icon: Settings, label: 'Jobs', desc: 'Background automation' },
  { v: 'admin-heatmap', Icon: Flame, label: 'Heatmap', desc: 'Where demand builds up' },
]

function OverviewPanel({ user, setView, toast }) {
  const [data, setData] = useState(null)
  const [pendingCount, setPendingCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [dispatching, setDispatching] = useState(false)

  const load = useCallback(async () => {
    try {
      const [d, pending] = await Promise.all([
        analyticsApi.overview(),
        authApi.getPendingDrivers().catch(() => []),
      ])
      setData(d)
      setPendingCount(Array.isArray(pending) ? pending.length : 0)
    } catch {
      toast('error', 'Failed to load overview')
    } finally {
      setLoading(false)
    }
  }, [toast])
  useDeferredLoad(load)

  const runAutoDispatch = async () => {
    setDispatching(true)
    try {
      const res = await jobsApi.runAutoDispatch()
      toast('success', 'Dispatch complete', `${res.clusters_formed || 0} groups formed · ${res.routes_optimized || 0} routes planned · ${res.assigned_rides || 0} rides assigned.`)
      load()
    } catch (e) {
      toast('error', 'Dispatch failed', e?.response?.data?.detail || '')
    } finally {
      setDispatching(false)
    }
  }

  const byStatus = data?.rides_by_status || {}
  const firstName = user?.name?.split(' ')[0] || 'Admin'

  return (
    <div className="mx-auto w-full max-w-6xl space-y-5 p-4 md:p-7">
      <PageHeader
        title={`Welcome, ${firstName}`}
        description={data?.generated_at ? `Live picture · updated ${new Date(data.generated_at).toLocaleTimeString()}` : 'Live picture of your transit network'}
        actions={
          <>
            <Button variant="secondary" size="sm" onClick={() => setView('presentation-demo')} className="gap-1.5">
              <Zap className="h-3.5 w-3.5" /> Presentation demo
            </Button>
            <Button size="sm" onClick={runAutoDispatch} disabled={dispatching} className="gap-1.5">
              {dispatching ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
              {dispatching ? 'Dispatching…' : 'Run full dispatch'}
            </Button>
          </>
        }
      />

      {pendingCount > 0 && (
        <Card className="border-amber-500/40 bg-amber-500/[0.06]">
          <CardContent className="flex flex-wrap items-center gap-3 p-4">
            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-amber-500/15">
              <CarFront className="h-4 w-4 text-amber-600 dark:text-amber-400" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-[13px] font-bold">{pendingCount} driver{pendingCount === 1 ? '' : 's'} waiting for approval</p>
              <p className="text-xs text-muted-foreground">They can't drive until you approve them.</p>
            </div>
            <Button size="sm" variant="outline" onClick={() => setView('admin-drivers')} className="gap-1.5">
              Review <ChevronRight className="h-3.5 w-3.5" />
            </Button>
          </CardContent>
        </Card>
      )}

      {loading ? (
        <LoadingRows count={4} height="h-[92px]" />
      ) : (
        <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
          <StatCard icon={ClipboardList} label="Total rides" value={data?.total_rides ?? 0} sub={`${data?.rides_by_status?.pending ?? 0} waiting`} />
          <StatCard icon={Truck} label="Fleet" value={`${data?.active_vehicles ?? 0}/${data?.total_vehicles ?? 0}`} sub="active vehicles" />
          <StatCard icon={RouteIcon} label="Route plans" value={data?.total_route_plans ?? 0} sub={`${data?.route_utilization_percent ?? 0}% seat use`} />
          <StatCard icon={FlaskConical} label="Groups formed" value={data?.total_cluster_runs ?? 0} sub="pooling runs" />
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
        <Card className="shadow-sm">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-semibold">Rides by stage</CardTitle>
            <CardDescription>Where every booking sits right now · bar = share of total</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2.5">
            {Object.keys(byStatus).length === 0 && <p className="text-sm text-muted-foreground">No rides yet.</p>}
            {(() => {
              const max = Math.max(1, ...Object.values(byStatus))
              const total = Object.values(byStatus).reduce((n, c) => n + c, 0)
              return Object.entries(byStatus).map(([st, cnt]) => (
                <div key={st}>
                  <div className="mb-1 flex items-center justify-between gap-2">
                    <StatusBadge status={st} />
                    <p className="mob-data text-sm font-semibold">{cnt} <span className="font-normal text-muted-foreground">· {total ? Math.round((cnt / total) * 100) : 0}%</span></p>
                  </div>
                  <DensityBar value={cnt} max={max} colorClass="bg-primary" label={`${st}: ${cnt} rides`} />
                </div>
              ))
            })()}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm">Manage</CardTitle>
            <CardDescription>Jump to any admin tool</CardDescription>
          </CardHeader>
          <CardContent className="grid grid-cols-1 gap-1.5 sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2">
            {QUICK_LINKS.map(({ v, Icon, label, desc }) => (
              <button
                key={v}
                onClick={() => setView(v)}
                className="group flex items-center gap-2.5 rounded-lg border p-2.5 text-left transition-colors hover:border-primary/40 hover:bg-primary/[0.04] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10">
                  <Icon className="h-4 w-4 text-primary" />
                </span>
                <span className="min-w-0">
                  <span className="block text-[13px] font-bold leading-tight">{label}</span>
                  <span className="block truncate text-[11px] text-muted-foreground">{desc}</span>
                </span>
              </button>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

// ─── Rides — find any booking, move it forward ───────────────────────────────
const RIDE_FILTERS = ['', 'pending', 'clustered', 'assigned', 'in_progress', 'completed', 'cancelled']
const NEXT_STATUS = { pending: 'clustered', clustered: 'assigned', assigned: 'in_progress', in_progress: 'completed' }
const NEXT_LABEL = { pending: 'Group', clustered: 'Assign', assigned: 'Start trip', in_progress: 'Complete' }

function RidesPanel({ setView, toast }) {
  const [rides, setRides] = useState([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('')
  const [query, setQuery] = useState('')

  const load = useCallback(async () => {
    try {
      const r = await ridesApi.getAll({ limit: 50 })
      setRides(Array.isArray(r) ? r : [])
    } catch (e) {
      toast('error', 'Failed to load rides', e?.response?.data?.detail || '')
    } finally {
      setLoading(false)
    }
  }, [toast])
  useDeferredLoad(load)

  const updateStatus = async (id, status) => {
    try {
      await ridesApi.updateStatus(id, status)
      setRides((p) => p.map((r) => (r.id === id ? { ...r, status } : r)))
      toast('success', `Ride #${id} → ${status.replace(/_/g, ' ')}`)
    } catch (e) {
      toast('error', 'Update failed', e?.response?.data?.detail || '')
    }
  }

  const q = query.trim().toLowerCase()
  const filtered = rides.filter((r) => {
    if (filter && r.status !== filter) return false
    if (!q) return true
    return String(r.id).includes(q)
      || (r.pickup_label || '').toLowerCase().includes(q)
      || (r.destination_label || '').toLowerCase().includes(q)
  })

  return (
    <div className="mx-auto w-full max-w-4xl space-y-4 p-4 md:p-7">
      <PageHeader
        title="Rides"
        description={`${filtered.length} of ${rides.length} bookings`}
        onBack={() => setView('admin-overview')}
        actions={
          <Button variant="outline" size="sm" onClick={load} className="gap-1.5">
            <RefreshCw className="h-3.5 w-3.5" /> Refresh
          </Button>
        }
      />

      <div className="flex flex-col gap-2.5">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search by ride #, pickup or destination…" className="pl-9" />
        </div>
        <div className="flex flex-wrap gap-1.5">
          {RIDE_FILTERS.map((st) => (
            <Button
              key={st || 'all'}
              size="sm"
              variant={filter === st ? 'secondary' : 'ghost'}
              onClick={() => setFilter(st)}
              className="h-7 text-xs capitalize"
            >
              {st ? st.replace(/_/g, ' ') : 'All'}
            </Button>
          ))}
        </div>
      </div>

      {loading ? (
        <LoadingRows />
      ) : filtered.length === 0 ? (
        <EmptyState title="No rides match" hint="Try a different search or stage filter." />
      ) : (
        <div className="space-y-2">
          {filtered.map((r) => (
            <Card key={r.id}>
              <CardContent className="space-y-2 p-3.5">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs text-muted-foreground">#{r.id}</span>
                    <StatusBadge status={r.status} />
                  </div>
                  <span className="text-[11px] text-muted-foreground">
                    {r.request_time ? new Date(r.request_time).toLocaleString() : ''}
                  </span>
                </div>
                <p className="truncate text-[13px] font-medium">
                  {r.pickup_label || 'Pickup'} <ArrowRight className="mx-1 inline h-3.5 w-3.5 text-muted-foreground" />
                  {r.destination_label || 'Destination'}
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {NEXT_STATUS[r.status] && (
                    <Button size="sm" variant="secondary" className="h-7 text-xs" onClick={() => updateStatus(r.id, NEXT_STATUS[r.status])}>
                      {NEXT_LABEL[r.status]} <ChevronRight className="h-3.5 w-3.5" />
                    </Button>
                  )}
                  {!['completed', 'cancelled'].includes(r.status) && (
                    <Button size="sm" variant="ghost" className="h-7 text-xs text-destructive hover:text-destructive" onClick={() => updateStatus(r.id, 'cancelled')}>
                      <Ban className="h-3.5 w-3.5" /> Cancel
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Fleet — vehicles, plus a nudge when drivers wait for approval ──────────
function VehiclesPanel({ setView, toast }) {
  const [vehicles, setVehicles] = useState([])
  const [pendingCount, setPendingCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState({ license_plate: '', capacity: '4', lat: '12.9784', lng: '77.6408' })

  const load = useCallback(async () => {
    try {
      const [v, pending] = await Promise.all([
        vehiclesApi.list(),
        authApi.getPendingDrivers().catch(() => []),
      ])
      setVehicles(Array.isArray(v) ? v : [])
      setPendingCount(Array.isArray(pending) ? pending.length : 0)
    } catch (e) {
      toast('error', 'Failed to load fleet', e?.response?.data?.detail || '')
    } finally {
      setLoading(false)
    }
  }, [toast])
  useDeferredLoad(load)

  const create = async () => {
    if (!form.license_plate.trim()) { toast('warning', 'Enter a license plate'); return }
    setCreating(true)
    try {
      await vehiclesApi.create({ license_plate: form.license_plate.trim(), capacity: Number(form.capacity), lat: Number(form.lat), lng: Number(form.lng) })
      toast('success', 'Vehicle added to the fleet')
      setForm({ license_plate: '', capacity: '4', lat: '12.9784', lng: '77.6408' })
      load()
    } catch (e) {
      toast('error', 'Could not add vehicle', e?.response?.data?.detail || '')
    } finally {
      setCreating(false)
    }
  }

  const updateStatus = async (id, status) => {
    try {
      await vehiclesApi.update(id, { status })
      setVehicles((p) => p.map((v) => (v.id === id ? { ...v, status } : v)))
      toast('success', `Vehicle #${id} is now ${status}`)
    } catch (e) {
      toast('error', 'Update failed', e?.response?.data?.detail || '')
    }
  }

  return (
    <div className="mx-auto w-full max-w-5xl space-y-4 p-4 md:p-7">
      <PageHeader
        title="Fleet"
        description={`${vehicles.length} vehicle${vehicles.length === 1 ? '' : 's'} · approve drivers on the Drivers page`}
        onBack={() => setView('admin-overview')}
        actions={
          <Button variant="outline" size="sm" onClick={load} className="gap-1.5">
            <RefreshCw className="h-3.5 w-3.5" /> Refresh
          </Button>
        }
      />

      {pendingCount > 0 && (
        <Card className="border-amber-500/40 bg-amber-500/[0.06]">
          <CardContent className="flex flex-wrap items-center gap-2.5 p-3.5">
            <p className="min-w-0 flex-1 text-[13px]"><strong>{pendingCount} driver{pendingCount === 1 ? '' : 's'}</strong> <span className="text-muted-foreground">waiting for approval</span></p>
            <Button size="sm" variant="outline" onClick={() => setView('admin-drivers')} className="gap-1.5">
              Review <ChevronRight className="h-3.5 w-3.5" />
            </Button>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-4 lg:grid-cols-[300px_minmax(0,1fr)]">
        <Card className="h-fit">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm">Add vehicle</CardTitle>
            <CardDescription>Appears in the fleet immediately</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Field label="License plate">
              <Input value={form.license_plate} onChange={(e) => setForm((p) => ({ ...p, license_plate: e.target.value }))} placeholder="KA01AB1234" className="font-mono" />
            </Field>
            <div className="grid grid-cols-3 gap-2">
              <Field label="Seats">
                <Input value={form.capacity} onChange={(e) => setForm((p) => ({ ...p, capacity: e.target.value }))} inputMode="numeric" />
              </Field>
              <Field label="Lat">
                <Input value={form.lat} onChange={(e) => setForm((p) => ({ ...p, lat: e.target.value }))} inputMode="decimal" />
              </Field>
              <Field label="Lng">
                <Input value={form.lng} onChange={(e) => setForm((p) => ({ ...p, lng: e.target.value }))} inputMode="decimal" />
              </Field>
            </div>
            <Button className="w-full gap-1.5" onClick={create} disabled={creating}>
              {creating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
              {creating ? 'Adding…' : 'Add vehicle'}
            </Button>
          </CardContent>
        </Card>

        <div className="space-y-2">
          {loading ? (
            <LoadingRows />
          ) : vehicles.length === 0 ? (
            <EmptyState icon={Truck} title="No vehicles yet" hint="Add the first one with the form." />
          ) : (
            vehicles.map((v) => (
              <Card key={v.id}>
                <CardContent className="space-y-2 p-3.5">
                  <div className="flex items-center justify-between gap-2">
                    <p className="font-mono text-[13px] font-bold">{v.license_plate} <span className="font-sans font-normal text-muted-foreground">· {v.capacity} seats</span></p>
                    <StatusBadge status={v.status} />
                  </div>
                  {v.lat != null && <p className="font-mono text-[11px] text-muted-foreground">GPS {Number(v.lat).toFixed(4)}, {Number(v.lng).toFixed(4)}</p>}
                  <div className="flex flex-wrap gap-1.5">
                    {v.status !== 'idle' && <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => updateStatus(v.id, 'idle')}>Set idle</Button>}
                    {v.status !== 'active' && <Button size="sm" variant="secondary" className="h-7 text-xs" onClick={() => updateStatus(v.id, 'active')}><Play className="h-3.5 w-3.5" /> Set active</Button>}
                    {v.status !== 'offline' && <Button size="sm" variant="ghost" className="h-7 text-xs text-destructive hover:text-destructive" onClick={() => updateStatus(v.id, 'offline')}>Take offline</Button>}
                  </div>
                </CardContent>
              </Card>
            ))
          )}
        </div>
      </div>
    </div>
  )
}

// ─── Grouping — pool nearby ride requests together ──────────────────────────
function ClusterPanel({ setView, toast }) {
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [selectedId, setSelectedId] = useState(null)
  const [minSize, setMinSize] = useState('2')
  const [resolution, setResolution] = useState('9')

  const load = useCallback(async () => {
    try {
      const h = await clusterApi.history()
      setHistory(h?.runs || [])
    } catch (e) {
      toast('error', 'Failed to load grouping history', e?.response?.data?.detail || '')
    } finally {
      setLoading(false)
    }
  }, [toast])
  useDeferredLoad(load)

  const runCluster = async () => {
    setRunning(true)
    try {
      const res = await clusterApi.run({ resolution: Number(resolution), min_cluster_size: Number(minSize) })
      toast('success', 'Grouping done', `${res.clusters_formed} groups from ${res.total_processed_requests} waiting rides.`)
      load()
    } catch (e) {
      toast('error', 'Grouping failed', e?.response?.data?.detail || '')
    } finally {
      setRunning(false)
    }
  }

  const selected = history.find((r) => r.id === selectedId) || null
  const maxGroups = Math.max(1, ...history.map((r) => r.clusters_formed || 0))
  const maxRiders = Math.max(1, ...history.flatMap((r) => (r.cluster_summary || []).map((cs) => cs.passenger_count || 0)))
  const totals = useMemo(() => ({
    runs: history.length,
    groups: history.reduce((n, r) => n + (r.clusters_formed || 0), 0),
    riders: history.reduce((n, r) => n + (r.cluster_summary || []).reduce((m, cs) => m + (cs.passenger_count || 0), 0), 0),
    noise: history.reduce((n, r) => n + (r.noise_requests_count || 0), 0),
  }), [history])
  const selectedStops = useMemo(() => (
    (selected?.cluster_summary || [])
      .filter((cs) => cs.virtual_stop_lat != null && cs.virtual_stop_lng != null)
      .map((cs) => ({
        lat: cs.virtual_stop_lat,
        lng: cs.virtual_stop_lng,
        waypoint_type: 'waypoint',
        label: `Group #${cs.cluster_id} · ${cs.passenger_count || 0} riders`,
      }))
  ), [selected])

  return (
    <div className="mx-auto w-full max-w-6xl space-y-4 p-4 md:p-7">
      <PageHeader
        title="Pooling groups"
        description="Density-based grouping turns nearby requests into shared rides"
        onBack={() => setView('admin-overview')}
        actions={
          <Badge variant="secondary" className="mob-data gap-1.5">
            <FlaskConical className="h-3 w-3" /> HDBSCAN · res {resolution} · min {minSize}
          </Badge>
        }
      />

      {/* Aggregate picture: where groups stand across runs */}
      {!loading && history.length > 0 && (
        <div className="flex flex-wrap items-center gap-x-6 gap-y-3 rounded-xl border bg-card px-4 py-3 shadow-sm" aria-label="Grouping summary">
          <KpiStat label="Runs" value={totals.runs} />
          <Separator orientation="vertical" className="hidden h-8 sm:block" />
          <KpiStat label="Groups formed" value={totals.groups} sub="pooled stops" />
          <Separator orientation="vertical" className="hidden h-8 sm:block" />
          <KpiStat label="Riders pooled" value={totals.riders} sub="across all runs" />
          <Separator orientation="vertical" className="hidden h-8 sm:block" />
          <KpiStat label="Left out" value={totals.noise} sub="noise requests" />
          <MapLegend
            className="ml-auto"
            items={[
              { color: '#a78bfa', label: 'Pooled stop' },
              { color: '#f59e0b', label: 'Noise' },
            ]}
          />
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
        <Card className="h-fit">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm">Algorithm parameters</CardTitle>
            <CardDescription>Applied to waiting rides on the next run</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <div className="mb-1.5 flex items-center justify-between">
                <Label htmlFor="cluster-res">Map detail</Label>
                <Tooltip>
                  <TooltipTrigger render={<Badge variant="secondary" className="mob-data cursor-help text-[11px]">{resolution}</Badge>} />
                  <TooltipContent className="max-w-[220px]">H3 resolution 7–12. Higher detail = smaller hexagons = tighter groups.</TooltipContent>
                </Tooltip>
              </div>
              <Slider
                id="cluster-res"
                min={7}
                max={12}
                step={1}
                value={[Number(resolution) || 9]}
                onValueChange={([v]) => setResolution(String(v))}
                aria-label="H3 resolution, 7 to 12"
              />
              <div className="mob-data mt-1 flex justify-between text-[10px] text-muted-foreground" aria-hidden="true"><span>7 · coarse</span><span>12 · fine</span></div>
            </div>
            <div>
              <div className="mb-1.5 flex items-center justify-between">
                <Label htmlFor="cluster-min">Min group size</Label>
                <Tooltip>
                  <TooltipTrigger render={<Badge variant="secondary" className="mob-data cursor-help text-[11px]">{minSize}</Badge>} />
                  <TooltipContent className="max-w-[220px]">Minimum requests per group. Larger minimum = fewer, fuller groups.</TooltipContent>
                </Tooltip>
              </div>
              <Slider
                id="cluster-min"
                min={2}
                max={8}
                step={1}
                value={[Number(minSize) || 2]}
                onValueChange={([v]) => setMinSize(String(v))}
                aria-label="Minimum group size, 2 to 8"
              />
              <div className="mob-data mt-1 flex justify-between text-[10px] text-muted-foreground" aria-hidden="true"><span>2 riders</span><span>8 riders</span></div>
            </div>
            <Button className="w-full gap-1.5" onClick={runCluster} disabled={running}>
              {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <FlaskConical className="h-4 w-4" />}
              {running ? 'Grouping…' : 'Group waiting rides'}
            </Button>
            <p className="text-[11px] leading-relaxed text-muted-foreground">Needs waiting rides — or run the full dispatch from Overview.</p>
          </CardContent>
        </Card>

        <div className="min-w-0 space-y-2">
          <div className="flex items-center justify-between">
            <p className="text-sm font-semibold">Runs <span className="mob-data font-normal text-muted-foreground">· newest first</span></p>
            <Button variant="ghost" size="sm" onClick={load} className="h-7 gap-1.5 text-xs"><RefreshCw className="h-3.5 w-3.5" /> Refresh</Button>
          </div>
          {loading ? (
            <LoadingRows />
          ) : history.length === 0 ? (
            <EmptyState icon={FlaskConical} title="No grouping runs yet" hint="Tune the parameters and group waiting rides to see density results here." />
          ) : (
            history.map((run) => {
              const open = selected?.id === run.id
              return (
                <Card key={run.id} className={cn('cluster-row', open && 'border-primary/50')}>
                  <button onClick={() => setSelectedId(open ? null : run.id)} data-active={open} className="cluster-row w-full rounded-xl p-3.5 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" aria-expanded={open}>
                    <div className="mb-1 flex items-center justify-between gap-2">
                      <p className="mob-data text-[13px] font-semibold">Run #{run.id}</p>
                      <StatusBadge status={run.status} />
                    </div>
                    <div className="mb-1.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
                      <span className="mob-data"><strong className="text-foreground">{run.total_processed_requests}</strong> rides</span>
                      <span className="mob-data"><strong className="text-violet-600 dark:text-violet-400">{run.clusters_formed}</strong> groups</span>
                      <span className="mob-data"><strong className="text-amber-600 dark:text-amber-400">{run.noise_requests_count}</strong> left out</span>
                      {run.created_at ? <span>{new Date(run.created_at).toLocaleString()}</span> : null}
                    </div>
                    <DensityBar value={run.clusters_formed || 0} max={maxGroups} colorClass="bg-violet-500" label={`Run ${run.id}: ${run.clusters_formed} groups`} />
                    {open && (
                      <div className="mt-3 space-y-2 border-t pt-3" onClick={(e) => e.stopPropagation()}>
                        {selectedStops.length > 0 && (
                          <div>
                            <div className="mb-1.5 overflow-hidden rounded-lg border">
                              <AppMap
                                center={[selectedStops[0].lat, selectedStops[0].lng]}
                                zoom={13}
                                height={220}
                                waypoints={selectedStops}
                                style={{ borderRadius: 0 }}
                              />
                            </div>
                            <p className="mb-2 text-[11px] text-muted-foreground">{selectedStops.length} pooled {selectedStops.length === 1 ? 'stop' : 'stops'} · violet pins sized equally, bar = riders</p>
                          </div>
                        )}
                        {(run.cluster_summary || []).slice(0, 8).map((cs) => (
                          <div key={cs.cluster_id} className="flex items-center gap-2.5 rounded-lg bg-muted/50 px-2.5 py-2">
                            <span className="h-2.5 w-2.5 shrink-0 rounded-full bg-violet-500" aria-hidden="true" />
                            <div className="min-w-0 flex-1">
                              <div className="flex items-baseline justify-between gap-2">
                                <p className="text-[11px] font-semibold">Group #{cs.cluster_id}</p>
                                <p className="mob-data shrink-0 text-[11px] text-muted-foreground">{cs.passenger_count} riders</p>
                              </div>
                              <DensityBar value={cs.passenger_count || 0} max={maxRiders} colorClass="bg-violet-500" className="mt-1" />
                              <p className="mob-data mt-1 truncate text-[10px] text-muted-foreground">stop {cs.virtual_stop_lat?.toFixed(4)}, {cs.virtual_stop_lng?.toFixed(4)}</p>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </button>
                </Card>
              )
            })
          )}
        </div>
      </div>
    </div>
  )
}

// ─── Routes — turn groups into multi-stop plans ─────────────────────────────
function RoutesPanel({ setView, toast }) {
  const [routes, setRoutes] = useState([])
  const [vehicles, setVehicles] = useState([])
  const [clusters, setClusters] = useState([])
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [selectedId, setSelectedId] = useState(null)
  const [depotLat, setDepotLat] = useState('12.9784')
  const [depotLng, setDepotLng] = useState('77.6408')

  const load = useCallback(async () => {
    try {
      const [ro, ve, cl] = await Promise.all([routeApi.history(), vehiclesApi.idle(), clusterApi.history(5)])
      setRoutes(ro?.routes || [])
      setVehicles(Array.isArray(ve) ? ve : [])
      setClusters(cl?.runs || [])
    } catch (e) {
      toast('error', 'Failed to load routes', e?.response?.data?.detail || '')
    } finally {
      setLoading(false)
    }
  }, [toast])
  useDeferredLoad(load)

  const runOptimize = async () => {
    if (vehicles.length === 0) { toast('warning', 'No free vehicles', 'Free up a vehicle first.'); return }
    const latestCluster = clusters[0]
    if (!latestCluster?.cluster_summary?.length) { toast('warning', 'Group rides first', 'Route planning needs a grouping run.'); return }
    const stopIds = latestCluster.cluster_summary.map((c) => c.virtual_stop_id).filter(Boolean)
    if (!stopIds.length) { toast('warning', 'No stops found', 'The latest grouping has no stops.'); return }
    setRunning(true)
    try {
      const res = await routeApi.optimize({
        vehicle_ids: vehicles.slice(0, 3).map((v) => v.id),
        virtual_stop_ids: stopIds,
        depot_lat: Number(depotLat),
        depot_lng: Number(depotLng),
        source_cluster_run_id: latestCluster.id,
      })
      toast('success', 'Routes planned', `${res.routes?.length || 0} routes · ${res.unassigned_stops?.length || 0} stops left over.`)
      load()
    } catch (e) {
      toast('error', 'Planning failed', e?.response?.data?.detail || '')
    } finally {
      setRunning(false)
    }
  }

  const selected = routes.find((r) => (r.id ?? r.route_id) === selectedId) || null

  return (
    <div className="mx-auto w-full max-w-6xl space-y-4 p-4 md:p-7">
      <PageHeader
        title="Route plans"
        description="Multi-stop plans pairing pooled stops with free vehicles"
        onBack={() => setView('admin-overview')}
        actions={
          vehicles.length > 0 ? (
            <Badge variant="secondary" className="mob-data gap-1.5">
              <Truck className="h-3 w-3" /> {vehicles.length} free {vehicles.length === 1 ? 'vehicle' : 'vehicles'}
            </Badge>
          ) : undefined
        }
      />

      <div className="grid gap-4 lg:grid-cols-[300px_minmax(0,1fr)]">
        <Card className="h-fit">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm">Plan routes</CardTitle>
            <CardDescription>Uses the latest grouping + free vehicles</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-2 gap-2">
              <Field label="Depot lat">
                <Input value={depotLat} onChange={(e) => setDepotLat(e.target.value)} inputMode="decimal" />
              </Field>
              <Field label="Depot lng">
                <Input value={depotLng} onChange={(e) => setDepotLng(e.target.value)} inputMode="decimal" />
              </Field>
            </div>
            <div className="rounded-lg bg-muted/50 p-2.5 text-xs text-muted-foreground">
              <p className="mob-data">Free vehicles: <strong className="text-foreground">{vehicles.length}</strong></p>
              <p className="mob-data mt-1">Latest grouping: <strong className="text-foreground">{clusters[0] ? `#${clusters[0].id} (${clusters[0].clusters_formed} groups)` : 'none yet'}</strong></p>
            </div>
            <Button className="w-full gap-1.5" onClick={runOptimize} disabled={running}>
              {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Navigation className="h-4 w-4" />}
              {running ? 'Planning…' : 'Plan routes'}
            </Button>
          </CardContent>
        </Card>

        <div className="min-w-0 space-y-2">
          <div className="flex items-center justify-between">
            <p className="text-sm font-semibold">Plans <span className="mob-data font-normal text-muted-foreground">· tap to inspect on map</span></p>
            <Button variant="ghost" size="sm" onClick={load} className="h-7 gap-1.5 text-xs"><RefreshCw className="h-3.5 w-3.5" /> Refresh</Button>
          </div>
          {loading ? (
            <LoadingRows />
          ) : routes.length === 0 ? (
            <EmptyState icon={RouteIcon} title="No routes yet" hint="Group rides first, then plan routes." />
          ) : (
            routes.map((r) => {
              const id = r.id ?? r.route_id
              const open = (selected?.id ?? selected?.route_id) === id
              return (
                <Card key={id} className={cn('cluster-row', open && 'border-primary/50')}>
                  <button onClick={() => setSelectedId(open ? null : id)} data-active={open} className="cluster-row w-full rounded-xl p-3.5 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" aria-expanded={open}>
                    <div className="mb-1 flex items-center justify-between gap-2">
                      <p className="mob-data truncate font-mono text-xs font-semibold">{String(r.route_id || `route-${id}`).slice(0, 28)}</p>
                      <StatusBadge status={r.status} />
                    </div>
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
                      <span className="mob-data">Vehicle <strong className="text-foreground">#{r.vehicle_id ?? '—'}</strong></span>
                      <span className="mob-data"><strong className="text-foreground">{r.total_distance_meters ? `${(r.total_distance_meters / 1000).toFixed(2)} km` : '—'}</strong></span>
                      <span className="mob-data"><strong className="text-foreground">{r.waypoints?.length || 0}</strong> stops</span>
                    </div>
                  </button>
                  {open && (
                    <CardContent className="space-y-2 pt-0" onClick={(e) => e.stopPropagation()}>
                      {r.waypoints?.length > 0 && (
                        <>
                          <div className="overflow-hidden rounded-lg border">
                            <AppMap center={[r.waypoints[0].lat, r.waypoints[0].lng]} zoom={13} height={260} waypoints={r.waypoints} style={{ borderRadius: 0 }} />
                          </div>
                          <MapLegend
                            items={[
                              { color: '#3b82f6', label: 'Depot' },
                              { color: '#a78bfa', label: 'Stop' },
                              { color: '#f43f5e', label: 'Destination' },
                            ]}
                          />
                        </>
                      )}
                      <ol className="divide-y rounded-lg border">
                        {(r.waypoints || []).map((wp, i) => (
                          <li key={i} className="flex items-center gap-2.5 px-3 py-2 text-xs">
                            <span className="mob-data flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[10px] font-bold text-primary">{i + 1}</span>
                            <span className="shrink-0 text-[10px] font-bold uppercase tracking-wide text-primary">{wp.waypoint_type}</span>
                            <span className="mob-data truncate text-muted-foreground">{wp.lat?.toFixed(4)}, {wp.lng?.toFixed(4)}</span>
                            {wp.passenger_ids?.length > 0 && <Badge variant="secondary" className="mob-data ml-auto shrink-0 text-[10px]">{wp.passenger_ids.length} riders</Badge>}
                          </li>
                        ))}
                      </ol>
                    </CardContent>
                  )}
                </Card>
              )
            })
          )}
        </div>
      </div>
    </div>
  )
}

// ─── Analytics — demand trends + key numbers ────────────────────────────────
function AnalyticsPanel({ setView, toast }) {
  const [overview, setOverview] = useState(null)
  const [daily, setDaily] = useState([])
  const [days, setDays] = useState(14)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [ov, da] = await Promise.all([analyticsApi.overview(), analyticsApi.daily(days)])
      setOverview(ov)
      setDaily(da?.points || [])
    } catch (e) {
      toast('error', 'Failed to load analytics', e?.response?.data?.detail || '')
    } finally {
      setLoading(false)
    }
  }, [days, toast])
  useDeferredLoad(load)

  const maxRides = Math.max(1, ...daily.map((d) => d.ride_requests))

  return (
    <div className="mx-auto w-full max-w-5xl space-y-4 p-4 md:p-7">
      <PageHeader title="Analytics" description="Demand trends and how well seats are filled" onBack={() => setView('admin-overview')} />
      {loading || !overview ? (
        <LoadingRows count={4} height="h-[92px]" />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
            <StatCard icon={ClipboardList} label="Total rides" value={overview.total_rides} sub="all time" />
            <StatCard icon={CheckCircle2} label="Completed" value={overview.rides_by_status?.completed || 0} sub="finished trips" />
            <StatCard icon={Clock} label="Waiting" value={overview.rides_by_status?.pending || 0} sub="need grouping" />
            <StatCard icon={Gauge} label="Seat use" value={`${overview.route_utilization_percent}%`} sub="of planned seats filled" />
          </div>

          <Card>
            <CardHeader className="pb-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <CardTitle className="text-sm font-semibold">Ride requests per day</CardTitle>
                  <CardDescription>Taller bar = busier day · hover for exact counts</CardDescription>
                </div>
                <ToggleGroup type="single" size="sm" value={String(days)} onValueChange={(v) => { if (v) setDays(Number(v)) }} aria-label="Date range">
                  {[7, 14, 30].map((d) => (
                    <ToggleGroupItem key={d} value={String(d)} aria-label={`Last ${d} days`} className="mob-data px-2.5 text-xs">
                      {d}d
                    </ToggleGroupItem>
                  ))}
                </ToggleGroup>
              </div>
            </CardHeader>
            <CardContent>
              {daily.length === 0 ? (
                <p className="text-sm text-muted-foreground">No daily data yet.</p>
              ) : (
                <>
                  <div className="mb-1 flex justify-between text-[10px] text-muted-foreground" aria-hidden="true">
                    <span className="mob-data">{maxRides} peak</span>
                    <span>Last {days} days →</span>
                  </div>
                  <div className="flex h-[120px] items-end gap-1 px-1" role="img" aria-label={`Ride requests per day, peak ${maxRides}`}>
                    {daily.map((d) => {
                      const h = Math.max(4, (d.ride_requests / maxRides) * 110)
                      return (
                        <div key={d.day} className="group flex min-w-0 flex-1 flex-col items-center gap-1" title={`${d.ride_requests} rides · ${d.clustered_rides} grouped · ${d.completed_rides} done — ${d.day}`}>
                          <div className="w-full rounded-t bg-primary/80 transition-colors group-hover:bg-primary" style={{ height: h }} />
                        </div>
                      )
                    })}
                  </div>
                  <div className="mob-data mt-1 flex justify-between text-[10px] text-muted-foreground" aria-hidden="true">
                    <span>{daily[0] ? new Date(daily[0].day).toLocaleDateString('en', { month: 'short', day: 'numeric' }) : ''}</span>
                    <span>{daily[daily.length - 1] ? new Date(daily[daily.length - 1].day).toLocaleDateString('en', { month: 'short', day: 'numeric' }) : ''}</span>
                  </div>
                </>
              )}
            </CardContent>
          </Card>

          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {[
              ['Avg trip', overview.avg_trip_distance_meters ? `${(overview.avg_trip_distance_meters / 1000).toFixed(2)} km` : '—'],
              ['Avg route', overview.avg_route_distance_meters ? `${(overview.avg_route_distance_meters / 1000).toFixed(2)} km` : '—'],
              ['Riders / stop', String(overview.avg_passengers_per_virtual_stop || 0)],
              ['Boarding stops', String(overview.total_virtual_stops || 0)],
            ].map(([label, val]) => (
              <Card key={label} className="shadow-sm">
                <CardContent className="p-3.5">
                  <p className="mob-section-label">{label}</p>
                  <p className="mob-data mt-1 text-lg font-bold">{val}</p>
                </CardContent>
              </Card>
            ))}
          </div>

          <Card className="shadow-sm">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-semibold">Daily breakdown</CardTitle>
            </CardHeader>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow className="bg-muted/50">
                    {['Date', 'Requests', 'Grouped', 'Done', 'Cancelled', 'Routes'].map((h) => (
                      <TableHead key={h} className="px-4">{h}</TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {daily.slice().reverse().map((d) => (
                    <TableRow key={d.day}>
                      <TableCell className="px-4">{new Date(d.day).toLocaleDateString('en', { month: 'short', day: 'numeric' })}</TableCell>
                      <TableCell className="mob-data px-4 font-semibold">{d.ride_requests}</TableCell>
                      <TableCell className="mob-data px-4 text-violet-600 dark:text-violet-400">{d.clustered_rides}</TableCell>
                      <TableCell className="mob-data px-4 text-emerald-600 dark:text-emerald-400">{d.completed_rides}</TableCell>
                      <TableCell className="mob-data px-4 text-destructive">{d.cancelled_rides}</TableCell>
                      <TableCell className="mob-data px-4">{d.route_plans}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </Card>
        </>
      )}
    </div>
  )
}

// ─── Jobs — automation that runs on a schedule, plus manual triggers ───────
const JOB_BUTTONS = [
  { key: 'auto_dispatch', label: 'Full dispatch', hint: 'Group → plan → assign', Icon: Zap },
  { key: 'clustering', label: 'Grouping only', hint: 'Pool waiting rides', Icon: FlaskConical },
  { key: 'demand', label: 'Refresh demand', hint: 'Recount hot zones', Icon: Activity },
  { key: 'rebalance', label: 'Rebalance fleet', hint: 'Suggest idle moves', Icon: Truck },
]

function JobsPanel({ setView, toast }) {
  const [status, setStatus] = useState(null)
  const [runs, setRuns] = useState([])
  const [suggestions, setSuggestions] = useState([])
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(null)

  const load = useCallback(async () => {
    try {
      const [st, ru, sg] = await Promise.all([jobsApi.status(), jobsApi.runs(), jobsApi.rebalanceSuggestions()])
      setStatus(st); setRuns(ru || []); setSuggestions(sg || [])
    } catch (e) {
      toast('error', 'Failed to load jobs', e?.response?.data?.detail || '')
    } finally {
      setLoading(false)
    }
  }, [toast])
  useDeferredLoad(load)

  const runJob = async (type) => {
    setRunning(type)
    try {
      const fn = type === 'auto_dispatch' ? jobsApi.runAutoDispatch : type === 'clustering' ? jobsApi.runClustering : type === 'demand' ? jobsApi.runDemand : jobsApi.runRebalance
      const res = await fn()
      toast('success', 'Job started', res?.message || (res?.clusters_formed !== undefined ? `${res.clusters_formed} groups formed` : 'Done'))
      setTimeout(load, 1500)
    } catch (e) {
      toast('error', 'Job failed', e?.response?.data?.detail || '')
    } finally {
      setRunning(null)
    }
  }

  return (
    <div className="mx-auto w-full max-w-5xl space-y-4 p-4 md:p-7">
      <PageHeader
        title="Jobs"
        description="Recurring automation — run anything now with one tap"
        onBack={() => setView('admin-overview')}
        actions={
          <Button variant="outline" size="sm" onClick={load} className="gap-1.5">
            <RefreshCw className="h-3.5 w-3.5" /> Refresh
          </Button>
        }
      />

      {status && (
        <Card>
          <CardContent className="flex flex-wrap items-center gap-3 p-4">
            <span className={cn('flex h-2.5 w-2.5 rounded-full', status.scheduler_running ? 'animate-pulse bg-emerald-500' : 'bg-destructive')} />
            <p className="text-sm font-bold">Scheduler {status.scheduler_running ? 'running' : 'stopped'}</p>
            <Separator orientation="vertical" className="hidden h-5 sm:block" />
            <p className="text-xs text-muted-foreground">Grouping every {status.cluster_interval_seconds}s</p>
            <p className="text-xs text-muted-foreground">Demand every {status.demand_interval_seconds}s</p>
            <p className="text-xs text-muted-foreground">Rebalance every {status.rebalance_interval_seconds}s</p>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
        {JOB_BUTTONS.map(({ key, label, hint, Icon }) => (
          <Card key={key}>
            <CardContent className="space-y-2 p-3.5">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10">
                <Icon className="h-4 w-4 text-primary" />
              </span>
              <div>
                <p className="text-[13px] font-bold">{label}</p>
                <p className="text-[11px] text-muted-foreground">{hint}</p>
              </div>
              <Button size="sm" variant="secondary" className="h-8 w-full" onClick={() => runJob(key)} disabled={!!running}>
                {running === key ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
                {running === key ? 'Running…' : 'Run now'}
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm">Recent runs</CardTitle>
            <CardDescription>Newest first</CardDescription>
          </CardHeader>
          <CardContent className="space-y-1.5">
            {loading && <LoadingRows count={3} height="h-[52px]" />}
            {!loading && runs.length === 0 && <p className="text-sm text-muted-foreground">No runs yet.</p>}
            {runs.slice(0, 10).map((r) => (
              <div key={r.id} className="rounded-lg bg-muted/50 p-2.5">
                <div className="mb-1 flex items-center justify-between gap-2">
                  <p className="text-xs font-bold capitalize">{String(r.job_type || '').replace(/_/g, ' ')}</p>
                  <StatusBadge status={r.status} />
                </div>
                <p className="text-[11px] text-muted-foreground">
                  {r.started_at ? new Date(r.started_at).toLocaleString() : ''}{r.duration_seconds ? ` · ${Number(r.duration_seconds).toFixed(1)}s` : ''}
                </p>
                {r.error_message && <p className="mt-1 text-[11px] text-destructive">{r.error_message}</p>}
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm">Suggested vehicle moves</CardTitle>
            <CardDescription>Where idle vehicles would help most</CardDescription>
          </CardHeader>
          <CardContent className="space-y-1.5">
            {!loading && suggestions.length === 0 && <p className="text-sm text-muted-foreground">No suggestions right now.</p>}
            {suggestions.slice(0, 8).map((sg) => (
              <div key={sg.id} className="rounded-lg bg-muted/50 p-2.5 text-xs">
                <p className="font-bold">Vehicle #{sg.vehicle_id}</p>
                <p className="font-mono text-[11px] text-muted-foreground">→ {sg.target_lat?.toFixed(4)}, {sg.target_lng?.toFixed(4)}</p>
                <p className="mt-0.5 text-[11px] text-muted-foreground">{sg.reason}</p>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

// ─── Heatmap — where demand builds up ───────────────────────────────────────
function HeatmapPanel({ setView, toast }) {
  const [cells, setCells] = useState([])
  const [loading, setLoading] = useState(false)
  const [box, setBox] = useState({ minLat: '12.80', maxLat: '13.10', minLng: '77.40', maxLng: '77.80' })

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await predictApi.heatmap({
        min_lat: Number(box.minLat), max_lat: Number(box.maxLat),
        min_lng: Number(box.minLng), max_lng: Number(box.maxLng),
      })
      const list = res?.cells || []
      setCells(list)
      if (list.length === 0) toast('info', 'No demand data', 'Book some rides first to generate data.')
    } catch (e) {
      toast('error', 'Failed to load heatmap', e?.response?.data?.detail || '')
    } finally {
      setLoading(false)
    }
  }, [box, toast])
  useDeferredLoad(load)

  const sorted = useMemo(() => [...cells].sort((a, b) => (b.predicted_demand || 0) - (a.predicted_demand || 0)), [cells])
  const set = (k) => (e) => setBox((p) => ({ ...p, [k]: e.target.value }))

  return (
    <div className="mx-auto w-full max-w-6xl space-y-4 p-4 md:p-7">
      <PageHeader
        title="Demand heatmap"
        description="Predicted hot zones get idle vehicles sent their way"
        onBack={() => setView('admin-overview')}
        actions={
          cells.length > 0 ? (
            <Badge variant="secondary" className="mob-data gap-1.5">
              <Flame className="h-3 w-3" /> {cells.length} zones
            </Badge>
          ) : undefined
        }
      />

      {/* Area controls: slim strip, not a card */}
      <div className="flex flex-wrap items-end gap-2 rounded-xl border bg-card px-3 py-2.5 shadow-sm">
        <div className="grid flex-1 grid-cols-2 gap-2 sm:grid-cols-4">
          <Field label="Min lat"><Input value={box.minLat} onChange={set('minLat')} inputMode="decimal" className="mob-data h-8 text-xs" /></Field>
          <Field label="Max lat"><Input value={box.maxLat} onChange={set('maxLat')} inputMode="decimal" className="mob-data h-8 text-xs" /></Field>
          <Field label="Min lng"><Input value={box.minLng} onChange={set('minLng')} inputMode="decimal" className="mob-data h-8 text-xs" /></Field>
          <Field label="Max lng"><Input value={box.maxLng} onChange={set('maxLng')} inputMode="decimal" className="mob-data h-8 text-xs" /></Field>
        </div>
        <Button onClick={load} disabled={loading} className="gap-1.5">
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Flame className="h-4 w-4" />}
          {loading ? 'Loading…' : 'Show demand'}
        </Button>
      </div>
      <p className="-mt-2 text-[11px] text-muted-foreground">Defaults cover Bengaluru — change only if you operate elsewhere.</p>

      {/* Map is the centerpiece: full-bleed with floating legend */}
      {cells.length > 0 && (
        <div className="map-workspace relative h-[52vh] min-h-[320px] overflow-hidden rounded-xl border shadow-sm lg:h-[58vh]">
          <AppMap
            center={[(Number(box.minLat) + Number(box.maxLat)) / 2, (Number(box.minLng) + Number(box.maxLng)) / 2]}
            zoom={12}
            height="100%"
            heatCells={cells}
            style={{ borderRadius: 0 }}
          />
          <div className="absolute bottom-3 left-3 z-[500] rounded-lg border border-border/80 bg-card/95 px-3 py-2 shadow-md backdrop-blur">
            <p className="mob-section-label mb-1.5">Predicted demand</p>
            <div className="heat-legend-gradient h-1.5 w-40 rounded-full" aria-hidden="true" />
            <div className="mob-data mt-1 flex w-40 justify-between text-[10px] text-muted-foreground"><span>Low</span><span>High</span></div>
          </div>
          {sorted[0] && (
            <div className="absolute right-3 top-3 z-[500] rounded-lg border border-border/80 bg-card/95 px-3 py-2 shadow-md backdrop-blur">
              <p className="mob-section-label">Hottest zone</p>
              <p className="mob-data text-sm font-bold text-destructive">{sorted[0].predicted_demand?.toFixed(1)} <span className="text-[11px] font-medium text-muted-foreground">· {sorted[0].historical_request_count} past rides</span></p>
            </div>
          )}
        </div>
      )}

      {cells.length > 0 && (
        <div>
          <p className="mb-2 text-sm font-semibold">Hottest zones first</p>
          <div className="overflow-hidden rounded-xl border bg-card shadow-sm">
            <div className="max-h-[320px] overflow-auto">
              <Table>
                <TableHeader className="sticky top-0 bg-muted/80 backdrop-blur">
                  <TableRow>
                    {['Zone', 'Lat', 'Lng', 'Past rides', 'Predicted'].map((h) => (
                      <TableHead key={h} className="px-4">{h}</TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {sorted.map((c) => (
                    <TableRow key={c.h3_index}>
                      <TableCell className="mob-data max-w-[180px] truncate font-mono text-[11px]">{c.h3_index}</TableCell>
                      <TableCell className="mob-data text-muted-foreground">{c.latitude?.toFixed(3)}</TableCell>
                      <TableCell className="mob-data text-muted-foreground">{c.longitude?.toFixed(3)}</TableCell>
                      <TableCell className="mob-data font-semibold">{c.historical_request_count}</TableCell>
                      <TableCell className="mob-data font-bold text-destructive">{c.predicted_demand?.toFixed(1) || '—'}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </div>
        </div>
      )}
      {!loading && cells.length === 0 && (
        <EmptyState icon={Flame} title="No demand data" hint="Book some rides first to generate data." />
      )}
    </div>
  )
}

// ─── Drivers — the one place driver approvals happen ───────────────────────
function PendingDriversPanel({ setView, toast }) {
  const [pending, setPending] = useState([])
  const [loading, setLoading] = useState(true)
  const [verifying, setVerifying] = useState({})

  const load = useCallback(async () => {
    try {
      const data = await authApi.getPendingDrivers()
      setPending(Array.isArray(data) ? data : [])
    } catch (e) {
      toast('error', 'Failed to load applicants', e?.response?.data?.detail || '')
    } finally {
      setLoading(false)
    }
  }, [toast])
  useDeferredLoad(load)

  const handleVerify = async (userId, status) => {
    setVerifying((p) => ({ ...p, [userId]: status }))
    try {
      await authApi.verifyDriver(userId, status)
      setPending((p) => p.filter((d) => d.id !== userId))
      toast('success',
        status === 'active' ? 'Driver approved' : status === 'rejected' ? 'Driver rejected' : `Driver ${status}`,
        `Applicant #${userId} updated.`)
    } catch (e) {
      toast('error', 'Action failed', e?.response?.data?.detail || '')
    } finally {
      setVerifying((p) => { const n = { ...p }; delete n[userId]; return n })
    }
  }

  return (
    <div className="mx-auto w-full max-w-4xl space-y-4 p-4 md:p-7">
      <PageHeader
        title="Drivers"
        description={pending.length ? `${pending.length} applicant${pending.length === 1 ? '' : 's'} waiting — approve to unlock driving` : 'Approve applicants so they can start driving'}
        onBack={() => setView('admin-overview')}
        actions={
          <Button variant="outline" size="sm" onClick={load} disabled={loading} className="gap-1.5">
            <RefreshCw className="h-3.5 w-3.5" /> Refresh
          </Button>
        }
      />

      <Card className="border-primary/25 bg-primary/[0.04]">
        <CardContent className="flex gap-3 p-4">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10">
            <Info className="h-4 w-4 text-primary" />
          </span>
          <p className="text-xs leading-relaxed text-muted-foreground">
            Anyone who signs up as a driver waits here first. <strong className="text-foreground">Approve</strong> unlocks
            driving, <strong className="text-foreground">Suspend</strong> pauses them, <strong className="text-foreground">Reject</strong> removes
            the application.
          </p>
        </CardContent>
      </Card>

      {loading ? (
        <LoadingRows />
      ) : pending.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-1.5 py-12 text-center">
            <CheckCheck className="h-8 w-8 text-emerald-500" />
            <p className="font-bold">All caught up</p>
            <p className="text-sm text-muted-foreground">Every driver application has been reviewed.</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {pending.map((driver) => (
            <Card key={driver.id} className="border-amber-500/30">
              <CardContent className="flex flex-wrap items-center gap-3 p-3.5">
                <Avatar className="h-9 w-9">
                  <AvatarFallback className="bg-primary/10 text-sm font-bold text-primary">
                    {driver.name?.charAt(0)?.toUpperCase() || '?'}
                  </AvatarFallback>
                </Avatar>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[13px] font-bold">{driver.name}</p>
                  <p className="truncate text-xs text-muted-foreground">{driver.email}{driver.phone ? ` · ${driver.phone}` : ''}</p>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  <Button
                    size="sm"
                    variant="secondary"
                    className="h-8 gap-1 border border-emerald-500/40 text-emerald-600 hover:text-emerald-600 dark:text-emerald-400 dark:hover:text-emerald-400"
                    disabled={!!verifying[driver.id]}
                    onClick={() => handleVerify(driver.id, 'active')}
                  >
                    {verifying[driver.id] === 'active' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
                    Approve
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-8 gap-1 text-amber-600 hover:text-amber-600 dark:text-amber-400 dark:hover:text-amber-400"
                    disabled={!!verifying[driver.id]}
                    onClick={() => handleVerify(driver.id, 'suspended')}
                  >
                    <PauseCircle className="h-3.5 w-3.5" /> Suspend
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-8 gap-1 text-destructive hover:text-destructive"
                    disabled={!!verifying[driver.id]}
                    onClick={() => handleVerify(driver.id, 'rejected')}
                  >
                    <XCircle className="h-3.5 w-3.5" /> Reject
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}

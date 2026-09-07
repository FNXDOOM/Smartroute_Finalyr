import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import {
  ArrowLeft, ArrowUp, BatteryCharging, CarFront, CheckCircle2, ChevronRight,
  CircleDot, Clock, CornerUpRight, Flag, Gauge, Loader2, LocateFixed, MapPin,
  Navigation, Pause, Play, RefreshCw, Route as RouteIcon, Satellite, Users,
} from 'lucide-react'
import { ridesApi, trackingApi, routeApi, vehiclesApi, createTrackingWS } from '../services/api.js'
import { useAuth } from '@clerk/clerk-react'
import AppMap from '../components/AppMap'
import { DEMO_PRESETS } from '../config/demoPresets.js'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Separator } from '@/components/ui/separator'

const DEMO_RIDES = DEMO_PRESETS.indiranagar.riders.map((r, i) => ({
  id: r.id,
  name: r.name,
  pickup: r.plbl,
  dest: r.dlbl,
  status: 'assigned',
  fare: r.fare,
  plat: r.plat,
  plng: r.plng,
  dlat: r.dlat,
  dlng: r.dlng,
  stopOrder: i + 1,
}))

const FULL_PATH = DEMO_PRESETS.indiranagar.roadPath

function nearestSegIndex(lng, lat, path) {
  let best = 0
  let bestD = Infinity
  for (let i = 0; i < path.length; i += 1) {
    const dx = path[i][0] - lng
    const dy = path[i][1] - lat
    const d = dx * dx + dy * dy
    if (d < bestD) { bestD = d; best = i }
  }
  return best
}

// Board segment of each demo rider on the full pooled path (Priya idx 1,
// Rohan idx 2, Ananya idx 3). Computed, not hardcoded, so the data fix above
// and the sim/manifest thresholds can't drift apart.
const demoBoardSeg = Object.fromEntries(
  DEMO_RIDES.map((r) => [r.id, nearestSegIndex(r.plng, r.plat, FULL_PATH)]),
)

// Per-ride animation path. The pooled roadPath ends at each rider's door in
// order: idx 9 = Church St (Rohan, stop 2), idx 10 = Brigade Rd (Priya,
// stop 3), idx 11 = MG Road (Ananya, stop 1). Truncating there gives each of
// the 3 previews a visibly different route + end marker instead of replaying
// the same full animation.
function pathForRide(ride) {
  if (!ride || ride.plat == null || ride.dlat == null) return FULL_PATH
  if (ride.stopOrder === 2) {
    const base = FULL_PATH.slice(0, 10)
    return [...base, [ride.dlng, ride.dlat]]
  }
  if (ride.stopOrder === 3) {
    const base = FULL_PATH.slice(0, 11)
    return [...base, [ride.dlng, ride.dlat]]
  }
  if (ride.stopOrder === 1) return FULL_PATH
  return [[77.6408, 12.9784], [ride.plng, ride.plat], [ride.dlng, ride.dlat]]
}

export default function DriverView({ user, view, setView, toast }) {
  const { getToken } = useAuth()
  const [vehicles,   setVehicles]   = useState([])
  const [rides,      setRides]      = useState([])
  const [routes,     setRoutes]     = useState([])
  const [tracking,   setTracking]   = useState({ vehicles:[], events:[] })
  const [loading,    setLoading]    = useState(true)
  const [myVehicle,  setMyVehicle]  = useState(null)
  const [updatingLoc,setUpdatingLoc]= useState(false)
  const [simActive,  setSimActive]  = useState(false)
  const [simProgress,setSimProgress]= useState(0)
  const [simCoords,  setSimCoords]  = useState([77.6408, 12.9784])
  const [simBearing, setSimBearing] = useState(180)
  const [simSpeed,   setSimSpeed]   = useState(0)
  const [previewRide, setPreviewRide] = useState(null)
  const [runRide, setRunRide] = useState(null)
  const simTimerRef = useRef(null)
  const simFiredRef = useRef(new Set())
  const simPathRef = useRef(null)
  const wsRef = useRef(null)

  const loadData = useCallback(async () => {
    try {
      const [v, r, ro] = await Promise.all([vehiclesApi.list(), ridesApi.getAll({ status:'assigned', limit:20 }), routeApi.history(10)])
      setVehicles(Array.isArray(v)?v:[])
      setRides(Array.isArray(r)?r:[])
      setRoutes(ro?.routes || [])
      if (Array.isArray(v) && v.length) setMyVehicle(v[0])
    } catch(e) { toast('error','Failed to load data', e?.response?.data?.detail||'') }
    setLoading(false)
  }, [toast])

  useEffect(() => { const timer = setTimeout(() => { void loadData() }, 0); return () => clearTimeout(timer) }, [loadData])

  // Live tracking WebSocket
  useEffect(() => {
    let dead = false
    const connect = async () => {
      try {
        const token = await getToken()
        if (!token || dead) return
        wsRef.current = createTrackingWS(token, (msg) => {
          if (dead) return
          if (msg.type === 'tracking_snapshot') {
            setTracking({ vehicles: msg.vehicles || [], events: msg.events || [] })
          } else if (msg.type === 'vehicle_location_update' && msg.vehicle) {
            setTracking(prev => ({
              vehicles: prev.vehicles.some(vehicle => vehicle.id === msg.vehicle.id)
                ? prev.vehicles.map(vehicle => vehicle.id === msg.vehicle.id ? { ...vehicle, ...msg.vehicle } : vehicle)
                : [...prev.vehicles, msg.vehicle],
              events: msg.event ? [msg.event, ...prev.events].slice(0, 50) : prev.events,
            }))
            setMyVehicle(prev => prev?.id === msg.vehicle.id ? { ...prev, ...msg.vehicle } : prev)
          }
        }, () => { if (!dead) setTimeout(connect, 3000) })
      } catch (error) { void error }
    }
    connect()
    return () => { dead = true; wsRef.current?.close() }
  }, [getToken])

  const updateLocation = async () => {
    if (!myVehicle) { toast('warning','No vehicle selected'); return }
    setUpdatingLoc(true)
    try {
      const position = await new Promise((resolve, reject) => {
        if (!navigator.geolocation) return reject(new Error('GPS is not available'))
        navigator.geolocation.getCurrentPosition(resolve, reject)
      })
      await trackingApi.updateLocation(myVehicle.id, { lat: position.coords.latitude, lng: position.coords.longitude })
      toast('success','Location updated')
    } catch(e) { toast('error','Failed to update',e?.response?.data?.detail||''); setUpdatingLoc(false) }
    finally { setUpdatingLoc(false) }
  }

  const updateRideStatus = async (rideId, status) => {
    try {
      await ridesApi.updateStatus(rideId, status)
      setRides(prev => prev.map(r => r.id===rideId ? {...r, status} : r))
      toast('success', `Ride #${rideId} → ${status}`)
    } catch(e) { toast('error','Failed', e?.response?.data?.detail||'') }
  }

  // Interactive Driver Route Drive Simulation.
  // overrideRide === undefined → drive whatever is previewed (or the full
  // pooled route). overrideRide === null → force the full pooled route.
  // Each previewed rider drives its own truncated pathForRide so ride 2/3
  // don't replay ride 1's animation.
  const toggleDriveSimulation = (overrideRide) => {
    if (simActive) {
      if (simTimerRef.current) clearInterval(simTimerRef.current)
      setSimActive(false)
      setSimSpeed(0)
      toast('info', 'GPS Simulation Paused')
      return
    }

    const resolvedRide = overrideRide !== undefined ? overrideRide : previewRide
    // Switching context (e.g. finished ride 1, now starting ride 2, or a
    // paused single run giving way to a full pooled run) must restart.
    const switchingContext = (resolvedRide?.id ?? null) !== (runRide?.id ?? (simPathRef.current?.rideId ?? null))
    let p = simProgress >= 1 || (switchingContext && simProgress > 0) ? 0 : simProgress
    let path
    if (p === 0) {
      path = pathForRide(resolvedRide)
      simPathRef.current = { path, rideId: resolvedRide?.id ?? null }
      setRunRide(resolvedRide ?? null)
      simFiredRef.current = new Set()
      setSimProgress(0)
      setSimCoords([path[0][0], path[0][1]])
    } else {
      path = simPathRef.current?.path || pathForRide(resolvedRide)
    }
    const totalSegments = path.length - 1
    const single = !!resolvedRide
    const boardAt = single
      ? Math.min(nearestSegIndex(resolvedRide.plng, resolvedRide.plat, path) / totalSegments, 0.9)
      : 0
    const fireOnce = (key, type, title, body) => {
      if (simFiredRef.current.has(key)) return
      simFiredRef.current.add(key)
      toast(type, title, body)
    }

    setSimActive(true)
    toast('success', single ? `Driving ${resolvedRide.name}` : 'Driver Navigation Active', single ? `${resolvedRide.pickup} → ${resolvedRide.dest}.` : 'Simulating live road traversal to Virtual Stop #1 and MG Road.')
    const totalSteps = 200

    if (simTimerRef.current) clearInterval(simTimerRef.current)
    simTimerRef.current = setInterval(() => {
      p += 1 / totalSteps
      if (p >= 1) {
        p = 1
        clearInterval(simTimerRef.current)
        setSimActive(false)
        setSimProgress(1)
        setSimSpeed(0)
        if (single) fireOnce('drop', 'success', `Dropped ${resolvedRide.name}`, `${resolvedRide.dest} · trip complete.`)
        else fireOnce('ananya', 'success', 'Dropped Ananya Sharma', 'MG Road Metro Station · trip complete.')
        toast('success', 'Route Navigation Finished', single ? `${resolvedRide.name} delivered.` : 'All dropoffs completed.')
        return
      }

      setSimProgress(p)
      if (single) {
        if (p >= boardAt) fireOnce('board', 'success', `Boarded ${resolvedRide.name}`, `${resolvedRide.pickup}.`)
      } else {
        // Sequential boardings at three distinct pins — not one shared stop.
        if (p >= demoBoardSeg[103] / totalSegments) fireOnce('board-priya', 'success', 'Boarded Priya Iyer', 'Stop C · 100 Feet Rd.')
        if (p >= demoBoardSeg[102] / totalSegments) fireOnce('board-rohan', 'success', 'Boarded Rohan Mehta', 'Stop B · 100 Feet Rd.')
        if (p >= demoBoardSeg[101] / totalSegments) fireOnce('board-ananya', 'success', 'Boarded Ananya Sharma', 'Stop A · 100 Feet Rd.')
        if (p >= 9 / totalSegments) fireOnce('rohan', 'info', 'Dropped Rohan Mehta', 'Church Street Boulevard · ₹42.')
        if (p >= 10 / totalSegments) fireOnce('priya', 'info', 'Dropped Priya Iyer', 'Brigade Road Junction · ₹48.')
      }

      const segmentFloat = p * totalSegments
      const segIndex = Math.min(Math.floor(segmentFloat), totalSegments - 1)
      const segFraction = segmentFloat - segIndex

      const [lng1, lat1] = path[segIndex]
      const [lng2, lat2] = path[segIndex + 1]

      const currLng = lng1 + (lng2 - lng1) * segFraction
      const currLat = lat1 + (lat2 - lat1) * segFraction

      const dy = lat2 - lat1
      const dx = (lng2 - lng1) * Math.cos((lat1 * Math.PI) / 180)
      const bearing = (Math.atan2(dx, dy) * 180) / Math.PI

      setSimCoords([currLng, currLat])
      setSimBearing(bearing)
      setSimSpeed(Math.round(35 + Math.sin(p * 20) * 5))

      // Push telemetry (functional update — the interval closure holds a stale
      // myVehicle value, so never gate on it).
      setMyVehicle(prev => (prev ? { ...prev, lat: currLat, lng: currLng } : prev))
    }, 80)
  }

  const resetSim = () => {
    if (simTimerRef.current) clearInterval(simTimerRef.current)
    simPathRef.current = null
    simFiredRef.current = new Set()
    setSimActive(false)
    setSimSpeed(0)
    setSimProgress(0)
    setSimCoords([FULL_PATH[0][0], FULL_PATH[0][1]])
    setRunRide(null)
  }

  // Opening a different ride's preview always restarts from the depot so ride
  // 2 never resumes ride 1's mid-path progress.
  const openPreview = (ride) => {
    if (simTimerRef.current) clearInterval(simTimerRef.current)
    simPathRef.current = null
    simFiredRef.current = new Set()
    setSimActive(false)
    setSimSpeed(0)
    setSimProgress(0)
    setSimCoords([FULL_PATH[0][0], FULL_PATH[0][1]])
    setRunRide(null)
    setPreviewRide(ride)
    setView('driver-map')
  }

  const openFullNav = () => {
    // A paused single-rider run can't resume on the full pooled path —
    // discard it so Start begins a fresh full drive.
    if (!simActive && runRide && simProgress > 0) resetSim()
    setPreviewRide(null)
    setView('driver-map')
  }

  const startFullNav = () => {
    setPreviewRide(null)
    setView('driver-map')
    if (!simActive) toggleDriveSimulation(null)
  }

  useEffect(() => {
    return () => {
      if (simTimerRef.current) clearInterval(simTimerRef.current)
    }
  }, [])

  if (view === 'driver-map') {
    return (
      <LiveMapView
        myVehicle={myVehicle}
        onBack={() => { setPreviewRide(null); setView('driver-home') }}
        onUpdateLoc={updateLocation}
        updating={updatingLoc}
        simActive={simActive}
        simProgress={simProgress}
        simSpeed={simSpeed}
        simCoords={simCoords}
        simBearing={simBearing}
        onToggleSim={() => toggleDriveSimulation()}
        previewRide={previewRide}
        runRide={runRide}
        onClearPreview={() => setPreviewRide(null)}
        onResetSim={resetSim}
      />
    )
  }

  if (view === 'driver-routes') {
    return <RoutesView routes={routes} loading={loading} onBack={()=>setView('driver-home')} onStartNav={startFullNav} />
  }

  // Driver dashboard home
  const firstName = user?.name?.split(' ')[0] || 'Driver'
  const activeVehicles = tracking.vehicles.filter((v) => v.status !== 'idle').length
  const pendingRides = rides.filter((r) => r.status === 'assigned').length
  const usingDemoManifest = rides.length === 0
  // Pooled thresholds for the full 11-segment roadPath: sequential boardings
  // at three distinct pins (Priya Stop C → Rohan Stop B → Ananya Stop A),
  // then drops Rohan (stop 2) at seg 9, Priya (stop 3) at seg 10, Ananya
  // (stop 1) at the end. A single-rider run (runRide set) only moves its own
  // card, boarding at its own pin.
  const demoDropAt = { 1: 1.01, 2: 9 / 11, 3: 10 / 11 }
  const demoBoardAt = { 101: demoBoardSeg[101] / 11, 102: demoBoardSeg[102] / 11, 103: demoBoardSeg[103] / 11 }
  const runBoardAt = runRide ? Math.min(nearestSegIndex(runRide.plng, runRide.plat, pathForRide(runRide)) / (pathForRide(runRide).length - 1), 0.9) : 3 / 11
  const manifest = rides.length > 0
    ? rides.slice(0, 6).map((r) => ({
        id: r.id,
        name: r.passenger_name || r.rider_name || `Rider #${r.id}`,
        pickup: r.pickup_label || 'Pickup stop',
        dest: r.destination_label || 'Destination',
        status: r.status,
        fare: r.fare ? `₹${r.fare}` : r.ride_option_price || '',
        plat: r.pickup_lat,
        plng: r.pickup_lng,
        dlat: r.dest_lat,
        dlng: r.dest_lng,
        stopOrder: null,
      }))
    : DEMO_RIDES.map((r) => {
        if (simProgress <= 0) return r
        if (runRide) {
          if (r.id !== runRide.id) return r
          if (simProgress >= 1) return { ...r, status: 'completed' }
          return simProgress >= runBoardAt ? { ...r, status: 'in_progress' } : r
        }
        if (simProgress >= (demoDropAt[r.stopOrder] ?? 1)) return { ...r, status: 'completed' }
        if (simProgress >= (demoBoardAt[r.id] ?? 3 / 11)) return { ...r, status: 'in_progress' }
        return r
      })

  return (
    <div className="mx-auto w-full max-w-6xl space-y-5 p-4 md:p-7">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-3">
        <Avatar className="h-11 w-11">
          <AvatarFallback className="bg-primary text-base font-extrabold text-primary-foreground">
            {firstName.charAt(0).toUpperCase()}
          </AvatarFallback>
        </Avatar>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="font-display text-xl font-extrabold tracking-tight md:text-2xl">Driver Dashboard</h1>
            <Badge variant="secondary" className="gap-1.5">
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-500 opacity-60" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
              </span>
              Live dispatch
            </Badge>
          </div>
          <p className="mt-0.5 truncate text-sm text-muted-foreground">
            Welcome back, {firstName} · {myVehicle?.license_plate || 'No vehicle assigned'}
          </p>
        </div>
        {vehicles.length > 1 ? (
          <select
            aria-label="Select vehicle"
            value={myVehicle?.id ?? ''}
            onChange={(e) => {
              const next = vehicles.find((v) => String(v.id) === e.target.value)
              if (next) setMyVehicle(next)
            }}
            className="h-9 rounded-md border border-input bg-background px-2.5 text-sm shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {vehicles.map((v) => (
              <option key={v.id} value={v.id}>{v.license_plate} · {v.status}</option>
            ))}
          </select>
        ) : myVehicle ? (
          <Badge variant="outline" className="gap-1.5 font-mono">
            <CarFront className="h-3.5 w-3.5" /> {myVehicle.license_plate}
          </Badge>
        ) : null}
      </div>

      {/* Stats */}
      {loading ? (
        <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <Card key={i}><CardContent className="space-y-2 p-4"><div className="h-3 w-20 animate-pulse rounded bg-muted" /><div className="h-7 w-16 animate-pulse rounded bg-muted" /></CardContent></Card>
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
          <StatCard icon={CarFront} label="My Vehicle" value={myVehicle?.license_plate || 'Unassigned'} sub={myVehicle ? `${myVehicle.status || 'ready'} · cap ${myVehicle.capacity || 4}` : 'Contact dispatch'} />
          <StatCard icon={Satellite} label="Active Vehicles" value={String(activeVehicles)} sub="On fleet network" />
          <StatCard icon={Users} label="Assigned Rides" value={String(pendingRides)} sub={pendingRides === 1 ? '1 pickup waiting' : `${pendingRides} pickups waiting`} />
          <StatCard icon={RouteIcon} label="My Routes" value={String(routes.length)} sub={routes.length ? 'Optimized by AI' : 'No routes yet'} />
        </div>
      )}

      {/* Quick actions */}
      <Card>
        <CardContent className="flex flex-wrap gap-2 p-3.5">
          <Button onClick={openFullNav} className="flex-1 sm:flex-none">
            <Navigation className="h-4 w-4" /> Open Live Navigation
          </Button>
          <Button variant="outline" onClick={updateLocation} disabled={updatingLoc || !myVehicle}>
            {updatingLoc ? <Loader2 className="h-4 w-4 animate-spin" /> : <LocateFixed className="h-4 w-4" />}
            {updatingLoc ? 'Updating…' : 'Push GPS Telemetry'}
          </Button>
          <Button variant="secondary" onClick={() => setView('driver-routes')}>
            <RouteIcon className="h-4 w-4" /> My Assigned Routes
          </Button>
          <Button variant="ghost" size="icon" onClick={() => void loadData()} aria-label="Refresh dashboard">
            <RefreshCw className="h-4 w-4" />
          </Button>
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
        {/* Assigned rides */}
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between gap-2">
              <div>
                <CardTitle className="text-sm">Passenger Manifest</CardTitle>
                <CardDescription>Board and drop off in stop order</CardDescription>
              </div>
              <Badge variant="secondary">{usingDemoManifest ? `${manifest.length} pooled · demo` : `${manifest.length} pooled`}</Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-2">
            {loading ? (
              [0, 1, 2].map((i) => <div key={i} className="h-[104px] animate-pulse rounded-lg bg-muted/60" />)
            ) : manifest.length === 0 ? (
              <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed py-10 text-center">
                <CircleDot className="h-6 w-6 text-muted-foreground" />
                <p className="text-sm font-semibold">No assigned rides</p>
                <p className="max-w-[260px] text-xs text-muted-foreground">New pooled pickups from dispatch will appear here automatically.</p>
              </div>
            ) : (
              manifest.map((ride, idx) => (
                <div key={ride.id} className="rounded-lg border bg-card p-3.5 shadow-sm transition-colors hover:border-primary/30">
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <div className="flex min-w-0 items-center gap-2">
                      <Avatar className="h-7 w-7">
                        <AvatarFallback className="bg-primary/10 text-[11px] font-bold text-primary">
                          {String(ride.name).charAt(0).toUpperCase()}
                        </AvatarFallback>
                      </Avatar>
                      <p className="truncate text-[13px] font-semibold">{ride.name}</p>
                      {ride.stopOrder && (
                        <Badge variant="secondary" className="shrink-0">Stop {ride.stopOrder} of {manifest.length}</Badge>
                      )}
                      {ride.fare && <Badge variant="outline" className="shrink-0">{ride.fare}</Badge>}
                    </div>
                    <StatusBadge status={ride.status} />
                  </div>
                  <p className="flex items-center gap-1.5 truncate text-xs text-muted-foreground">
                    <MapPin className="h-3.5 w-3.5 shrink-0 text-primary" /> {ride.pickup}
                  </p>
                  <p className="mt-1 flex items-center gap-1.5 truncate text-xs text-muted-foreground">
                    <Flag className="h-3.5 w-3.5 shrink-0 text-rose-500" /> {ride.dest}
                  </p>
                  {!usingDemoManifest && (
                    <div className="mt-2.5 flex gap-2">
                      <Button size="sm" variant="secondary" className="h-8 flex-1" onClick={() => updateRideStatus(ride.id, 'in_progress')}>
                        <CheckCircle2 className="h-3.5 w-3.5" /> Board
                      </Button>
                      <Button size="sm" variant="outline" className="h-8 flex-1" onClick={() => updateRideStatus(ride.id, 'completed')}>
                        Dropoff <ChevronRight className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  )}
                  {usingDemoManifest && (
                    <div className="mt-2.5 flex gap-2">
                      <Button size="sm" variant="secondary" className="h-8 flex-1" onClick={() => openPreview(ride)}>
                        <Navigation className="h-3.5 w-3.5" /> Preview {ride.stopOrder ? `stop ${ride.stopOrder}` : 'route'} · {String(ride.dest).split(',')[0]}
                      </Button>
                    </div>
                  )}
                  {!usingDemoManifest && ride.plat != null && ride.dlat != null && (
                    <div className="mt-2">
                      <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={() => openPreview(ride)}>
                        <MapPin className="h-3.5 w-3.5" /> Preview this ride on map
                      </Button>
                    </div>
                  )}
                </div>
              ))
            )}
            {usingDemoManifest && !loading && (
              <p className="pt-1 text-center text-[11px] text-muted-foreground">Demo preview — live assignments from dispatch will replace this list.</p>
            )}
          </CardContent>
        </Card>

        {/* Vehicle diagnostics */}
        <div className="space-y-4">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">Vehicle Status</CardTitle>
              <CardDescription>Diagnostics & telemetry</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="rounded-lg bg-muted/50 p-3">
                <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Assigned vehicle</p>
                <div className="mt-1 flex items-center justify-between gap-2">
                  <p className="font-mono text-base font-extrabold">{myVehicle?.license_plate || '—'}</p>
                  {myVehicle && <StatusBadge status={myVehicle.status || 'idle'} />}
                </div>
                <p className="mt-0.5 text-xs text-muted-foreground">Tata Tigor EV · Capacity {myVehicle?.capacity || 6} passengers</p>
              </div>
              <div className="rounded-lg bg-muted/50 p-3">
                <div className="flex items-center justify-between">
                  <p className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                    <BatteryCharging className="h-3.5 w-3.5 text-emerald-500" /> Battery / Range
                  </p>
                  <span className="text-xs font-bold text-emerald-600 dark:text-emerald-400">88%</span>
                </div>
                <div className="mt-2 h-2 overflow-hidden rounded-full bg-secondary">
                  <div className="h-full w-[88%] rounded-full bg-emerald-500" />
                </div>
                <p className="mt-1.5 text-xs text-muted-foreground">195 km remaining · healthy</p>
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="rounded-lg border p-2.5">
                  <p className="flex items-center gap-1 text-muted-foreground"><Users className="h-3.5 w-3.5" /> Seats</p>
                  <p className="mt-1 text-sm font-bold">{myVehicle?.capacity || 6} total</p>
                </div>
                <div className="rounded-lg border p-2.5">
                  <p className="flex items-center gap-1 text-muted-foreground"><Clock className="h-3.5 w-3.5" /> Shift</p>
                  <p className="mt-1 text-sm font-bold">On duty</p>
                </div>
              </div>
              {myVehicle?.lat != null && (
                <p className="font-mono text-[11px] text-muted-foreground">
                  GPS {Number(myVehicle.lat).toFixed(5)}, {Number(myVehicle.lng).toFixed(5)}
                </p>
              )}
              <Separator />
              <Button variant="outline" className="w-full" onClick={updateLocation} disabled={updatingLoc || !myVehicle}>
                {updatingLoc ? <Loader2 className="h-4 w-4 animate-spin" /> : <Satellite className="h-4 w-4" />}
                {updatingLoc ? 'Pushing telemetry…' : 'Push GPS Telemetry'}
              </Button>
            </CardContent>
          </Card>

          <Card className="border-primary/25 bg-primary/[0.04]">
            <CardContent className="flex gap-3 p-4">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10">
                <Navigation className="h-4 w-4 text-primary" />
              </span>
              <div className="min-w-0">
                <p className="text-[13px] font-bold">Indiranagar → MG Road ready</p>
                <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">4.2 km · 3 pooled stops · optimized route loaded. Start navigation when you leave the depot.</p>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
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
        <p className="mt-2 truncate font-display text-xl font-extrabold tracking-tight" title={value}>{value}</p>
        <p className="mt-0.5 truncate text-xs text-muted-foreground">{sub}</p>
      </CardContent>
    </Card>
  )
}

// ─── Live Navigation Map View ──────────────────────────────────────────────────
function LiveMapView({ myVehicle, onBack, onUpdateLoc, updating, simActive, simProgress, simSpeed, simCoords, simBearing, onToggleSim, previewRide, runRide, onClearPreview, onResetSim }) {
  // The run's own ride wins once a simulation exists; otherwise the static
  // preview. Either way the blue route line + animation follow that ride's
  // truncated pathForRide, never a shared full path.
  const contextRide = (simActive || simProgress > 0) && runRide ? runRide : previewRide
  // Memoized: the sim ticks every 80ms (new simCoords → re-render). Without
  // this, fresh array references retrigger AppMap's overlay effect each tick,
  // which removes + re-adds every pin so the drop-in animation replays as a
  // rapid blink. These only recompute when the selected ride actually changes.
  const activePath = useMemo(() => pathForRide(contextRide), [contextRide])
  const vehicle = {
    id: myVehicle?.id || 99,
    license_plate: myVehicle?.license_plate || 'KA-01-TEST-99',
    status: simActive ? 'active' : 'idle',
    lat: simCoords[1],
    lng: simCoords[0],
    bearing: simBearing,
  }

  const waypoints = useMemo(() => (
    contextRide?.plat != null && contextRide?.dlat != null
      ? [
          { lat: 12.9784, lng: 77.6408, waypoint_type: 'depot', label: 'Depot' },
          { lat: contextRide.plat, lng: contextRide.plng, waypoint_type: 'pickup', label: `${contextRide.name} pickup` },
          { lat: contextRide.dlat, lng: contextRide.dlng, waypoint_type: 'destination', label: `${contextRide.name} dropoff` },
        ]
      : [
          { lat: 12.9784, lng: 77.6408, waypoint_type: 'depot', label: 'Depot' },
          { lat: 12.97650, lng: 77.64100, waypoint_type: 'pickup', label: 'Stop C · Priya' },
          { lat: 12.97400, lng: 77.64110, waypoint_type: 'pickup', label: 'Stop B · Rohan' },
          { lat: 12.97190, lng: 77.64124, waypoint_type: 'pickup', label: 'Stop A · Ananya' },
          { lat: 12.97490, lng: 77.60800, waypoint_type: 'waypoint', label: 'Drop · Rohan' },
          { lat: 12.97340, lng: 77.60750, waypoint_type: 'waypoint', label: 'Drop · Priya' },
          { lat: 12.97560, lng: 77.60660, waypoint_type: 'destination', label: 'MG Road · Ananya' },
        ]
  ), [contextRide])

  // When previewing a single rider (and not driving), center on that rider's
  // leg so each card visibly opens a different map. While driving, follow GPS.
  const mapCenter = simActive
    ? [simCoords[1], simCoords[0]]
    : contextRide?.plat != null && contextRide?.dlat != null
      ? [(contextRide.plat + contextRide.dlat) / 2, (contextRide.plng + contextRide.dlng) / 2]
      : [simCoords[1], simCoords[0]]
  const mapZoom = contextRide && !simActive ? 14.5 : 14

  const boardAt = Math.min(3 / (activePath.length - 1), 0.9)
  const totalKm = contextRide?.stopOrder === 2 ? 3.6 : contextRide?.stopOrder === 3 ? 3.9 : 4.2
  let navInstruction = 'Head South on 100 Feet Rd towards Virtual Stop #1'
  let nextStopLabel = '100 Ft Rd · Stop 1'
  let nextStopShort = 'Virtual Stop #1'
  if (contextRide) {
    const destShort = String(contextRide.dest).split(',')[0]
    if (simProgress >= 1) {
      navInstruction = `Delivered ${contextRide.name} · ${contextRide.dest}`
      nextStopLabel = `${destShort} · delivered`
      nextStopShort = destShort
    } else if (simProgress >= boardAt) {
      navInstruction = `En route: dropping ${contextRide.name} at ${destShort}`
      nextStopLabel = `${destShort} · ${contextRide.name}`
      nextStopShort = destShort
    } else {
      navInstruction = simActive
        ? `Pickup ${contextRide.name} at ${contextRide.pickup}`
        : `Preview: ${contextRide.name} · ${contextRide.pickup} → ${contextRide.dest}`
      nextStopLabel = `${String(contextRide.pickup).split(',')[0]}${contextRide.stopOrder ? ` · Stop ${contextRide.stopOrder}` : ''}`
      nextStopShort = destShort
    }
  } else {
    const bC = demoBoardSeg[103] / 11
    const bB = demoBoardSeg[102] / 11
    const bA = demoBoardSeg[101] / 11
    if (simProgress >= 10 / 11) { nextStopLabel = 'MG Road Metro · Ananya'; nextStopShort = 'MG Road' }
    else if (simProgress >= 9 / 11) { nextStopLabel = 'Brigade Rd · Priya'; nextStopShort = 'Brigade Rd' }
    else if (simProgress >= bA) { nextStopLabel = 'Church St · Rohan'; nextStopShort = 'Church St' }
    else if (simProgress >= bB) { nextStopLabel = 'Stop A · Ananya boarding'; nextStopShort = 'Stop A' }
    else if (simProgress >= bC) { nextStopLabel = 'Stop B · Rohan boarding'; nextStopShort = 'Stop B' }
    else { nextStopLabel = 'Stop C · Priya boarding'; nextStopShort = 'Stop C' }
    if (simProgress < bC) navInstruction = 'Head South on 100 Feet Rd towards Stop C · Priya'
    else if (simProgress < bB) navInstruction = 'Board Priya, continue South to Stop B · Rohan'
    else if (simProgress < bA) navInstruction = 'Board Rohan, continue South to Stop A · Ananya'
    else if (simProgress < 9 / 11) navInstruction = 'All aboard — head West on Trinity Corridor towards Church Street'
    else if (simProgress < 10 / 11) navInstruction = 'Drop Rohan, continue to Brigade Road Junction'
    else navInstruction = 'Final leg: arriving MG Road Metro Station'
  }
  const ManeuverIcon = simProgress > 0.3 && simProgress < 0.7 && !contextRide ? CornerUpRight : ArrowUp
  const kmLeft = (Math.round((1 - simProgress) * totalKm * 10) / 10).toFixed(1)

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* Turn-by-Turn Navigation HUD */}
      <div className="z-10 flex shrink-0 flex-wrap items-center gap-3 border-b bg-card px-3 py-2.5 md:px-5">
        <Button variant="ghost" size="sm" onClick={onBack} className="gap-1.5">
          <ArrowLeft className="h-4 w-4" /> Back
        </Button>

        <div className="flex min-w-0 flex-1 items-center gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow">
            <ManeuverIcon className="h-4.5 w-4.5" size={18} />
          </span>
          <div className="min-w-0">
            <p className="truncate text-[13px] font-bold">{navInstruction}</p>
            <p className="truncate text-xs text-muted-foreground">
              {simActive ? `${simSpeed} km/h · ${kmLeft} km to destination` : 'Ready to start driving'}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button size="sm" onClick={onToggleSim} className="gap-1.5">
            {simActive ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
            {simActive ? 'Pause drive' : 'Start GPS drive'}
          </Button>
          <Button size="sm" variant="outline" onClick={onUpdateLoc} disabled={updating} className="gap-1.5">
            {updating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <LocateFixed className="h-3.5 w-3.5" />}
            {updating ? 'Updating…' : 'Real GPS'}
          </Button>
        </div>

        <div className="h-1 w-full overflow-hidden rounded-full bg-secondary" role="progressbar" aria-valuenow={Math.round(simProgress * 100)} aria-valuemin={0} aria-valuemax={100} aria-label="Route progress">
          <div className="h-full rounded-full bg-primary transition-[width] duration-150" style={{ width: `${Math.round(simProgress * 100)}%` }} />
        </div>
      </div>

      {/* Map */}
      <div className="relative min-h-[420px] min-w-0 flex-1">
        {runRide && (simActive || simProgress > 0) ? (
          <div className="absolute left-3 top-3 z-[500] flex max-w-[calc(100%-24px)] flex-wrap items-center gap-2 rounded-lg border bg-card/95 px-3 py-2 shadow backdrop-blur">
            <Badge className="gap-1">
              <MapPin className="h-3 w-3" />
              Driving {runRide.stopOrder ? `stop ${runRide.stopOrder}` : 'ride'} · {runRide.name} · {Math.round(simProgress * 100)}%
            </Badge>
            <span className="max-w-[420px] truncate text-xs text-muted-foreground">
              {runRide.pickup} → {runRide.dest}
            </span>
            {!simActive && simProgress > 0 && (
              <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={onResetSim}>
                Discard & reset
              </Button>
            )}
          </div>
        ) : previewRide && (
          <div className="absolute left-3 top-3 z-[500] flex max-w-[calc(100%-24px)] flex-wrap items-center gap-2 rounded-lg border bg-card/95 px-3 py-2 shadow backdrop-blur">
            <Badge className="gap-1">
              <MapPin className="h-3 w-3" />
              {previewRide.stopOrder ? `Previewing stop ${previewRide.stopOrder}` : 'Previewing ride'} · {previewRide.name}
            </Badge>
            <span className="max-w-[420px] truncate text-xs text-muted-foreground">
              {previewRide.pickup} → {previewRide.dest}
            </span>
            <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={onClearPreview}>
              Show full pooled route
            </Button>
          </div>
        )}
        <AppMap
          center={mapCenter}
          zoom={mapZoom}
          height="100%"
          vehicles={[vehicle]}
          routeGeometry={activePath}
          waypoints={waypoints}
          followCamera={simActive}
          vehicleMotion="direct"
        />

        {/* Floating telemetry HUD */}
        <Card className="absolute bottom-4 left-4 z-[500] border-white/10 bg-slate-950/85 text-slate-100 shadow-xl backdrop-blur-md dark:bg-slate-950/85">
          <CardContent className="flex items-center gap-4 p-3.5">
            <div>
              <p className="flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider text-slate-400">
                <Gauge className="h-3 w-3" /> Speed
              </p>
              <p className="font-display text-2xl font-extrabold text-teal-300">
                {simActive ? simSpeed : 0} <span className="text-xs font-semibold">km/h</span>
              </p>
            </div>
            <div className="h-9 w-px bg-white/15" />
            <div className="min-w-0">
              <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Next stop</p>
              <p className="truncate text-xs font-bold">
                {nextStopLabel}
              </p>
              <p className="mt-0.5 flex items-center gap-1 text-[11px] text-slate-400">
                <Clock className="h-3 w-3" /> {simActive ? `~${kmLeft} km to ${nextStopShort} · ${simSpeed} km/h` : 'Awaiting start'}
              </p>
            </div>
          </CardContent>
        </Card>

        <Badge variant="secondary" className="absolute right-3 top-3 z-[500] gap-1.5 shadow">
          <span className={cn('h-2 w-2 rounded-full', simActive ? 'animate-pulse bg-emerald-500' : 'bg-muted-foreground')} />
          {vehicle.license_plate} · {simActive ? 'en route' : 'idle'}
        </Badge>
      </div>
    </div>
  )
}

// ─── Routes View ──────────────────────────────────────────────────────────────
function RoutesView({ routes, loading, onBack, onStartNav }) {
  const [selectedId, setSelectedId] = useState(null)

  const list = routes?.length ? routes : []
  const activeRoute = list.find((r) => (r.id ?? r.route_id) === selectedId) || list[0] || null
  const stopCount = activeRoute?.waypoints?.length || 5

  return (
    <div className="mx-auto w-full max-w-5xl space-y-5 p-4 md:p-7">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={onBack} className="gap-1.5">
            <ArrowLeft className="h-4 w-4" /> Back
          </Button>
          <div>
            <h1 className="font-display text-lg font-extrabold tracking-tight md:text-xl">My Assigned Routes</h1>
            <p className="text-xs text-muted-foreground">Optimized multi-stop plan for this shift</p>
          </div>
        </div>
        <Button size="sm" onClick={onStartNav} className="gap-1.5">
          <Navigation className="h-3.5 w-3.5" /> Start Navigation
        </Button>
      </div>

      <div className="grid gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
        <div className="space-y-2">
          {loading ? (
            [0, 1].map((i) => <div key={i} className="h-[92px] animate-pulse rounded-xl bg-muted/60" />)
          ) : list.length === 0 ? (
            <Card className="border-primary/30">
              <CardContent className="space-y-1.5 p-4">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-[13px] font-bold">Indiranagar → MG Road Multi-Stop</p>
                  <Badge>Active route</Badge>
                </div>
                <p className="text-xs text-muted-foreground">Vehicle KA-01-TEST-99 · 4.2 km · 3 pickups + 3 drops</p>
                <p className="text-[11px] text-muted-foreground">Optimized by OR-Tools CVRP</p>
                <p className="pt-1 text-[11px] text-muted-foreground">Demo preview — run optimization to generate live routes.</p>
              </CardContent>
            </Card>
          ) : (
            list.map((r) => {
              const id = r.id ?? r.route_id
              const isActive = (activeRoute?.id ?? activeRoute?.route_id) === id
              return (
                <button
                  key={id}
                  onClick={() => setSelectedId(id)}
                  className={cn(
                    'w-full rounded-xl border bg-card p-4 text-left shadow-sm transition-colors hover:border-primary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                    isActive ? 'border-primary/50 ring-1 ring-primary/30' : 'border-border',
                  )}
                >
                  <div className="mb-1 flex items-center justify-between gap-2">
                    <p className="truncate font-mono text-xs font-bold">{String(r.route_id || `route-${id}`).slice(0, 28)}</p>
                    {isActive ? <Badge>Active</Badge> : <StatusBadge status={r.status || 'assigned'} />}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Vehicle #{r.vehicle_id ?? '—'} · {r.total_distance_meters ? `${(r.total_distance_meters / 1000).toFixed(2)} km` : '4.2 km'} · {r.waypoints?.length || 3} stops
                  </p>
                </button>
              )
            })
          )}
        </div>

        {/* Route Detail Map Preview */}
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between gap-2">
              <div>
                <CardTitle className="text-sm">Route Map & Waypoints</CardTitle>
                <CardDescription>{stopCount} stops · live traffic aware</CardDescription>
              </div>
              <Badge variant="secondary" className="gap-1"><RouteIcon className="h-3 w-3" /> {stopCount} stops</Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="h-[260px] overflow-hidden rounded-lg border">
              <AppMap
                center={[12.9756, 77.6250]}
                zoom={13}
                height="100%"
                routeGeometry={DEMO_PRESETS.indiranagar.roadPath}
                waypoints={activeRoute?.waypoints || [
                  { lat: 12.9784, lng: 77.6408, waypoint_type: 'depot', label: 'Depot' },
                  { lat: 12.97650, lng: 77.64100, waypoint_type: 'pickup', label: 'Stop C · Priya' },
                  { lat: 12.97400, lng: 77.64110, waypoint_type: 'pickup', label: 'Stop B · Rohan' },
                  { lat: 12.97190, lng: 77.64124, waypoint_type: 'pickup', label: 'Stop A · Ananya' },
                  { lat: 12.9756, lng: 77.6066, waypoint_type: 'destination', label: 'MG Road' },
                ]}
              />
            </div>
            <div className="space-y-0">
              {['Depot · Indiranagar Hub', 'Board Priya · Stop C (100 Feet Rd)', 'Board Rohan · Stop B (100 Feet Rd)', 'Board Ananya · Stop A (100 Feet Rd)', 'Drop Rohan · Church Street', 'Drop Priya · Brigade Road', 'Drop Ananya · MG Road Metro'].map((label, i, arr) => (
                <div key={label} className="flex gap-3">
                  <div className="flex flex-col items-center">
                    <span className={cn('mt-1 h-2.5 w-2.5 rounded-full', i === 0 ? 'bg-sky-500' : i === arr.length - 1 ? 'bg-rose-500' : 'bg-primary')} />
                    {i < arr.length - 1 && <span className="w-px flex-1 bg-border" />}
                  </div>
                  <p className="pb-3 text-xs font-medium">{label}</p>
                </div>
              ))}
            </div>
            <Button className="w-full gap-1.5" onClick={onStartNav}>
              <Play className="h-4 w-4" /> Launch Interactive Simulation
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

const STATUS_STYLES = {
  completed: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400',
  in_progress: 'border-teal-500/30 bg-teal-500/10 text-teal-600 dark:text-teal-300',
  arriving: 'border-teal-500/30 bg-teal-500/10 text-teal-600 dark:text-teal-300',
  assigned: 'border-sky-500/30 bg-sky-500/10 text-sky-600 dark:text-sky-400',
  active: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400',
  en_route: 'border-sky-500/30 bg-sky-500/10 text-sky-600 dark:text-sky-400',
  idle: 'border-slate-500/30 bg-slate-500/10 text-slate-500 dark:text-slate-400',
  pending: 'border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400',
  clustered: 'border-violet-500/30 bg-violet-500/10 text-violet-600 dark:text-violet-400',
  cancelled: 'border-rose-500/30 bg-rose-500/10 text-rose-600 dark:text-rose-400',
  offline: 'border-rose-500/30 bg-rose-500/10 text-rose-600 dark:text-rose-400',
}

function StatusBadge({ status }) {
  const key = status || 'pending'
  return (
    <Badge variant="outline" className={cn('shrink-0 uppercase tracking-wide', STATUS_STYLES[key] || STATUS_STYLES.pending)}>
      {String(key).replace(/_/g, ' ')}
    </Badge>
  )
}

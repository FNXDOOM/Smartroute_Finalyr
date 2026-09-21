import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import {
  ArrowLeft, ArrowUp, BatteryCharging, BellRing, CarFront, Check,
  CircleDot, Clock, CornerUpRight, Flag, Gauge, Inbox, Loader2, LocateFixed, MapPin,
  Navigation, Pause, Play, RefreshCw, Route as RouteIcon, Satellite, Users, X,
} from 'lucide-react'
import { authApi, ridesApi, trackingApi, routeApi, vehiclesApi, createTrackingWS } from '../services/api.js'
import { useAuth } from '@clerk/clerk-react'
import AppMap from '../components/AppMapLazy'
import { DEMO_PRESETS } from '../config/demoPresets.js'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Separator } from '@/components/ui/separator'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { MapLegend } from '@/components/dashboard-shared'

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
const EMPTY_WAYPOINTS = []

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

// Demo rider board segments on pooled path.
const demoBoardSeg = Object.fromEntries(
  DEMO_RIDES.map((r) => [r.id, nearestSegIndex(r.plng, r.plat, FULL_PATH)]),
)

// Per-ride path truncated for distinct previews.
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

function pathForRoute(route) {
  if (route?.geometry?.length > 1) return route.geometry
  const points = (route?.waypoints || [])
    .filter((waypoint) => waypoint?.lat != null && waypoint?.lng != null)
    .map((waypoint) => [waypoint.lng, waypoint.lat])
  return points.length > 1 ? points : []
}

export default function DriverView({ user, view, setView, toast }) {
  const { getToken } = useAuth()
  const [vehicles,   setVehicles]   = useState([])
  const [rides,      setRides]      = useState([])
  const [routes,     setRoutes]     = useState([])
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
  const [navRoute, setNavRoute] = useState(null)
  const simTimerRef = useRef(null)
  const simFiredRef = useRef(new Set())
  const simPathRef = useRef(null)
  const knownPendingRef = useRef(new Set())
  const knownRideStatusRef = useRef(new Map())
  const pollInitRef = useRef(false)
  const wsRef = useRef(null)

  const loadData = useCallback(async () => {
    try {
      // Load all rides; driver needs incoming and active.
      const [v, r, ro] = await Promise.all([vehiclesApi.list(), ridesApi.getAll({ limit: 50 }), routeApi.history(10)])
      const list = Array.isArray(r) ? r : []
      setVehicles(Array.isArray(v)?v:[])
      setRides(list)
      setRoutes(ro?.routes || [])
      knownPendingRef.current = new Set(list.filter((x) => ['pending', 'clustered'].includes(x.status)).map((x) => x.id))
      knownRideStatusRef.current = new Map(list.map((x) => [x.id, x.status]))
      pollInitRef.current = true
      if (Array.isArray(v) && v.length) setMyVehicle(v[0])
    } catch(e) { toast('error','Failed to load data', e?.response?.data?.detail||'') }
    setLoading(false)
  }, [toast])

// Poll rides so new requests appear in Incoming.
  const refreshRides = useCallback(async () => {
    try {
      const r = await ridesApi.getAll({ limit: 50 })
      const list = Array.isArray(r) ? r : []
      if (!pollInitRef.current) {
        knownPendingRef.current = new Set(list.filter((x) => ['pending', 'clustered'].includes(x.status)).map((x) => x.id))
        pollInitRef.current = true
      } else {
        const current = new Set()
        list.forEach((x) => {
          const previousStatus = knownRideStatusRef.current.get(x.id)
          if (x.is_shared && x.status === 'ready_for_pickup' && previousStatus !== 'ready_for_pickup') {
            toast('info', 'Passenger ready', `Ride #${x.id} is waiting at the assigned pickup stop.`)
          }
          knownRideStatusRef.current.set(x.id, x.status)
          if (!['pending', 'clustered'].includes(x.status)) return
          current.add(x.id)
          if (!knownPendingRef.current.has(x.id)) {
            toast('info', 'New ride request', `${x.pickup_label || 'Pickup'} → ${x.destination_label || 'Destination'}`)
          }
        })
        knownPendingRef.current = current
      }
      setRides(list)
    } catch { /* keep the last good list; next tick retries */ }
  }, [toast])

  const refreshRoutes = useCallback(async () => {
    try {
      const result = await routeApi.history(10)
      setRoutes(result?.routes || [])
    } catch { /* keep the last good route plan; next tick retries */ }
  }, [])

  const currentDriverRoute = myVehicle?.id
    ? routes.find((route) => route.route_id === myVehicle.assigned_route_id && route.status === 'solved' && route.route_metadata?.carpool_run_status !== 'completed')
      || routes.find((route) => route.vehicle_id === myVehicle.id && route.status === 'solved' && route.route_metadata?.carpool_run_status !== 'completed')
      || null
    : null

  useEffect(() => { const timer = setTimeout(() => { void loadData() }, 0); return () => clearTimeout(timer) }, [loadData])

  // Presence is the dispatch availability signal. An idle vehicle whose
  // driver has closed the app must not receive new automatic routes.
  useEffect(() => {
    let stopped = false
    const beat = () => { if (!stopped) void authApi.driverPresence().catch(() => {}) }
    beat()
    const timer = setInterval(beat, 30000)
    return () => { stopped = true; clearInterval(timer) }
  }, [])

  useEffect(() => {
    if (!['driver-home', 'driver-map', 'driver-carpool'].includes(view) || loading) return undefined
    const id = setInterval(() => {
      void refreshRides()
      void refreshRoutes()
    }, 6000)
    return () => clearInterval(id)
  }, [view, loading, refreshRides, refreshRoutes])

  // Live tracking WebSocket
  useEffect(() => {
    let dead = false
    const connect = async () => {
      try {
        const token = await getToken()
        if (!token || dead) return
        wsRef.current = createTrackingWS(token, (msg) => {
          if (dead) return
          // Only track driver's own vehicle.
          if (msg.type === 'vehicle_location_update' && msg.vehicle) {
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
      setMyVehicle((prev) => prev ? {
        ...prev,
        lat: position.coords.latitude,
        lng: position.coords.longitude,
      } : prev)
      toast('success','Location updated')
    } catch(e) { toast('error','Failed to update',e?.response?.data?.detail||''); setUpdatingLoc(false) }
    finally { setUpdatingLoc(false) }
  }

  const updateRideStatus = async (rideId, status) => {
    try {
      await ridesApi.updateStatus(rideId, status)
      setRides(prev => prev.map(r => r.id===rideId ? {...r, status} : r))
      // Trip over: free driver's vehicle.
      if ((status === 'completed' || status === 'cancelled') && myVehicle) {
        try {
          await vehiclesApi.update(myVehicle.id, { status: 'idle' })
          setMyVehicle((prev) => (prev ? { ...prev, status: 'idle' } : prev))
        } catch { /* non-fatal: vehicle keeps its last status */ }
      }
      toast('success', `Ride #${rideId} → ${status.replace(/_/g, ' ')}`)
    } catch(e) { toast('error','Failed', e?.response?.data?.detail||'') }
  }

// Accept ride: activate vehicle, notify passenger.
  const acceptRide = async (rideId) => {
    if (myVehicle) {
      try {
        await vehiclesApi.update(myVehicle.id, { status: 'active' })
        setMyVehicle((prev) => (prev ? { ...prev, status: 'active' } : prev))
      } catch { /* accepting still proceeds without the vehicle flip */ }
    }
    try {
      await ridesApi.updateStatus(rideId, 'assigned')
      setRides((prev) => prev.map((r) => (r.id === rideId ? { ...r, status: 'assigned' } : r)))
      toast('success', `Ride #${rideId} accepted`, myVehicle ? `Passenger notified · ${myVehicle.license_plate} is on the way` : 'Passenger notified')
    } catch(e) { toast('error','Could not accept', e?.response?.data?.detail||'') }
  }

  const declineRide = async (rideId) => {
    try {
      await ridesApi.updateStatus(rideId, 'cancelled')
      setRides((prev) => prev.map((r) => (r.id === rideId ? { ...r, status: 'cancelled' } : r)))
      toast('info', `Ride #${rideId} declined`, 'The passenger was notified')
    } catch(e) { toast('error','Could not decline', e?.response?.data?.detail||'') }
  }

// Drive simulation for previewed or full route.
  const toggleDriveSimulation = (overrideRide, overrideRoute) => {
    if (simActive) {
      if (simTimerRef.current) clearInterval(simTimerRef.current)
      setSimActive(false)
      setSimSpeed(0)
      toast('info', 'GPS Simulation Paused')
      return
    }

    const resolvedRide = overrideRide !== undefined ? overrideRide : previewRide
    const resolvedRoute = overrideRoute !== undefined ? overrideRoute : navRoute
    // Restart when switching ride or persisted route context.
    const switchingContext = (resolvedRide?.id ?? null) !== (runRide?.id ?? (simPathRef.current?.rideId ?? null))
      || (resolvedRoute?.id ?? null) !== (simPathRef.current?.routeId ?? null)
    let p = simProgress >= 1 || (switchingContext && simProgress > 0) ? 0 : simProgress
    let path
    if (p === 0) {
      if (!resolvedRoute && !resolvedRide) {
        toast('info', 'No assigned route', 'Optimize and assign a route before starting navigation.')
        return
      }
      path = resolvedRoute ? pathForRoute(resolvedRoute) : pathForRide(resolvedRide)
      if (path.length < 2) {
        toast('info', 'No assigned route', 'Optimize and assign a route before starting navigation.')
        return
      }
      simPathRef.current = { path, rideId: resolvedRide?.id ?? null, routeId: resolvedRoute?.id ?? null }
      setRunRide(resolvedRide ?? null)
      setNavRoute(resolvedRoute ?? null)
      simFiredRef.current = new Set()
      setSimProgress(0)
      setSimCoords([path[0][0], path[0][1]])
    } else {
      path = simPathRef.current?.path || (resolvedRoute ? pathForRoute(resolvedRoute) : pathForRide(resolvedRide))
    }
    const totalSegments = path.length - 1
    const single = !!resolvedRide && !resolvedRoute
    const boardAt = single
      ? Math.min(nearestSegIndex(resolvedRide.plng, resolvedRide.plat, path) / totalSegments, 0.9)
      : 0
    const fireOnce = (key, type, title, body) => {
      if (simFiredRef.current.has(key)) return
      simFiredRef.current.add(key)
      toast(type, title, body)
    }

    setSimActive(true)
    toast('success', single ? `Driving ${resolvedRide.name}` : 'Driver Navigation Active', single ? `${resolvedRide.pickup} → ${resolvedRide.dest}.` : resolvedRoute ? 'Following the assigned route stops.' : 'No assigned route selected.')
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
      } else if (resolvedRoute) {
        fireOnce('route-start', 'info', 'Route navigation started', 'Follow the assigned stop order on the map.')
      } else {
        // Sequential boardings at distinct pins.
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

      // Push telemetry via functional update.
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
    setNavRoute(null)
  }

  // Route history is the source of truth. A completed route is removed by
  // the API, so do not keep rendering the copy held by the map screen.
  useEffect(() => {
    if (loading || !navRoute?.route_id) return
    const stillActive = routes.some((item) => (
      item.route_id === navRoute.route_id &&
      item.status === 'solved' &&
      item.route_metadata?.carpool_run_status !== 'completed'
    ))
    if (!stillActive) {
      const timer = setTimeout(() => {
        if (simTimerRef.current) clearInterval(simTimerRef.current)
        simPathRef.current = null
        setSimActive(false)
        setSimSpeed(0)
        setSimProgress(0)
        setRunRide(null)
        setNavRoute(null)
        setView('driver-home')
        toast('info', 'Route completed', 'The live map was cleared because this route is no longer active.')
      }, 0)
      return () => clearTimeout(timer)
    }
  }, [loading, navRoute, routes, setView, toast])

// New preview restarts from depot.
  const openPreview = (ride) => {
    if (simTimerRef.current) clearInterval(simTimerRef.current)
    simPathRef.current = null
    simFiredRef.current = new Set()
    setSimActive(false)
    setSimSpeed(0)
    setSimProgress(0)
    setSimCoords([FULL_PATH[0][0], FULL_PATH[0][1]])
    setRunRide(null)
    setNavRoute(null)
    setPreviewRide(ride)
    setView('driver-map')
  }

  const openFullNav = (route = currentDriverRoute) => {
    // Discard paused single run before full drive.
    if (!simActive && runRide && simProgress > 0) resetSim()
    setPreviewRide(null)
    setNavRoute(route || null)
    setView('driver-map')
  }

  const acceptAssignedRoute = async (route) => {
    if (!route?.route_id) return false
    try {
      const accepted = await routeApi.accept(route.route_id)
      setRoutes((prev) => prev.map((item) => (
        item.route_id === route.route_id ? { ...item, ...accepted } : item
      )))
      setMyVehicle((prev) => (prev ? { ...prev, status: 'active' } : prev))
      toast('success', 'Route accepted', 'Passengers will now see the driver progressing to their stops.')
      return true
    } catch (error) {
      toast('error', 'Could not accept route', error?.response?.data?.detail || 'The route may no longer be available.')
      return false
    }
  }

  const startFullNav = async (route = currentDriverRoute) => {
    if (route && !(route.route_metadata || {}).driver_accepted) {
      const accepted = await acceptAssignedRoute(route)
      if (!accepted) return
    }
    setPreviewRide(null)
    setNavRoute(route || null)
    setView('driver-map')
    if (!simActive) toggleDriveSimulation(null, route || null)
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
         onToggleSim={() => {
           const route = navRoute || (previewRide ? null : currentDriverRoute)
           if (!simActive && route) void startFullNav(route)
           else toggleDriveSimulation(undefined, route)
         }}
         previewRide={previewRide}
         runRide={runRide}
         route={navRoute || (previewRide ? null : currentDriverRoute)}
        onClearPreview={() => setPreviewRide(null)}
        onResetSim={resetSim}
      />
    )
  }

  if (view === 'driver-routes') {
    return <RoutesView routes={routes} loading={loading} onBack={()=>setView('driver-home')} onStartNav={startFullNav} />
  }

  if (view === 'driver-carpool') {
    return (
      <CarpoolRouteView
        routes={routes}
        rides={rides}
        vehicle={myVehicle}
        loading={loading}
        onBack={() => setView('driver-home')}
        onOpenMap={openFullNav}
        onAcceptRoute={acceptAssignedRoute}
        onAnnouncePickup={async (routeId, rideId) => {
          try {
            await routeApi.announceCarpoolPickup(routeId, rideId)
            await refreshRides()
            toast('success', 'Pickup announced', `Rider #${rideId} was asked to walk to the assigned stop.`)
          } catch (error) { toast('error', 'Could not notify rider', error?.response?.data?.detail || '') }
        }}
        onConfirmPickup={async (routeId, rideId) => {
          try {
            await routeApi.confirmCarpoolPickup(routeId, rideId)
            await refreshRides()
            toast('success', 'Passenger picked up', `Ride #${rideId} is now in progress.`)
          } catch (error) { toast('error', 'Could not confirm pickup', error?.response?.data?.detail || '') }
        }}
        onMarkArrived={async (routeId, rideId) => {
          try {
            await routeApi.markCarpoolArrived(routeId, rideId)
            await refreshRides()
            toast('success', 'Arrival logged', `Rider #${rideId} was told you are at the stop.`)
          } catch (error) { toast('error', 'Could not log arrival', error?.response?.data?.detail || '') }
        }}
        onDepart={async (routeId) => {
          try {
            const result = await routeApi.departCarpool(routeId)
            await refreshRides()
            toast('success', 'Trip started', `${result?.ride_ids?.length || 0} rider(s) are on the move.`)
          } catch (error) { toast('error', 'Could not start the trip', error?.response?.data?.detail || '') }
        }}
        onCompleteRun={async (routeId) => {
          try {
            await routeApi.completeCarpool(routeId)
            await refreshRides()
            await refreshRoutes()
            toast('success', 'Carpool run completed', 'Your vehicle is back in the pool.')
          } catch (error) { toast('error', 'Could not complete the run', error?.response?.data?.detail || '') }
        }}
        onConfirmDropoff={async (routeId, rideId) => {
          try {
            await routeApi.confirmCarpoolDropoff(routeId, rideId)
            await refreshRides()
            await refreshRoutes()
            toast('success', 'Passenger dropped off', `Ride #${rideId} is complete.`)
          } catch (error) { toast('error', 'Could not confirm drop-off', error?.response?.data?.detail || '') }
        }}
      />
    )
  }

  // Driver home
  const firstName = user?.name?.split(' ')[0] || 'Driver'
  const normalRides = rides.filter((r) => r.is_shared === false)
  const incoming = normalRides.filter((r) => ['pending', 'clustered'].includes(r.status))
  const activeTrips = normalRides.filter((r) => ['assigned', 'arriving', 'in_progress'].includes(r.status))
  const usingDemoManifest = rides.length === 0
  // Pooled thresholds for boardings and drops.
  const demoDropAt = { 1: 1.01, 2: 9 / 11, 3: 10 / 11 }
  const demoBoardAt = { 101: demoBoardSeg[101] / 11, 102: demoBoardSeg[102] / 11, 103: demoBoardSeg[103] / 11 }
  const runBoardAt = runRide ? Math.min(nearestSegIndex(runRide.plng, runRide.plat, pathForRide(runRide)) / (pathForRide(runRide).length - 1), 0.9) : 3 / 11
  const manifest = rides.length > 0
    ? activeTrips.slice(0, 6).map((r) => ({
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
        request_time: r.request_time,
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
            <h1 className="mob-page-title">Driver Dashboard</h1>
            <Badge variant="secondary" className="gap-1.5">
              <span className="relative flex h-2 w-2" aria-hidden="true">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-black opacity-20" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-black dark:bg-white" />
              </span>
              <span className="sr-only">Live: </span>Live dispatch
            </Badge>
          </div>
          <p className="mt-0.5 truncate text-sm text-muted-foreground">
            Welcome back, {firstName} · {myVehicle?.license_plate || 'No vehicle assigned'}
          </p>
        </div>
        {vehicles.length > 1 ? (
          <Select
            value={myVehicle ? String(myVehicle.id) : ''}
            onValueChange={(val) => {
              const next = vehicles.find((v) => String(v.id) === val)
              if (next) setMyVehicle(next)
            }}
          >
            <SelectTrigger className="w-[220px] font-mono text-xs" aria-label="Select vehicle">
              <SelectValue placeholder="Select vehicle" />
            </SelectTrigger>
            <SelectContent>
              {vehicles.map((v) => (
                <SelectItem key={v.id} value={String(v.id)}>{v.license_plate} · {v.status}</SelectItem>
              ))}
            </SelectContent>
          </Select>
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
          <StatCard icon={Inbox} label="Incoming Requests" value={String(incoming.length)} sub={incoming.length === 1 ? '1 rider waiting' : `${incoming.length} riders waiting`} />
          <StatCard icon={Users} label="Active Trips" value={String(activeTrips.length)} sub={activeTrips.length === 1 ? '1 trip in motion' : `${activeTrips.length} trips in motion`} />
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
        <div className="min-w-0 space-y-4">
        {/* Incoming requests — normal-mode passenger bookings land here live */}
        {!usingDemoManifest && (
          <Card className={cn(incoming.length > 0 && 'border-primary/40')}>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between gap-2">
                <div>
                  <CardTitle className="flex items-center gap-2 text-sm">
                    {incoming.length > 0 && (
                      <span className="relative flex h-2 w-2">
                        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary opacity-60" />
                        <span className="relative inline-flex h-2 w-2 rounded-full bg-primary" />
                      </span>
                    )}
                    Incoming Requests
                  </CardTitle>
                  <CardDescription>Accept fast — the passenger is notified instantly</CardDescription>
                </div>
                <Badge variant="secondary">{incoming.length} waiting</Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-2">
              {loading ? (
                [0, 1].map((i) => <div key={i} className="h-[104px] animate-pulse rounded-lg bg-muted/60" />)
              ) : incoming.length === 0 ? (
                <p className="rounded-lg border border-dashed px-3 py-5 text-center text-xs text-muted-foreground">
                  No waiting requests — new passenger bookings pop up here automatically.
                </p>
              ) : (
                incoming.slice(0, 5).map((r) => (
                  <div key={r.id} className="rounded-lg border border-primary/25 bg-card p-3.5 shadow-sm">
                    <div className="mb-2 flex items-center justify-between gap-2">
                      <div className="flex min-w-0 items-center gap-2">
                        <Avatar className="h-7 w-7">
                          <AvatarFallback className="bg-primary/10 text-[11px] font-bold text-primary">
                            <BellRing className="h-3.5 w-3.5" />
                          </AvatarFallback>
                        </Avatar>
                        <p className="truncate text-[13px] font-semibold">Ride #{r.id}</p>
                        {r.request_time && <span className="shrink-0 text-[11px] text-muted-foreground">{timeAgo(r.request_time)}</span>}
                      </div>
                      <StatusBadge status={r.status} />
                    </div>
                    <p className="flex items-center gap-1.5 truncate text-xs text-muted-foreground">
                      <MapPin className="h-3.5 w-3.5 shrink-0 text-primary" /> {r.pickup_label || 'Pickup stop'}
                    </p>
                    <p className="mt-1 flex items-center gap-1.5 truncate text-xs text-muted-foreground">
                      <Flag className="h-3.5 w-3.5 shrink-0 text-rose-500" /> {r.destination_label || 'Destination'}
                    </p>
                    <div className="mt-2.5 flex gap-2">
                      {r.is_shared ? (
                        <div className="flex flex-1 items-center rounded-md bg-primary/10 px-3 text-[11px] font-semibold text-primary">
                          <Users className="mr-1.5 h-3.5 w-3.5" /> Waiting for a compatible carpool route
                        </div>
                      ) : (
                        <Button size="sm" className="h-8 flex-1 gap-1.5" onClick={() => acceptRide(r.id)}>
                          <Check className="h-3.5 w-3.5" /> Accept ride
                        </Button>
                      )}
                      <Button size="sm" variant="ghost" className="h-8 gap-1 text-destructive hover:text-destructive" onClick={() => declineRide(r.id)}>
                        <X className="h-3.5 w-3.5" /> Decline
                      </Button>
                    </div>
                  </div>
                ))
              )}
            </CardContent>
          </Card>
        )}
        {/* Active trips */}
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between gap-2">
              <div>
                <CardTitle className="text-sm">{usingDemoManifest ? 'Passenger Manifest' : 'My Active Trips'}</CardTitle>
                <CardDescription>{usingDemoManifest ? 'Board and drop off in stop order' : 'Drive each stage — the passenger follows along live'}</CardDescription>
              </div>
              <Badge variant="secondary">{usingDemoManifest ? `${manifest.length} pooled · demo` : `${manifest.length} active`}</Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-2">
            {loading ? (
              [0, 1, 2].map((i) => <div key={i} className="h-[104px] animate-pulse rounded-lg bg-muted/60" />)
            ) : manifest.length === 0 ? (
              <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed py-10 text-center">
                <CircleDot className="h-6 w-6 text-muted-foreground" />
                <p className="text-sm font-semibold">No active trips</p>
                <p className="max-w-[260px] text-xs text-muted-foreground">Accepted requests appear here — drive them stage by stage.</p>
              </div>
            ) : (
              manifest.map((ride) => (
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
                    <div className="mt-2.5 flex flex-wrap gap-2">
                      {(DRIVER_NEXT[ride.status] || []).map(({ status, label, variant, Icon }) => (
                        <Button key={status} size="sm" variant={variant} className="h-8 flex-1 gap-1.5" onClick={() => updateRideStatus(ride.id, status)}>
                          <Icon className="h-3.5 w-3.5" /> {label}
                        </Button>
                      ))}
                      <Button size="sm" variant="ghost" className="h-8 gap-1 text-destructive hover:text-destructive" onClick={() => updateRideStatus(ride.id, 'cancelled')}>
                        <X className="h-3.5 w-3.5" /> Cancel
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
        </div>

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
                    <BatteryCharging className="h-3.5 w-3.5 text-black dark:text-white" /> Battery / Range
                  </p>
                  <span className="text-xs font-bold text-green-700 dark:text-green-400">88%</span>
                </div>
                <div className="mt-2 h-2 overflow-hidden rounded-full bg-secondary">
                  <div className="h-full w-[88%] rounded-full bg-black dark:bg-white" />
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
        <p className="mob-data mt-2 truncate text-xl font-bold tracking-tight" title={value}>{value}</p>
        <p className="mt-0.5 truncate text-xs text-muted-foreground">{sub}</p>
      </CardContent>
    </Card>
  )
}

// Live navigation map
function LiveMapView({ myVehicle, route, onBack, onUpdateLoc, updating, simActive, simProgress, simSpeed, simCoords, simBearing, onToggleSim, previewRide, runRide, onClearPreview, onResetSim }) {
  // A persisted assigned route is the source of truth. A single ride is only
  // used for the driver's preview action.
  const contextRide = (simActive || simProgress > 0) && runRide ? runRide : previewRide
  const activePath = useMemo(() => route ? pathForRoute(route) : contextRide ? pathForRide(contextRide) : [], [route, contextRide])
  const routeWaypoints = route?.waypoints || EMPTY_WAYPOINTS
  const initialPoint = routeWaypoints[0] || null
  const vehicleLat = simActive ? simCoords[1] : (myVehicle?.lat ?? initialPoint?.lat ?? 12.9784)
  const vehicleLng = simActive ? simCoords[0] : (myVehicle?.lng ?? initialPoint?.lng ?? 77.6408)
  const vehicle = {
    id: myVehicle?.id || 99,
    license_plate: myVehicle?.license_plate || 'KA-01-TEST-99',
    status: simActive ? 'active' : (myVehicle?.status || 'idle'),
    lat: vehicleLat,
    lng: vehicleLng,
    bearing: simActive ? simBearing : (myVehicle?.bearing || 0),
  }

  const waypoints = useMemo(() => (
    routeWaypoints.length
      ? routeWaypoints
      : contextRide?.plat != null && contextRide?.dlat != null
      ? [
          { lat: 12.9784, lng: 77.6408, waypoint_type: 'depot', label: 'Depot' },
          { lat: contextRide.plat, lng: contextRide.plng, waypoint_type: 'pickup', label: `${contextRide.name} pickup` },
          { lat: contextRide.dlat, lng: contextRide.dlng, waypoint_type: 'destination', label: `${contextRide.name} dropoff` },
        ]
      : []
  ), [contextRide, routeWaypoints])

  // Center on the real vehicle; AppMap fits the persisted route when idle.
  const mapCenter = [vehicleLat, vehicleLng]
  const mapZoom = route ? 13.5 : contextRide && !simActive ? 14.5 : 14

  const boardAt = contextRide?.plat != null && activePath.length > 1
    ? Math.min(nearestSegIndex(contextRide.plng, contextRide.plat, activePath) / (activePath.length - 1), 0.9)
    : 0
  const totalKm = contextRide?.stopOrder === 2 ? 3.6 : contextRide?.stopOrder === 3 ? 3.9 : 4.2
  let navInstruction
  let nextStopLabel
  let nextStopShort
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
  } else if (route) {
    const nextWaypoint = routeWaypoints[Math.min(Math.floor(simProgress * routeWaypoints.length), Math.max(0, routeWaypoints.length - 1))]
    const nextLabel = nextWaypoint?.label || `${nextWaypoint?.waypoint_type === 'pickup' ? 'Pickup' : 'Drop-off'} stop`
    navInstruction = simProgress >= 1 ? 'Assigned route completed' : `Proceed to ${nextLabel}`
    nextStopLabel = nextLabel
    nextStopShort = nextLabel
  } else {
    navInstruction = 'No assigned route'
    nextStopLabel = 'Assign a route to begin'
    nextStopShort = 'assigned route'
  }
  const ManeuverIcon = simProgress > 0.3 && simProgress < 0.7 && !contextRide ? CornerUpRight : ArrowUp
  const routeKm = route?.total_distance_meters ? route.total_distance_meters / 1000 : totalKm
  const kmLeft = (Math.round((1 - simProgress) * routeKm * 10) / 10).toFixed(1)

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
            {simActive ? 'Pause drive' : route && !(route.route_metadata || {}).driver_accepted ? 'Accept & start drive' : 'Start GPS drive'}
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
      <div className="relative min-h-[420px] min-w-0 flex-1 overflow-hidden rounded-2xl border">
          {route && (simActive || simProgress > 0) ? (
          <div className="absolute left-3 top-3 z-10 flex max-w-[calc(100%-24px)] flex-wrap items-center gap-2 rounded-lg border bg-card/95 px-3 py-2 shadow backdrop-blur">
            <Badge className="gap-1">
              <MapPin className="h-3 w-3" />
               Driving assigned route · {Math.round(simProgress * 100)}%
            </Badge>
            <span className="max-w-[420px] truncate text-xs text-muted-foreground">
               {route.waypoints?.length || 0} ordered stops · {((route.total_distance_meters || 0) / 1000).toFixed(1)} km
            </span>
            {!simActive && simProgress > 0 && (
              <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={onResetSim}>
                Discard & reset
              </Button>
            )}
          </div>
        ) : previewRide && (
          <div className="absolute left-3 top-3 z-10 flex max-w-[calc(100%-24px)] flex-wrap items-center gap-2 rounded-lg border bg-card/95 px-3 py-2 shadow backdrop-blur">
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
        <Card className="absolute bottom-4 left-4 z-10 border-border/80 bg-card/95 text-card-foreground shadow-xl backdrop-blur-md">
          <CardContent className="flex items-center gap-4 p-3.5">
            <div>
              <p className="flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                <Gauge className="h-3 w-3" /> Speed
              </p>
              <p className="mob-data text-2xl font-bold text-foreground">
                {simActive ? simSpeed : 0} <span className="text-xs font-semibold">km/h</span>
              </p>
            </div>
            <div className="h-9 w-px bg-border" />
            <div className="min-w-0">
              <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Next stop</p>
              <p className="truncate text-xs font-bold">
                {nextStopLabel}
              </p>
              <p className="mt-0.5 flex items-center gap-1 text-[11px] text-muted-foreground">
                <Clock className="h-3 w-3" /> {simActive ? `~${kmLeft} km to ${nextStopShort} · ${simSpeed} km/h` : 'Awaiting start'}
              </p>
            </div>
          </CardContent>
        </Card>

        <Badge variant="secondary" className="absolute right-3 top-3 z-10 gap-1.5 shadow">
          <span className={cn('h-2 w-2 rounded-full', simActive ? 'animate-pulse bg-black dark:bg-white' : 'bg-muted-foreground')} aria-hidden="true" />
          {vehicle.license_plate} · {simActive ? 'en route' : 'idle'}
        </Badge>
      </div>
    </div>
  )
}

// Routes view
function RoutesView({ routes, loading, onBack, onStartNav }) {
  const [selectedId, setSelectedId] = useState(null)

  const list = routes?.length ? routes : []
  const activeRoute = list.find((r) => (r.id ?? r.route_id) === selectedId) || list[0] || null
  const stopCount = activeRoute?.waypoints?.length || 0
  const routeWaypoints = activeRoute?.waypoints || []
  const routeGeometry = pathForRoute(activeRoute)
  const routeCenter = routeWaypoints[0]
    ? [routeWaypoints[0].lat, routeWaypoints[0].lng]
    : [12.9784, 77.6408]

  return (
    <div className="mx-auto w-full max-w-5xl space-y-5 p-4 md:p-7">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={onBack} className="gap-1.5">
            <ArrowLeft className="h-4 w-4" /> Back
          </Button>
          <div>
            <h1 className="mob-page-title text-lg">My Assigned Routes</h1>
            <p className="text-xs text-muted-foreground">Optimized multi-stop plan for this shift</p>
          </div>
        </div>
          <Button size="sm" onClick={() => onStartNav(activeRoute)} disabled={!activeRoute} className="gap-1.5">
          <Navigation className="h-3.5 w-3.5" /> Accept & Start Navigation
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
                  <p className="text-[13px] font-bold">No assigned routes</p>
                </div>
                <p className="text-xs text-muted-foreground">Routes will appear here after dispatch assigns one to your vehicle.</p>
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
                <CardDescription>{stopCount ? `${stopCount} stops · live route geometry` : 'No route selected'}</CardDescription>
              </div>
              <Badge variant="secondary" className="gap-1"><RouteIcon className="h-3 w-3" /> {stopCount} stops</Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="relative overflow-hidden rounded-lg border">
              <AppMap
                center={routeCenter}
                zoom={13}
                height={260}
                routeGeometry={routeGeometry}
                waypoints={routeWaypoints}
                style={{ borderRadius: 0 }}
              />
            </div>
            <MapLegend
              items={[
                { color: '#525252', label: 'Depot' },
                { color: '#111111', label: 'Pickup' },
                { color: '#545454', label: 'Drop-off' },
              ]}
            />
            <div className="space-y-0">
              {routeWaypoints.map((waypoint, i, arr) => (
                <div key={`${waypoint.sequence ?? i}-${waypoint.lat}`} className="flex gap-3">
                  <div className="flex flex-col items-center">
                    <span className={cn('mt-1 h-2.5 w-2.5 rounded-full', i === 0 ? 'bg-muted-foreground' : i === arr.length - 1 ? 'bg-black dark:bg-white' : 'bg-foreground')} />
                    {i < arr.length - 1 && <span className="w-px flex-1 bg-border" />}
                  </div>
                  <p className="pb-3 text-xs font-medium">{waypoint.label || `${waypoint.waypoint_type} · ${waypoint.lat.toFixed(5)}, ${waypoint.lng.toFixed(5)}`}</p>
                </div>
              ))}
            </div>
            <Button className="w-full gap-1.5" onClick={() => onStartNav(activeRoute)} disabled={!activeRoute}>
              <Play className="h-4 w-4" /> Launch Interactive Simulation
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

function carpoolDistanceMeters(aLat, aLng, bLat, bLng) {
  const radius = 6371000
  const lat1 = (aLat * Math.PI) / 180
  const lat2 = (bLat * Math.PI) / 180
  const dLat = lat2 - lat1
  const dLng = ((bLng - aLng) * Math.PI) / 180
  const h = Math.sin(dLat / 2) ** 2
    + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2
  return 2 * radius * Math.asin(Math.sqrt(h))
}

function CarpoolRouteView({ routes, rides, vehicle, loading, onBack, onOpenMap, onAcceptRoute, onAnnouncePickup, onMarkArrived, onConfirmPickup, onDepart, onConfirmDropoff, onCompleteRun }) {
  const route = routes?.find((item) => (
    item.vehicle_id === vehicle?.id &&
    // A co-passenger cancellation leaves the plan needing re-optimization while
    // the riders already served stay live, so the run must remain drivable.
    ['solved', 'needs_reoptimization'].includes(item.status) &&
    item.route_metadata?.carpool_run &&
    item.route_metadata?.carpool_run_status !== 'completed' &&
    (item.problem || item.route_metadata?.problem || 'pdp') === 'pdp'
  )) || null
  const waypoints = route?.waypoints || []
  const rideById = new Map((rides || []).map((ride) => [ride.id, ride]))
  const passengerIds = [...new Set(waypoints.flatMap((waypoint) => waypoint.passenger_ids || []))]
  const passengers = passengerIds
    .map((id) => rideById.get(id))
    .filter((ride) => ride && ride.status !== 'cancelled')
  const boardedCount = passengers.filter((ride) => ride.carpool_status === 'boarded').length
  const everyRiderDroppedOff = passengers.length > 0 && passengers.every((ride) => ride.status === 'completed')
  const accepted = Boolean(route?.route_metadata?.driver_accepted)
  const routeGeometry = route?.geometry?.length > 1
    ? route.geometry
    : waypoints.map((waypoint) => [waypoint.lng, waypoint.lat])
  const center = waypoints.length
    ? [
        waypoints.reduce((sum, waypoint) => sum + waypoint.lat, 0) / waypoints.length,
        waypoints.reduce((sum, waypoint) => sum + waypoint.lng, 0) / waypoints.length,
      ]
    : [12.9756, 77.625]

  return (
    <div className="mx-auto w-full max-w-6xl space-y-5 p-4 md:p-7">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <Button variant="ghost" size="sm" onClick={onBack} className="gap-1.5">
            <ArrowLeft className="h-4 w-4" /> Back
          </Button>
          <div>
            <p className="text-xs font-semibold text-primary">DRIVER ITINERARY</p>
            <h1 className="mob-page-title text-xl">Carpool run</h1>
            <p className="mt-0.5 text-sm text-muted-foreground">Stop-by-stop guidance for up to three riders.</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {boardedCount > 0 && (
            <Button variant="outline" onClick={() => onDepart(route.route_id)} className="gap-1.5">
              <Play className="h-4 w-4" /> Start trip ({boardedCount})
            </Button>
          )}
          {accepted && everyRiderDroppedOff && (
            <Button onClick={() => onCompleteRun(route.route_id)} className="gap-1.5">
              <Check className="h-4 w-4" /> Complete run
            </Button>
          )}
          <Button onClick={() => accepted ? onOpenMap(route) : onAcceptRoute(route)} className="gap-1.5" disabled={!route}>
            <Navigation className="h-4 w-4" /> {accepted ? 'Open live map' : 'Accept carpool run'}
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1.2fr)_360px]">
          <div className="h-[360px] animate-pulse rounded-2xl bg-muted" />
          <div className="h-[360px] animate-pulse rounded-2xl bg-muted" />
        </div>
      ) : !route ? (
        <Card className="border-dashed">
          <CardContent className="space-y-2 p-8 text-center">
            <Users className="mx-auto h-8 w-8 text-muted-foreground" />
            <p className="font-semibold">No active carpool run for this vehicle</p>
            <p className="mx-auto max-w-md text-sm text-muted-foreground">
              {vehicle?.license_plate
                ? `No carpool route is currently assigned to ${vehicle.license_plate}. New assignments will appear here after dispatch and driver acceptance.`
                : 'A vehicle must be assigned to this driver before carpool runs can appear here.'}
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1.2fr)_360px]">
          <Card className="overflow-hidden">
            <div className="relative h-[420px] border-b">
              <AppMap center={center} zoom={13.5} height="100%" routeGeometry={routeGeometry} waypoints={waypoints} />
              <div className="absolute left-3 top-3 flex items-center gap-2 rounded-xl border bg-card/95 px-3 py-2 shadow backdrop-blur">
                <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground"><Users className="h-4 w-4" /></span>
                <div>
                  <p className="text-xs font-bold">{passengerIds.length} / 3 passengers</p>
                  <p className="text-[11px] text-muted-foreground">{vehicle?.license_plate || 'Assigned vehicle'}</p>
                </div>
              </div>
            </div>
            <CardContent className="grid grid-cols-3 gap-3 p-4">
              <RouteMetric label="Stops" value={String(waypoints.length)} />
              <RouteMetric label="Distance" value={`${((route.total_distance_meters || 0) / 1000).toFixed(1)} km`} />
              <RouteMetric label="Mode" value="PDP" />
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">Your next stops</CardTitle>
              <CardDescription>Follow this order. Pickups are shared curb stops.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-0">
              {waypoints.map((waypoint, index) => {
                const ids = waypoint.passenger_ids || []
                const isPickup = waypoint.waypoint_type === 'pickup'
                return (
                  <div key={`${waypoint.sequence ?? index}-${waypoint.lat}`} className="flex gap-3 border-l-2 border-border pb-4 pl-4 last:pb-0">
                    <div className={cn('relative -ml-[23px] mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border-2 bg-card text-xs font-bold', isPickup ? 'border-primary text-primary' : 'border-foreground')}>
                      {index + 1}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-xs font-bold">{isPickup ? 'Pick up' : 'Drop off'}</p>
                        <Badge variant="outline" className="text-[10px]">{isPickup ? 'BOARD' : 'EXIT'}</Badge>
                      </div>
                      {ids.map((id) => {
                        const ride = rideById.get(id)
                        const walk = isPickup && ride
                          ? carpoolDistanceMeters(ride.pickup_lat, ride.pickup_lng, waypoint.lat, waypoint.lng)
                          : 0
                        return (
                          <div key={id} className="mt-1 space-y-1">
                            <p className="truncate text-sm">
                              {ride?.pickup_label || ride?.destination_label || `Rider #${id}`}
                              {isPickup && walk > 0 ? <span className="ml-1 text-xs text-muted-foreground">· walks {Math.round(walk)} m</span> : null}
                            </p>
                            {ride && <div className="flex flex-wrap items-center gap-1.5">
                              <StatusBadge status={ride.status} />
                              {isPickup && ride.status === 'assigned' && (
                                <Button size="sm" className="h-7 px-2 text-[11px]" onClick={() => onAnnouncePickup(route.route_id, id)}>Ask rider to walk</Button>
                              )}
                              {isPickup && ride.carpool_status === 'driver_arriving' && (
                                <Button size="sm" className="h-7 px-2 text-[11px]" onClick={() => onMarkArrived(route.route_id, id)}>I have arrived</Button>
                              )}
                              {isPickup && ride.status === 'arriving' && ride.carpool_status !== 'driver_arriving' && (
                                <span className="text-[11px] text-muted-foreground">Waiting for rider confirmation</span>
                              )}
                              {isPickup && ride.status === 'ready_for_pickup' && (
                                <Button size="sm" className="h-7 px-2 text-[11px]" onClick={() => onConfirmPickup(route.route_id, id)}>Confirm pickup</Button>
                              )}
                              {!isPickup && ride.status === 'in_progress' && (
                                <Button size="sm" className="h-7 px-2 text-[11px]" onClick={() => onConfirmDropoff(route.route_id, id)}>Confirm drop-off</Button>
                              )}
                            </div>}
                          </div>
                        )
                      })}
                      <p className="mt-0.5 text-[11px] text-muted-foreground">{waypoint.lat.toFixed(5)}, {waypoint.lng.toFixed(5)}</p>
                    </div>
                  </div>
                )
              })}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}

function RouteMetric({ label, value }) {
  return <div className="rounded-lg bg-muted/60 p-3"><p className="text-[10px] font-semibold text-muted-foreground">{label}</p><p className="mt-1 text-sm font-bold">{value}</p></div>
}

const STATUS_STYLES = {
  completed: 'border-[#276EF1]/25 bg-[#276EF1]/10 text-[#276EF1]',
  in_progress: 'border-foreground/30 bg-foreground text-background',
  arriving: 'border-foreground/30 bg-foreground text-background',
  ready_for_pickup: 'border-[#276EF1]/25 bg-[#276EF1]/10 text-[#276EF1]',
  assigned: 'border-foreground/30 bg-foreground text-background',
  active: 'border-[#276EF1]/25 bg-[#276EF1]/10 text-[#276EF1]',
  en_route: 'border-foreground/30 bg-foreground text-background',
  idle: 'border-border bg-muted text-muted-foreground',
  pending: 'border-border bg-muted text-foreground',
  clustered: 'border-border bg-muted text-foreground',
  cancelled: 'border-destructive/30 bg-destructive/10 text-destructive',
  offline: 'border-destructive/30 bg-destructive/10 text-destructive',
}

function StatusBadge({ status }) {
  const key = status || 'pending'
  return (
    <Badge variant="outline" className={cn('shrink-0 uppercase tracking-wide', STATUS_STYLES[key] || STATUS_STYLES.pending)}>
      {String(key).replace(/_/g, ' ')}
    </Badge>
  )
}

// Stage buttons advance trip, notify passenger.
const DRIVER_NEXT = {
  assigned: [
    { status: 'arriving', label: 'Arrived at pickup', variant: 'secondary', Icon: MapPin },
    { status: 'in_progress', label: 'Start trip', variant: 'default', Icon: Play },
  ],
  arriving: [
    { status: 'in_progress', label: 'Start trip', variant: 'default', Icon: Play },
  ],
  in_progress: [
    { status: 'completed', label: 'Complete dropoff', variant: 'default', Icon: Check },
  ],
}

function timeAgo(ts) {
  if (!ts) return ''
  const s = Math.max(0, Math.round((Date.now() - new Date(ts).getTime()) / 1000))
  if (s < 60) return 'just now'
  const m = Math.floor(s / 60)
  if (m < 60) return `${m} min ago`
  return `${Math.floor(m / 60)} hr ago`
}

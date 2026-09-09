import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import {
  CarFront, CheckCircle2, ChevronRight, CircleDot, Dna, Flag, Loader2,
  MapPin, Navigation, Pause, Play, RotateCcw, Signpost,
  Users, Zap,
} from 'lucide-react'
import { ridesApi, jobsApi, geocodeApi, routingApi } from '../services/api.js'
import AppMap from '../components/AppMap'
import { DEMO_PRESETS, DEMO_STAGES, createDemoRunId } from '../config/demoPresets.js'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Switch } from '@/components/ui/switch'
import { Progress } from '@/components/ui/progress'
import { ScrollArea } from '@/components/ui/scroll-area'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { MapLegend, KpiStat } from '@/components/dashboard-shared'

// Stage icons for pipeline.
const STAGE_ICONS = { SPAWN: Users, CLUSTER: Dna, VIRTUAL_STOP: Signpost, VRP_SOLVE: Zap, DRIVE_SIM: CarFront }

function interpolateDemoPath(path, progress) {
  const segmentLengths = []
  let totalLength = 0
  for (let index = 1; index < path.length; index += 1) {
    const [fromLng, fromLat] = path[index - 1]
    const [toLng, toLat] = path[index]
    const eastWest = (toLng - fromLng) * Math.cos((fromLat * Math.PI) / 180)
    const northSouth = toLat - fromLat
    const length = Math.hypot(eastWest, northSouth)
    segmentLengths.push(length)
    totalLength += length
  }
  if (!totalLength) return { position: path[0], bearing: 0 }

  let distance = totalLength * Math.max(0, Math.min(1, progress))
  for (let index = 0; index < segmentLengths.length; index += 1) {
    const segmentLength = segmentLengths[index]
    if (distance <= segmentLength) {
      const ratio = segmentLength ? distance / segmentLength : 0
      const [fromLng, fromLat] = path[index]
      const [toLng, toLat] = path[index + 1]
      return {
        position: [fromLng + (toLng - fromLng) * ratio, fromLat + (toLat - fromLat) * ratio],
        bearing: (Math.atan2((toLng - fromLng) * Math.cos((fromLat * Math.PI) / 180), toLat - fromLat) * 180) / Math.PI,
      }
    }
    distance -= segmentLength
  }
  return { position: path[path.length - 1], bearing: 0 }
}

function nearestPathProgress(path, point) {
  if (!path.length) return 0
  let bestIndex = 0
  let bestDistance = Number.POSITIVE_INFINITY
  path.forEach(([lng, lat], index) => {
    const distance = Math.hypot((lng - point.lng) * Math.cos((point.lat * Math.PI) / 180), lat - point.lat)
    if (distance < bestDistance) {
      bestDistance = distance
      bestIndex = index
    }
  })
  return bestIndex / Math.max(1, path.length - 1)
}

function pointAtDemoProgress(path, progress) {
  return interpolateDemoPath(path, progress).position
}

function nearbyHome(stop, direction) {
  const walkMeters = 150
  const latDelta = walkMeters / 111320
  const lngDelta = walkMeters / (111320 * Math.max(0.2, Math.cos((stop.lat * Math.PI) / 180)))
  return direction === 'north'
    ? { lat: stop.lat + latDelta, lng: stop.lng, label: 'TC Palya residence' }
    : { lat: stop.lat, lng: stop.lng - lngDelta, label: 'Near-route residence' }
}

function buildSharedPassengers(path, pickup, destination, baseRiders) {
  const firstPickupProgress = Math.max(0.12, Math.min(0.45, nearestPathProgress(path, pickup)))
  const secondPickupProgress = Math.min(0.72, Math.max(0.5, firstPickupProgress + 0.18))
  const thirdPickupProgress = Math.min(0.86, Math.max(0.68, secondPickupProgress + 0.16))
  const stops = [
    { progress: firstPickupProgress, stop: pickup, home: pickup, walkDistanceM: 0, homeLabel: pickup.label, stopLabel: `${pickup.label} boarding point` },
    { progress: secondPickupProgress, stop: (() => { const [lng, lat] = pointAtDemoProgress(path, secondPickupProgress); return { lat, lng } })(), home: null, walkDistanceM: 150, homeLabel: 'TC Palya residence', stopLabel: 'TC Palya Main Road Virtual Stop' },
    { progress: thirdPickupProgress, stop: (() => { const [lng, lat] = pointAtDemoProgress(path, thirdPickupProgress); return { lat, lng } })(), home: null, walkDistanceM: 150, homeLabel: 'Near-route residence', stopLabel: 'Route Stop #3 Virtual Stop' },
  ]
  stops[1].home = nearbyHome(stops[1].stop, 'north')
  stops[2].home = nearbyHome(stops[2].stop, 'west')

  return baseRiders.slice(0, 3).map((rider, index) => {
    const assignment = stops[index]
    return {
      ...rider,
      plat: assignment.home.lat,
      plng: assignment.home.lng,
      plbl: assignment.homeLabel,
      dlat: destination.lat,
      dlng: destination.lng,
      dlbl: destination.label,
      homeLabel: assignment.homeLabel,
      virtualStop: { ...assignment.stop, label: assignment.stopLabel },
      pickupProgress: assignment.progress,
      walkDistanceM: assignment.walkDistanceM,
      walkingPath: assignment.walkDistanceM > 0
        ? [[assignment.home.lng, assignment.home.lat], [assignment.stop.lng, assignment.stop.lat]]
        : [],
      riderNumber: index + 1,
    }
  })
}

const riderStatusLabels = {
  requested: 'Requested',
  clustered: 'Matched to route',
  assigned: 'Route assigned',
  walking_to_stop: 'Walking to stop',
  boarding: 'Boarding',
  in_vehicle: 'In shared auto',
  completed: 'Dropped off',
}

function buildSharedWaypoints(scenario, depot, destination) {
  return [
    { lat: depot.lat, lng: depot.lng, waypoint_type: 'depot', label: 'Depot', marker_label: '🏢' },
    ...scenario.flatMap(rider => [
      { ...rider.virtualStop, waypoint_type: 'pickup', label: `P${rider.riderNumber} · ${rider.virtualStop.label}`, marker_label: `P${rider.riderNumber}` },
      ...(rider.walkDistanceM > 0
        ? [{ lat: rider.plat, lng: rider.plng, waypoint_type: 'rider_home', label: `P${rider.riderNumber} home · ${rider.homeLabel}`, marker_label: '🏠' }]
        : []),
    ]),
    { lat: destination.lat, lng: destination.lng, waypoint_type: 'destination', label: destination.label, marker_label: '★' },
  ]
}

export default function PresentationDemoView({ toast }) {
  const [selectedZone, setSelectedZone] = useState('indiranagar')
  const [currentStage, setCurrentStage] = useState(0)
  const [isPlaying, setIsPlaying] = useState(false)
  const [speedMultiplier, setSpeedMultiplier] = useState(1)
  // Keep map still; Follow tracks the auto.
  const [followCamera, setFollowCamera] = useState(false)

  const activePreset = DEMO_PRESETS[selectedZone] || DEMO_PRESETS.indiranagar
  const defaultPickup = {
    lat: activePreset.riders[0].plat,
    lng: activePreset.riders[0].plng,
    label: activePreset.riders[0].plbl,
  }
  const defaultDestination = {
    lat: activePreset.riders[0].dlat,
    lng: activePreset.riders[0].dlng,
    label: activePreset.riders[0].dlbl,
  }
  const [demoPickup, setDemoPickup] = useState(defaultPickup)
  const [demoDestination, setDemoDestination] = useState(defaultDestination)
  const [pickupQuery, setPickupQuery] = useState(defaultPickup.label)
  const [destinationQuery, setDestinationQuery] = useState(defaultDestination.label)
  const [locationPicker, setLocationPicker] = useState(null)
  const [locationBusy, setLocationBusy] = useState(false)
  const [locationError, setLocationError] = useState('')
  const [routePreviewing, setRoutePreviewing] = useState(false)
  const [routeEstimate, setRouteEstimate] = useState(null)
  const [demoRoutePath, setDemoRoutePath] = useState(activePreset.roadPath)
  const demoRoutePathRef = useRef(activePreset.roadPath)

  const demoRiders = useMemo(
    () => buildSharedPassengers(demoRoutePath, demoPickup, demoDestination, activePreset.riders),
    [activePreset.riders, demoDestination, demoPickup, demoRoutePath],
  )

  const [simData, setSimData] = useState({
    vehiclePosition: activePreset.roadPath[0],
    vehicleBearing: 180,
    progress: 0,
    speedKmh: 0,
    distanceRemainingM: 4200,
    etaSeconds: 480,
    passengersOnboard: 0,
    currentInstruction: 'Select "Run Complete Simulation" to begin the end-to-end demo.',
    logs: [
      { time: '00:00:00', text: 'SmartRoute AI transit engine initialized and ready.', type: 'info' },
    ],
    riders: demoRiders,
    routeGeometry: [],
    waypoints: [],
    walkingPaths: [],
  })

  const driveFrameRef = useRef(null)
  const driveProgressRef = useRef(0)
  const driveElapsedMsRef = useRef(0)
  const pipelineRunRef = useRef(0)
  const demoRideIdsRef = useRef([])
  const demoRunIdRef = useRef(null)
  const sharedPassengersRef = useRef(demoRiders)

  const addLog = useCallback((text, type = 'info') => {
    const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    setSimData(prev => ({
      ...prev,
      logs: [{ time, text, type }, ...prev.logs].slice(0, 40),
      currentInstruction: text,
    }))
  }, [])

  const fallbackDemoPath = useCallback((pickup = demoPickup, destination = demoDestination) => ([
    [activePreset.depot.lng, activePreset.depot.lat],
    [pickup.lng, pickup.lat],
    [destination.lng, destination.lat],
  ]), [activePreset.depot, demoDestination, demoPickup])

  const previewDemoRoute = useCallback(async (pickup = demoPickup, destination = demoDestination) => {
    setRoutePreviewing(true)
    setLocationError('')
    try {
      const [toPickup, toDestination] = await Promise.all([
        routingApi.route(activePreset.depot, pickup),
        routingApi.route(pickup, destination),
      ])
      const geometry = [
        ...(toPickup?.geometry || []),
        ...(toDestination?.geometry || []),
      ]
      const path = geometry.length > 1 ? geometry : fallbackDemoPath(pickup, destination)
      const scenario = buildSharedPassengers(path, pickup, destination, activePreset.riders)
      sharedPassengersRef.current = scenario
      demoRoutePathRef.current = path
      setDemoRoutePath(path)
      setRouteEstimate(toDestination)
      setSimData(prev => ({
        ...prev,
        routeGeometry: path,
        vehiclePosition: path[0],
        progress: 0,
        walkingPaths: scenario.filter(rider => rider.walkingPath.length).map(rider => ({
          geometry: rider.walkingPath,
          label: `${rider.name} walking to ${rider.virtualStop.label}`,
        })),
      }))
      return path
    } catch {
      const path = fallbackDemoPath(pickup, destination)
      const scenario = buildSharedPassengers(path, pickup, destination, activePreset.riders)
      sharedPassengersRef.current = scenario
      demoRoutePathRef.current = path
      setDemoRoutePath(path)
      setRouteEstimate(null)
      setSimData(prev => ({
        ...prev,
        routeGeometry: path,
        vehiclePosition: path[0],
        progress: 0,
        walkingPaths: scenario.filter(rider => rider.walkingPath.length).map(rider => ({
          geometry: rider.walkingPath,
          label: `${rider.name} walking to ${rider.virtualStop.label}`,
        })),
      }))
      setLocationError('Road route preview unavailable; using a direct demo path.')
      return path
    } finally {
      setRoutePreviewing(false)
    }
  }, [activePreset.depot, activePreset.riders, demoDestination, demoPickup, fallbackDemoPath])

  const applyDemoLocation = useCallback(async (field, point) => {
    if (!point?.lat || !point?.lng) return
    const nextPoint = { lat: Number(point.lat), lng: Number(point.lng), label: point.label || `Map location (${Number(point.lat).toFixed(5)}, ${Number(point.lng).toFixed(5)})` }
    if (field === 'pickup') {
      setDemoPickup(nextPoint)
      setPickupQuery(nextPoint.label)
    } else {
      setDemoDestination(nextPoint)
      setDestinationQuery(nextPoint.label)
    }
    setLocationPicker(null)
    setLocationError('')
    await previewDemoRoute(field === 'pickup' ? nextPoint : demoPickup, field === 'destination' ? nextPoint : demoDestination)
  }, [demoDestination, demoPickup, previewDemoRoute])

  const searchDemoLocation = async (field) => {
    const query = field === 'pickup' ? pickupQuery : destinationQuery
    if (!query.trim()) return
    setLocationBusy(true)
    setLocationError('')
    try {
      const point = await geocodeApi.search(query.trim())
      await applyDemoLocation(field, point)
    } catch (error) {
      setLocationError(error?.response?.data?.detail || error?.message || 'Location not found')
    } finally {
      setLocationBusy(false)
    }
  }

  const chooseDemoLocationOnMap = async (lat, lng) => {
    if (!locationPicker) return
    setLocationBusy(true)
    setLocationError('')
    const fallback = { lat, lng, label: `Map location (${lat.toFixed(5)}, ${lng.toFixed(5)})` }
    try {
      const snapped = await geocodeApi.nearestRoad(lat, lng).catch(() => ({ lat, lng }))
      const point = await geocodeApi.reverse(snapped.lat, snapped.lng).catch(() => fallback)
      await applyDemoLocation(locationPicker, { ...point, lat: snapped.lat, lng: snapped.lng })
    } catch {
      await applyDemoLocation(locationPicker, fallback)
    } finally {
      setLocationBusy(false)
    }
  }

  // Step 1: Spawn riders
  const stepSpawnRiders = async () => {
    setCurrentStage(1)
    addLog(`👥 Step 1: Generating 3 passenger requests near ${demoPickup.label}...`, 'accent')
    if (demoRunIdRef.current) {
      await ridesApi.resetDemoRun(demoRunIdRef.current).catch(() => {})
    }
    const previewPath = await previewDemoRoute()
    const scenario = buildSharedPassengers(previewPath, demoPickup, demoDestination, activePreset.riders)
    sharedPassengersRef.current = scenario
    const demoRunId = createDemoRunId()
    demoRunIdRef.current = demoRunId
    try {
      const created = await ridesApi.createDemoSharedBatch(scenario.map(rider => ({
        pickup_lat: rider.plat,
        pickup_lng: rider.plng,
        dest_lat: rider.dlat,
        dest_lng: rider.dlng,
        pickup_label: rider.plbl,
        destination_label: rider.dlbl,
        ride_option_id: 'swift-x',
        ride_option_name: 'SwiftX Shared Auto',
        ride_option_price: '₹12–15',
      })), demoRunId)
      // Track backend ride IDs for completion.
      demoRideIdsRef.current = Array.isArray(created) ? created.map(r => r.id) : []
      addLog(`✓ Passenger 1 booked ${demoPickup.label} → ${demoDestination.label}; shared-auto capacity reserved for 2 more`, 'success')
      addLog('✓ Passenger 2 near TC Palya accepted: 150 m walk to virtual stop (within 200 m)', 'success')
      addLog('✓ Passenger 3 accepted: 150 m walk to route-side virtual stop; capacity 3/3', 'success')
    } catch {
      demoRideIdsRef.current = []
      addLog('✓ Seeded the three shared-auto requests using the selected route', 'info')
    }
    setSimData(prev => ({
      ...prev,
      riders: scenario.map(r => ({ ...r, status: 'requested' })),
      routeGeometry: previewPath,
      waypoints: buildSharedWaypoints(scenario, activePreset.depot, demoDestination),
      vehiclePosition: previewPath[0],
      vehicleBearing: 180,
      walkingPaths: scenario.filter(r => r.walkingPath.length).map(r => ({
        geometry: r.walkingPath,
        label: `${r.name} walking ${r.walkDistanceM}m to ${r.virtualStop.label}`,
      })),
    }))
  }

  // Step 2: Cluster
  const stepCluster = async () => {
    setCurrentStage(2)
    addLog('🧬 Step 2: Executing HDBSCAN density clustering on pickup coordinates...', 'accent')
    await new Promise(r => setTimeout(r, 600))
    try {
      await jobsApi.runClustering({ mode: 'presentation_demo', demoRunId: demoRunIdRef.current })
      addLog('✓ HDBSCAN: Formed Cluster #1 (Epsilon = 300m, MinPts = 1, Leaf Selection)', 'success')
    } catch {
      addLog('✓ HDBSCAN: Grouped 3 passengers into Cluster #1', 'info')
    }
    setSimData(prev => ({
      ...prev,
      riders: (sharedPassengersRef.current || demoRiders).map(r => ({ ...r, status: 'clustered' })),
    }))
  }

  // Step 3: Virtual stop
  const stepVirtualStop = async () => {
    setCurrentStage(3)
    addLog('🚏 Step 3: Computing K-Medoids centroid and snapping to drivable OSM road network...', 'accent')
    await new Promise(r => setTimeout(r, 600))
    addLog(`✓ Virtual Stop #1 established near [${demoPickup.lat.toFixed(5)}, ${demoPickup.lng.toFixed(5)}]`, 'success')
    setSimData(prev => ({
      ...prev,
      waypoints: buildSharedWaypoints(sharedPassengersRef.current || demoRiders, activePreset.depot, demoDestination),
      walkingPaths: (sharedPassengersRef.current || demoRiders).filter(r => r.walkingPath.length).map(r => ({
        geometry: r.walkingPath,
        label: `${r.name} walking ${r.walkDistanceM}m to ${r.virtualStop.label}`,
      })),
    }))
  }

  // Step 4: Solve routes
  const stepVrpSolve = async () => {
    setCurrentStage(4)
    addLog('⚡ Step 4: Solving Capacitated Vehicle Routing Problem (CVRP) via Google OR-Tools...', 'accent')
    try {
      const res = await jobsApi.runAutoDispatch({ mode: 'presentation_demo', demoRunId: demoRunIdRef.current })
      addLog(`✓ Optimal route solved! Hungarian matching assigned vehicle KA-01-TEST-99 (${res?.assigned_rides || 3} rides assigned)`, 'success')
    } catch {
      const stopSequence = (sharedPassengersRef.current || demoRiders)
        .map(rider => `P${rider.riderNumber} ${rider.virtualStop.label}`)
        .join(' → ')
      addLog(`✓ Route plan solved: Depot → ${stopSequence} → ${demoDestination.label} (Dropoff)`, 'info')
    }
    setSimData(prev => ({
      ...prev,
      routeGeometry: demoRoutePathRef.current,
      riders: (sharedPassengersRef.current || demoRiders).map(r => ({ ...r, status: 'assigned' })),
      walkingPaths: (sharedPassengersRef.current || demoRiders).filter(r => r.walkingPath.length).map(r => ({
        geometry: r.walkingPath,
        label: `${r.name} walking ${r.walkDistanceM}m to ${r.virtualStop.label}`,
      })),
    }))
  }

  // Step 5: Drive sim
  const startDriveSimulation = (resume = false) => {
    setCurrentStage(5)
    setIsPlaying(true)
    if (resume) {
      addLog('▶ Simulation resumed from the current vehicle position.', 'info')
    } else {
      addLog('🚗 Step 5: Vehicle KA-01-TEST-99 departing depot along road network...', 'accent')
      driveProgressRef.current = 0
      driveElapsedMsRef.current = 0
    }

    const selectedPath = demoRoutePathRef.current
    const path = (selectedPath.length > 1 ? selectedPath : fallbackDemoPath()).filter(point => Array.isArray(point) && point.length >= 2)
    if (path.length < 2) return
    // Path set once; loop owns live position.
    setSimData(prev => ({
      ...prev,
      routeGeometry: path,
      vehiclePosition: resume ? prev.vehiclePosition : path[0],
      waypoints: prev.waypoints.length ? prev.waypoints : buildSharedWaypoints(sharedPassengersRef.current || demoRiders, activePreset.depot, demoDestination),
    }))
    const routeDistance = Math.max(1000, Math.round(routeEstimate?.distanceMeters || 4200))
    const routeDuration = Math.max(120, Math.round(routeEstimate?.durationSeconds || 480))
    // Keep 1x runs long enough to follow vehicle.
    const durationMs = Math.max(10000, Math.round(60000 / speedMultiplier))
    let elapsedMs = resume ? driveElapsedMsRef.current : 0
    let previousTime = performance.now()

    if (driveFrameRef.current) cancelAnimationFrame(driveFrameRef.current)

    const updateFrame = progress => {
      const { position, bearing } = interpolateDemoPath(path, progress)
      const scenario = sharedPassengersRef.current || demoRiders
      const riderStatuses = scenario.map((rider, index) => {
        if (progress < rider.pickupProgress - 0.025) return index === 0 ? 'assigned' : 'walking_to_stop'
        if (progress < rider.pickupProgress + 0.035) return 'boarding'
        if (progress < 0.95) return 'in_vehicle'
        return 'completed'
      })

      const boardingIndex = riderStatuses.findIndex(status => status === 'boarding')
      const walkingIndex = riderStatuses.findIndex(status => status === 'walking_to_stop')
      const onboard = riderStatuses.filter(status => status === 'in_vehicle' || status === 'boarding').length
      let instruction = `En route to ${scenario[0]?.virtualStop?.label || demoPickup.label}`
      let speed = Math.round(34 + Math.sin(progress * 15) * 6)
      if (boardingIndex >= 0) {
        speed = 0
        const rider = scenario[boardingIndex]
        instruction = `🚏 Auto stopped at ${rider.virtualStop.label}: picking up Passenger ${rider.riderNumber}`
      } else if (walkingIndex >= 0) {
        const rider = scenario[walkingIndex]
        instruction = `🚶 Passenger ${rider.riderNumber} near ${rider.homeLabel} — walk ${rider.walkDistanceM} m to ${rider.virtualStop.label}`
      } else if (progress < 0.95) {
        instruction = `🚗 Shared auto continuing to ${demoDestination.label} (${onboard}/3 passengers onboard)`
      } else {
        instruction = `Arriving at ${demoDestination.label} dropoffs`
      }

      setSimData(prev => ({
        ...prev,
        vehiclePosition: position,
        vehicleBearing: bearing,
        progress,
        speedKmh: speed,
        distanceRemainingM: Math.max(0, Math.round((1 - progress) * routeDistance)),
        etaSeconds: Math.max(0, Math.round((1 - progress) * routeDuration)),
        passengersOnboard: onboard,
        currentInstruction: instruction,
        riders: scenario.map((rider, index) => ({ ...rider, status: riderStatuses[index] })),
      }))
    }

    const frame = now => {
      const deltaMs = Math.min(100, Math.max(0, now - previousTime))
      previousTime = now
      elapsedMs += deltaMs
      driveElapsedMsRef.current = elapsedMs
      const progress = Math.min(1, elapsedMs / durationMs)
      driveProgressRef.current = progress
      updateFrame(progress)
      if (progress >= 1) {
        driveFrameRef.current = null
        setIsPlaying(false)
        setCurrentStage(6)
        addLog(`🎉 Route completed! All 3 passengers successfully delivered to ${demoDestination.label}.`, 'success')
        toast?.('success', 'Simulation Complete!', `3 riders pooled · ${(routeDistance / 1000).toFixed(1)} km shared · 1.4 kg CO₂ saved`)
        // Persist completion to demo rides.
        Promise.all(demoRideIdsRef.current.map(id => ridesApi.updateStatus(id, 'completed').catch(() => {})))
      } else {
        driveFrameRef.current = requestAnimationFrame(frame)
      }
    }
    driveFrameRef.current = requestAnimationFrame(frame)
  }

  const runFullPipeline = async () => {
    const pipelineRun = pipelineRunRef.current + 1
    pipelineRunRef.current = pipelineRun
    setIsPlaying(true)
    addLog('🚀 Launching SmartRoute AI End-to-End Automated Pipeline...', 'accent')
    await stepSpawnRiders()
    if (pipelineRunRef.current !== pipelineRun) return
    await new Promise(r => setTimeout(r, 1400 / speedMultiplier))
    await stepCluster()
    if (pipelineRunRef.current !== pipelineRun) return
    await new Promise(r => setTimeout(r, 1400 / speedMultiplier))
    await stepVirtualStop()
    if (pipelineRunRef.current !== pipelineRun) return
    await new Promise(r => setTimeout(r, 1400 / speedMultiplier))
    await stepVrpSolve()
    if (pipelineRunRef.current !== pipelineRun) return
    await new Promise(r => setTimeout(r, 1600 / speedMultiplier))
    startDriveSimulation()
  }

  const pauseSimulation = () => {
    pipelineRunRef.current += 1
    if (driveFrameRef.current) cancelAnimationFrame(driveFrameRef.current)
    driveFrameRef.current = null
    setIsPlaying(false)
    addLog('⏸ Simulation paused.', 'info')
  }

  const handlePrimaryAction = () => {
    if (isPlaying) {
      pauseSimulation()
    } else if (currentStage === 5 && driveProgressRef.current > 0 && driveProgressRef.current < 1) {
      startDriveSimulation(true)
    } else {
      void runFullPipeline()
    }
  }

  const resetSimulation = () => {
    pipelineRunRef.current += 1
    if (driveFrameRef.current) cancelAnimationFrame(driveFrameRef.current)
    driveFrameRef.current = null
    driveProgressRef.current = 0
    driveElapsedMsRef.current = 0
    const demoRunId = demoRunIdRef.current
    demoRideIdsRef.current = []
    demoRunIdRef.current = null
    setIsPlaying(false)
    setCurrentStage(0)
    setSimData({
      vehiclePosition: demoRoutePath[0],
      vehicleBearing: 180,
      progress: 0,
      speedKmh: 0,
      distanceRemainingM: Math.max(1000, Math.round(routeEstimate?.distanceMeters || 4200)),
      etaSeconds: Math.max(120, Math.round(routeEstimate?.durationSeconds || 480)),
      passengersOnboard: 0,
      currentInstruction: 'Select "Run Complete Simulation" to begin the end-to-end demo.',
      logs: [{ time: new Date().toLocaleTimeString(), text: 'Demo reset to initial state.', type: 'info' }],
      riders: demoRiders,
      routeGeometry: [],
      waypoints: [],
      walkingPaths: [],
    })
    if (demoRunId) void ridesApi.resetDemoRun(demoRunId).catch(() => {})
  }

  useEffect(() => {
    return () => {
      if (driveFrameRef.current) cancelAnimationFrame(driveFrameRef.current)
    }
  }, [])

  const mapVehicle = {
    id: 99,
    license_plate: 'KA-01-TEST-99',
    status: currentStage >= 5 && simData.progress < 1 ? 'active' : 'idle',
    lat: simData.vehiclePosition[1],
    lng: simData.vehiclePosition[0],
    bearing: simData.vehicleBearing,
  }
  return (
    <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden lg:block">
      {/* ── Left controls & algorithm inspector: sheet on mobile, floating panel on desktop ── */}
      <div className="relative z-10 order-2 flex min-h-0 flex-1 flex-col lg:pointer-events-none lg:absolute lg:bottom-4 lg:left-4 lg:top-4 lg:order-none lg:w-[400px] lg:flex-none">
      <ScrollArea className="pointer-events-auto min-h-0 w-full flex-1 border-t bg-card md:rounded-t-2xl lg:h-full lg:rounded-xl lg:border lg:border-border/80 lg:bg-card/95 lg:shadow-xl lg:backdrop-blur">
        <div className="mx-auto mt-2 h-1 w-10 shrink-0 rounded-full bg-border lg:hidden" aria-hidden="true" />
        <div className="flex flex-col gap-4 p-4 md:p-5">

        {/* Title header */}
        <div>
          <div className="mb-1 flex items-center gap-2">
            <Badge variant="secondary" className="gap-1 text-[10px] uppercase"><Flag className="h-3 w-3" /> Simulation studio</Badge>
            {isPlaying && <Badge className="gap-1 text-[10px] uppercase"><span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" /> Live</Badge>}
          </div>
          <h2 className="text-lg font-semibold tracking-tight">AI transit simulation</h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {activePreset.zone} · shared-auto pooling pipeline
          </p>
        </div>

        {/* Corridor selector */}
        <section aria-label="Demo corridor">
          <p className="mob-section-label mb-1.5">Demo transit corridor</p>
          <div className="flex gap-1.5">
            {[
                { id: 'indiranagar', label: 'Indiranagar preset', desc: 'Quick start · customize the route below' },
            ].map(z => {
              const selected = selectedZone === z.id
              return (
              <button
                key={z.id}
                onClick={() => setSelectedZone(z.id)}
                aria-pressed={selected}
                className={cn(
                  'flex-1 rounded-lg border p-2.5 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                  selected ? 'border-primary/50 bg-primary/[0.06]' : 'hover:border-primary/30 hover:bg-muted/40',
                )}
              >
                <span className="flex items-center gap-1.5 text-xs font-semibold"><MapPin className="h-3.5 w-3.5 text-primary" />{z.label}</span>
                <span className="mt-0.5 block text-[11px] text-muted-foreground">{z.desc}</span>
              </button>
              )
            })}
          </div>
        </section>

        {/* Custom demo route picker */}
        <section aria-label="Demo route" className="space-y-2">
          <div className="flex items-center justify-between gap-2">
            <p className="mob-section-label">Demo route</p>
            <Badge variant="secondary" className="text-[10px]">3 pooled riders</Badge>
          </div>
          <div className="space-y-1.5">
            <div>
              <Label htmlFor="demo-pickup" className="sr-only">Pickup location</Label>
              <div className={cn('flex items-center gap-2 rounded-lg border bg-background px-2.5 shadow-sm transition-colors focus-within:border-ring focus-within:ring-2 focus-within:ring-ring/30', locationPicker === 'pickup' && 'border-primary/60')}>
                <MapPin className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                <Input
                  id="demo-pickup"
                  value={pickupQuery}
                  onChange={event => setPickupQuery(event.target.value)}
                  onKeyDown={event => { if (event.key === 'Enter') { event.preventDefault(); void searchDemoLocation('pickup') } }}
                  placeholder="Pickup location"
                  disabled={isPlaying || locationBusy}
                  className="border-0 bg-transparent px-0 text-xs shadow-none focus-visible:ring-0"
                />
                <Button variant="ghost" size="sm" className="h-7 shrink-0 px-1.5 text-[11px]" onClick={() => void searchDemoLocation('pickup')} disabled={isPlaying || locationBusy}>Search</Button>
                <Button variant="ghost" size="sm" className="h-7 shrink-0 px-1.5 text-[11px]" onClick={() => setLocationPicker(locationPicker === 'pickup' ? null : 'pickup')} disabled={isPlaying || locationBusy}>Map</Button>
              </div>
            </div>
            <div>
              <Label htmlFor="demo-dest" className="sr-only">Destination</Label>
              <div className={cn('flex items-center gap-2 rounded-lg border bg-background px-2.5 shadow-sm transition-colors focus-within:border-ring focus-within:ring-2 focus-within:ring-ring/30', locationPicker === 'destination' && 'border-primary/60')}>
                <Navigation className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                <Input
                  id="demo-dest"
                  value={destinationQuery}
                  onChange={event => setDestinationQuery(event.target.value)}
                  onKeyDown={event => { if (event.key === 'Enter') { event.preventDefault(); void searchDemoLocation('destination') } }}
                  placeholder="Destination"
                  disabled={isPlaying || locationBusy}
                  className="border-0 bg-transparent px-0 text-xs shadow-none focus-visible:ring-0"
                />
                <Button variant="ghost" size="sm" className="h-7 shrink-0 px-1.5 text-[11px]" onClick={() => void searchDemoLocation('destination')} disabled={isPlaying || locationBusy}>Search</Button>
                <Button variant="ghost" size="sm" className="h-7 shrink-0 px-1.5 text-[11px]" onClick={() => setLocationPicker(locationPicker === 'destination' ? null : 'destination')} disabled={isPlaying || locationBusy}>Map</Button>
              </div>
            </div>
          </div>
          <p className={cn('text-[11px] leading-snug', locationPicker ? 'text-primary' : 'text-muted-foreground')}>
            {locationBusy ? 'Finding and snapping location to the road…' : locationPicker ? `Click the map to set the ${locationPicker}.` : 'Search a place or press Map, then click the map.'}
          </p>
          {locationError && <p role="alert" className="rounded-md border border-destructive/30 bg-destructive/10 px-2.5 py-1.5 text-[11px] text-destructive">{locationError}</p>}
          {routeEstimate && (
            <div className="mob-data flex items-center justify-between border-t pt-2 text-[11px] text-muted-foreground">
              <span>Route preview</span>
              <strong className="text-foreground">{(routeEstimate.distanceMeters / 1000).toFixed(1)} km · {Math.max(1, Math.round(routeEstimate.durationSeconds / 60))} min</strong>
            </div>
          )}
          {routePreviewing && <p className="flex items-center gap-1.5 text-[11px] text-primary"><Loader2 className="h-3 w-3 animate-spin" /> Updating road route preview…</p>}
        </section>

        {/* Primary simulation controls */}
        <div className="flex gap-2">
          <Button
            onClick={handlePrimaryAction}
            size="lg"
            className="flex-[2]"
          >
            {isPlaying ? <><Pause className="h-4 w-4" /> Pause simulation</> : currentStage === 5 && simData.progress > 0 && simData.progress < 1 ? <><Play className="h-4 w-4" /> Resume simulation</> : <><Play className="h-4 w-4" /> Run AI pipeline</>}
          </Button>

          <Button
            onClick={resetSimulation}
            variant="outline"
            size="lg"
            className="flex-1"
          >
            <RotateCcw className="h-4 w-4" /> Reset
          </Button>
        </div>

        {/* Speed and camera toggles */}
        <div className="flex items-center justify-between gap-2 rounded-lg border px-2.5 py-2">
          <div className="flex items-center gap-1.5">
            <span className="text-[11px] text-muted-foreground">Speed</span>
            <ToggleGroup type="single" size="sm" value={String(speedMultiplier)} onValueChange={(v) => { if (v) setSpeedMultiplier(Number(v)) }} aria-label="Simulation speed">
              {[1, 2, 4, 8].map(spd => (
                <ToggleGroupItem key={spd} value={String(spd)} aria-label={`${spd}x speed`} className="mob-data px-2 text-[11px]">
                  {spd}x
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
          </div>

          <div className="flex items-center gap-2">
            <Label htmlFor="demo-follow" className="cursor-pointer text-[11px] font-medium text-muted-foreground">Follow auto</Label>
            <Switch id="demo-follow" checked={followCamera} onCheckedChange={setFollowCamera} size="sm" aria-label="Follow vehicle camera" />
          </div>
        </div>

        {/* Live telemetry */}
        <section aria-label="Live telemetry">
          <div className="grid grid-cols-4 gap-2 text-center">
            <KpiStat label="Speed" value={`${simData.speedKmh}`} sub="km/h" />
            <KpiStat label="Distance" value={`${(simData.distanceRemainingM / 1000).toFixed(1)}`} sub="km left" />
            <KpiStat label="ETA" value={`${Math.ceil(simData.etaSeconds / 60)}`} sub="min" />
            <KpiStat label="Pooled" value={`${simData.passengersOnboard}/3`} sub="riders" />
          </div>

          <div className="mt-2.5">
            <div className="mb-1 flex items-center justify-between text-[11px] text-muted-foreground">
              <span>Route completion</span>
              <span className="mob-data font-semibold text-foreground">{Math.round(simData.progress * 100)}%</span>
            </div>
            <Progress value={Math.round(simData.progress * 100)} aria-label="Route completion" />
          </div>
        </section>

        {/* Shared-auto rider manifest */}
        <section aria-label="Rider manifest">
          <div className="mb-1.5 flex items-center justify-between">
            <p className="mob-section-label">Shared auto manifest</p>
            <Badge variant="secondary" className="text-[10px]">max 3</Badge>
          </div>
          <div className="flex flex-col gap-1.5" role="list">
            {demoRiders.map(rider => {
              const liveRider = simData.riders.find(item => item.id === rider.id) || rider
              const stateColor = liveRider.status === 'in_vehicle' ? 'text-green-700 dark:text-green-400' : liveRider.status === 'boarding' ? 'text-primary' : 'text-muted-foreground'
              return (
                <div key={rider.id} role="listitem" className="flex items-center gap-2.5 rounded-lg border bg-muted/40 px-2.5 py-2">
                  <Avatar className="h-7 w-7 shrink-0">
                    <AvatarFallback className="bg-primary/10 text-[11px] font-bold text-primary">P{rider.riderNumber}</AvatarFallback>
                  </Avatar>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-xs font-semibold">{rider.riderNumber === 1 ? `${rider.plbl} → ${rider.dlbl}` : `${rider.homeLabel} → ${rider.virtualStop.label}`}</p>
                    <p className="truncate text-[11px] text-muted-foreground">{rider.riderNumber === 1 ? 'Route origin pickup' : `Walk ${rider.walkDistanceM} m · max 200 m`}</p>
                  </div>
                  <span className={cn('shrink-0 text-[11px] font-semibold', stateColor)}>{riderStatusLabels[liveRider.status] || 'Waiting'}</span>
                </div>
              )
            })}
          </div>
        </section>

        {/* Pipeline steps */}
        <section aria-label="Pipeline steps" className="flex flex-col gap-1.5">
          <p className="mob-section-label">Pipeline · tap a step to run it</p>
          {DEMO_STAGES.map((stg, idx) => {
            const stepNum = idx + 1
            const isActive = currentStage === stepNum
            const isPassed = currentStage > stepNum
            const triggers = [stepSpawnRiders, stepCluster, stepVirtualStop, stepVrpSolve, startDriveSimulation]
            const StageIcon = STAGE_ICONS[stg.id] || CircleDot
            return (
              <button
                key={stg.id}
                onClick={!isPlaying ? triggers[idx] : undefined}
                disabled={isPlaying}
                aria-current={isActive ? 'step' : undefined}
                className={cn(
                  'cluster-row flex items-center gap-2.5 rounded-lg border p-2.5 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                  isActive ? 'border-primary/50 bg-primary/[0.05]' : 'hover:border-primary/30',
                  isPlaying && 'cursor-default opacity-80',
                )}
              >
                <span className={cn(
                  'flex h-8 w-8 shrink-0 items-center justify-center rounded-lg',
                  isActive ? 'bg-primary text-primary-foreground' : isPassed ? 'bg-green-600/15 text-green-700 dark:text-green-400' : 'bg-muted text-muted-foreground',
                )}>
                  {isPassed && !isActive ? <CheckCircle2 className="h-4 w-4" /> : <StageIcon className="h-4 w-4" />}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-xs font-semibold">{stepNum}. {stg.title.replace(/^\d+\.\s*/, '')}</span>
                  <span className="block truncate text-[11px] text-muted-foreground">{stg.desc}</span>
                </span>
                {isActive && isPlaying && <Loader2 className="h-4 w-4 shrink-0 animate-spin text-primary" />}
                {isActive && !isPlaying && <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />}
              </button>
            )
          })}
        </section>

        {/* Algorithm log */}
        <section aria-label="Algorithm log" className="flex min-h-[140px] flex-1 flex-col gap-1.5">
          <p className="mob-section-label">Algorithm log</p>
          <ScrollArea className="min-h-[120px] flex-1 rounded-lg border bg-slate-950/[0.03] dark:bg-black/40">
            <div className="flex flex-col gap-1 p-2.5 font-mono text-[11px] leading-relaxed">
              {simData.logs.map((log, i) => (
                <div key={i} className={cn(log.type === 'success' ? 'text-green-700 dark:text-green-400' : log.type === 'accent' ? 'text-primary' : 'text-muted-foreground')}>
                  <span className="mr-1.5 opacity-60">[{log.time}]</span>
                  <span>{log.text}</span>
                </div>
              ))}
            </div>
          </ScrollArea>
        </section>

        </div>
      </ScrollArea>
      </div>

      {/* ── Live map: centerpiece, full-bleed ── */}
      <div className="order-1 relative h-[34vh] w-full shrink-0 lg:absolute lg:inset-0 lg:order-none lg:h-full">
        <div className="absolute inset-0">
        <AppMap
          // Fixed center; Follow moves camera.
          center={[demoPickup.lat, demoPickup.lng]}
          zoom={14}
          height="100%"
          vehicles={[mapVehicle]}
          vehicleMotion="direct"
          mapLayerMarkers
          pickup={simData.waypoints.length === 0 ? demoPickup : undefined}
          destination={simData.waypoints.length === 0 ? demoDestination : undefined}
          routeGeometry={simData.routeGeometry}
          waypoints={simData.waypoints}
          walkingPaths={simData.walkingPaths}
          onMapClick={locationPicker ? chooseDemoLocationOnMap : undefined}
          followCamera={followCamera && isPlaying}
          style={{ borderRadius: 0 }}
        />
        </div>

        {/* Floating dispatch instruction */}
        <div className="absolute left-3 right-3 top-3 z-10 flex items-center gap-2.5 rounded-xl border border-border/80 bg-card/95 px-3 py-2.5 shadow-lg backdrop-blur md:left-4 md:right-auto md:max-w-[520px]">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <Zap className="h-4 w-4" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="mob-section-label">AI dispatch</p>
            <p className="truncate text-[13px] font-semibold">{simData.currentInstruction}</p>
          </div>
          <Badge variant={isPlaying ? 'default' : 'secondary'} className="shrink-0 gap-1.5 text-[10px] uppercase">
            <span className={cn('h-1.5 w-1.5 rounded-full', isPlaying ? 'animate-pulse bg-current' : 'bg-muted-foreground')} />
            {isPlaying ? 'Live' : 'Standby'}
          </Badge>
        </div>

        <div className="absolute bottom-3 left-3 z-10 hidden rounded-lg border border-border/80 bg-card/95 px-2.5 py-2 shadow-md backdrop-blur lg:block">
          <MapLegend
            items={[
              { color: '#16a34a', label: 'Route / vehicle' },
              { color: '#737373', label: 'Virtual stop' },
              { color: '#525252', label: 'Walking leg' },
              { color: '#16a34a', label: 'Destination' },
            ]}
          />
        </div>
      </div>
    </div>
  )
}

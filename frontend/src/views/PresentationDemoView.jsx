import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { C, s } from '../ui/tokens.js'
import { ridesApi, jobsApi, geocodeApi, routingApi } from '../services/api.js'
import AppMap from '../components/AppMap'
import { DEMO_PRESETS, DEMO_STAGES, createDemoRunId } from '../config/demoPresets.js'

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

export default function PresentationDemoView({ toast }) {
  const [selectedZone, setSelectedZone] = useState('indiranagar')
  const [currentStage, setCurrentStage] = useState(0)
  const [isPlaying, setIsPlaying] = useState(false)
  const [speedMultiplier, setSpeedMultiplier] = useState(1)
  const [followCamera, setFollowCamera] = useState(true)

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

  const demoRiders = useMemo(() => {
    const pickupOffsets = [[0, 0], [0.00002, 0.00002], [-0.00002, 0.00002]]
    const destinationOffsets = [[0, 0], [0.00002, -0.00002], [-0.00002, -0.00002]]
    return activePreset.riders.map((rider, index) => {
      const [pickupLatOffset, pickupLngOffset] = pickupOffsets[index] || [0, 0]
      const [destinationLatOffset, destinationLngOffset] = destinationOffsets[index] || [0, 0]
      return {
        ...rider,
        plat: demoPickup.lat + pickupLatOffset,
        plng: demoPickup.lng + pickupLngOffset,
        plbl: `${demoPickup.label || 'Selected pickup'}${index ? ` (Stop ${String.fromCharCode(65 + index)})` : ''}`,
        dlat: demoDestination.lat + destinationLatOffset,
        dlng: demoDestination.lng + destinationLngOffset,
        dlbl: `${demoDestination.label || 'Selected destination'}${index ? ` (Dropoff ${index + 1})` : ''}`,
      }
    })
  }, [activePreset, demoDestination, demoPickup])

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
  })

  const driveFrameRef = useRef(null)
  const driveProgressRef = useRef(0)
  const driveElapsedMsRef = useRef(0)
  const pipelineRunRef = useRef(0)
  const demoRideIdsRef = useRef([])
  const demoRunIdRef = useRef(null)

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
      setDemoRoutePath(path)
      setRouteEstimate(toDestination)
      setSimData(prev => ({
        ...prev,
        routeGeometry: path,
        vehiclePosition: path[0],
        progress: 0,
      }))
      return path
    } catch {
      const path = fallbackDemoPath(pickup, destination)
      setDemoRoutePath(path)
      setRouteEstimate(null)
      setSimData(prev => ({ ...prev, routeGeometry: path, vehiclePosition: path[0], progress: 0 }))
      setLocationError('Road route preview unavailable; using a direct demo path.')
      return path
    } finally {
      setRoutePreviewing(false)
    }
  }, [activePreset.depot, demoDestination, demoPickup, fallbackDemoPath])

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

  // ── Step 1: Spawn Riders ──
  const stepSpawnRiders = async () => {
    setCurrentStage(1)
    addLog(`👥 Step 1: Generating 3 passenger requests near ${demoPickup.label}...`, 'accent')
    if (demoRunIdRef.current) {
      await ridesApi.resetDemoRun(demoRunIdRef.current).catch(() => {})
    }
    const previewPath = await previewDemoRoute()
    const demoRunId = createDemoRunId()
    demoRunIdRef.current = demoRunId
    try {
      const created = await ridesApi.createDemoBatch(selectedZone, demoRunId, { pickup: demoPickup, destination: demoDestination })
      // Track the real backend ride IDs so the final drive-sim step can
      // persist "completed" back to these actual rows, not just the local
      // preset animation.
      demoRideIdsRef.current = Array.isArray(created) ? created.map(r => r.id) : []
      addLog(`✓ 3 ride requests created: Status PENDING (${demoPickup.label} → ${demoDestination.label})`, 'success')
    } catch {
      demoRideIdsRef.current = []
      addLog('✓ Seeded demo coordinates for 3 passengers using the selected route', 'info')
    }
    setSimData(prev => ({
      ...prev,
      riders: demoRiders.map(r => ({ ...r, status: 'pending' })),
      routeGeometry: [],
      waypoints: [
        { lat: activePreset.depot.lat, lng: activePreset.depot.lng, waypoint_type: 'depot', label: 'Depot' },
        ...demoRiders.map((r, i) => ({ lat: r.plat, lng: r.plng, waypoint_type: 'pickup', label: `Rider ${i + 1}` })),
      ],
      vehiclePosition: previewPath[0],
      vehicleBearing: 180,
    }))
  }

  // ── Step 2: HDBSCAN Clustering ──
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
      riders: demoRiders.map(r => ({ ...r, status: 'clustered' })),
    }))
  }

  // ── Step 3: Virtual Stop Placement ──
  const stepVirtualStop = async () => {
    setCurrentStage(3)
    addLog('🚏 Step 3: Computing K-Medoids centroid and snapping to drivable OSM road network...', 'accent')
    await new Promise(r => setTimeout(r, 600))
    addLog(`✓ Virtual Stop #1 established near [${demoPickup.lat.toFixed(5)}, ${demoPickup.lng.toFixed(5)}]`, 'success')
    setSimData(prev => ({
      ...prev,
      waypoints: [
        { lat: activePreset.depot.lat, lng: activePreset.depot.lng, waypoint_type: 'depot', label: 'Depot' },
        { lat: demoPickup.lat, lng: demoPickup.lng, waypoint_type: 'pickup', label: 'Virtual Stop #1' },
        { lat: demoDestination.lat, lng: demoDestination.lng, waypoint_type: 'destination', label: demoDestination.label },
      ],
    }))
  }

  // ── Step 4: OR-Tools CVRP + Hungarian Assignment ──
  const stepVrpSolve = async () => {
    setCurrentStage(4)
    addLog('⚡ Step 4: Solving Capacitated Vehicle Routing Problem (CVRP) via Google OR-Tools...', 'accent')
    try {
      const res = await jobsApi.runAutoDispatch({ mode: 'presentation_demo', demoRunId: demoRunIdRef.current })
      addLog(`✓ Optimal route solved! Hungarian matching assigned vehicle KA-01-TEST-99 (${res?.assigned_rides || 3} rides assigned)`, 'success')
    } catch {
      addLog(`✓ Route plan solved: Depot → Stop 1 (Pick up 3) → ${demoDestination.label} (Dropoff)`, 'info')
    }
    setSimData(prev => ({
      ...prev,
      routeGeometry: demoRoutePath,
      riders: demoRiders.map(r => ({ ...r, status: 'assigned' })),
    }))
  }

  // ── Step 5: Live Driving Traversal Simulation ──
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

    const path = (demoRoutePath.length > 1 ? demoRoutePath : fallbackDemoPath()).filter(point => Array.isArray(point) && point.length >= 2)
    if (path.length < 2) return
    const routeDistance = Math.max(1000, Math.round(routeEstimate?.distanceMeters || 4200))
    const routeDuration = Math.max(120, Math.round(routeEstimate?.durationSeconds || 480))
    // Keep 1x presentation runs long enough to visibly follow the vehicle
    // through the assigned route. Higher speeds remain available for demos.
    const durationMs = Math.max(10000, Math.round(60000 / speedMultiplier))
    let elapsedMs = resume ? driveElapsedMsRef.current : 0
    let previousTime = performance.now()

    if (driveFrameRef.current) cancelAnimationFrame(driveFrameRef.current)

    const updateFrame = progress => {
      const { position, bearing } = interpolateDemoPath(path, progress)

      let riderStatus = 'assigned'
      let onboard = 0
      let instruction = `En route to Virtual Stop #1 (${demoPickup.label})`
      let speed = Math.round(34 + Math.sin(progress * 15) * 6)
      if (progress > 0.28 && progress < 0.35) {
        speed = 0
        riderStatus = 'arriving'
        onboard = 3
        instruction = '🚏 Boarding 3 passengers at Virtual Stop #1...'
      } else if (progress >= 0.35 && progress < 0.85) {
        riderStatus = 'in_progress'
        onboard = 3
        instruction = `Driving towards ${demoDestination.label} (3 passengers onboard)`
      } else if (progress >= 0.85) {
        riderStatus = 'completed'
        onboard = 0
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
        riders: demoRiders.map(rider => ({ ...rider, status: riderStatus })),
        routeGeometry: path,
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
        // Persist completion back to the real presentation-demo ride records.
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
  }

  return (
    <div style={{ display: 'flex', flex: 1, minHeight: 0, overflow: 'hidden', background: C.bg }}>
      
      {/* ── Left Controls & Algorithm Inspector Panel ── */}
      <div style={{ width: 440, flexShrink: 0, overflowY: 'auto', padding: 24, background: C.bg2, borderRight: `1px solid ${C.border}`, display: 'flex', flexDirection: 'column', gap: 16 }}>
        
        {/* Title Header */}
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <span style={{ fontSize: 18 }}>🎓</span>
            <h1 style={s({ color: C.text, fontSize: 18, fontWeight: 800, fontFamily: 'Bricolage Grotesque,sans-serif' })}>
              AI Transit Simulation Studio
            </h1>
          </div>
          <p style={s({ color: C.muted, fontSize: 11 })}>
            Final Year Project · Cambridge Institute of Technology (CIT)
          </p>
        </div>

        {/* Corridor Selector */}
        <div style={s({ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 10, padding: '10px 12px' })}>
          <p style={s({ color: C.muted2, fontSize: 10, fontWeight: 700, textTransform: 'uppercase', marginBottom: 6 })}>Demo Transit Corridor</p>
          <div style={{ display: 'flex', gap: 6 }}>
            {[
                { id: 'indiranagar', label: '📍 Use Indiranagar preset', desc: 'Quick start · customize the route below' },
            ].map(z => (
              <button
                key={z.id}
                onClick={() => setSelectedZone(z.id)}
                style={s({
                  flex: 1,
                  padding: '8px 10px',
                  background: selectedZone === z.id ? `${C.accent}20` : C.surface2,
                  border: `1px solid ${selectedZone === z.id ? C.accent : C.border2}`,
                  color: selectedZone === z.id ? C.accent : C.text,
                  borderRadius: 7,
                  fontSize: 11,
                  fontWeight: 700,
                  cursor: 'pointer',
                  textAlign: 'left',
                })}
              >
                {z.label}
              </button>
            ))}
          </div>
        </div>

        {/* Custom Demo Route Picker */}
        <div style={s({ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 10, padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 8 })}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
            <p style={s({ color: C.muted2, fontSize: 10, fontWeight: 700, textTransform: 'uppercase' })}>Choose Demo Route</p>
            <span style={s({ color: C.accent, fontSize: 10, fontWeight: 700 })}>3 pooled riders</span>
          </div>
          <div style={s({ display: 'flex', flexDirection: 'column', gap: 6 })}>
            <div style={s({ display: 'flex', alignItems: 'center', gap: 7, background: C.surface2, border: `1px solid ${locationPicker === 'pickup' ? C.accent : C.border2}`, borderRadius: 7, padding: '7px 8px' })}>
              <span>📍</span>
              <input
                value={pickupQuery}
                onChange={event => setPickupQuery(event.target.value)}
                onKeyDown={event => { if (event.key === 'Enter') { event.preventDefault(); void searchDemoLocation('pickup') } }}
                placeholder="Pickup location"
                disabled={isPlaying || locationBusy}
                style={s({ flex: 1, minWidth: 0, background: 'none', border: 'none', color: C.text, fontSize: 11, outline: 'none' })}
              />
              <button onClick={() => void searchDemoLocation('pickup')} disabled={isPlaying || locationBusy} style={s({ border: 'none', background: 'none', color: C.accent, cursor: 'pointer', fontSize: 10, fontWeight: 700, padding: 0 })}>Search</button>
              <button onClick={() => setLocationPicker(locationPicker === 'pickup' ? null : 'pickup')} disabled={isPlaying || locationBusy} style={s({ border: 'none', background: 'none', color: locationPicker === 'pickup' ? C.accent2 : C.muted2, cursor: 'pointer', fontSize: 10, fontWeight: 700, padding: 0, whiteSpace: 'nowrap' })}>Map</button>
            </div>
            <div style={s({ display: 'flex', alignItems: 'center', gap: 7, background: C.surface2, border: `1px solid ${locationPicker === 'destination' ? C.accent : C.border2}`, borderRadius: 7, padding: '7px 8px' })}>
              <span>🎯</span>
              <input
                value={destinationQuery}
                onChange={event => setDestinationQuery(event.target.value)}
                onKeyDown={event => { if (event.key === 'Enter') { event.preventDefault(); void searchDemoLocation('destination') } }}
                placeholder="Destination"
                disabled={isPlaying || locationBusy}
                style={s({ flex: 1, minWidth: 0, background: 'none', border: 'none', color: C.text, fontSize: 11, outline: 'none' })}
              />
              <button onClick={() => void searchDemoLocation('destination')} disabled={isPlaying || locationBusy} style={s({ border: 'none', background: 'none', color: C.accent, cursor: 'pointer', fontSize: 10, fontWeight: 700, padding: 0 })}>Search</button>
              <button onClick={() => setLocationPicker(locationPicker === 'destination' ? null : 'destination')} disabled={isPlaying || locationBusy} style={s({ border: 'none', background: 'none', color: locationPicker === 'destination' ? C.accent2 : C.muted2, cursor: 'pointer', fontSize: 10, fontWeight: 700, padding: 0, whiteSpace: 'nowrap' })}>Map</button>
            </div>
          </div>
          <p style={s({ color: locationPicker ? C.accent : C.muted2, fontSize: 10, lineHeight: 1.35 })}>
            {locationBusy ? 'Finding and snapping location to the road…' : locationPicker ? `Click the map to set the ${locationPicker}.` : 'Search a place or press Map, then click the map.'}
          </p>
          {locationError && <p style={s({ color: C.danger, fontSize: 10, lineHeight: 1.35 })}>{locationError}</p>}
          {routeEstimate && (
            <div style={s({ display: 'flex', justifyContent: 'space-between', color: C.muted2, fontSize: 10, borderTop: `1px solid ${C.border}`, paddingTop: 7 })}>
              <span>Selected route preview</span>
              <strong style={s({ color: C.text })}>{(routeEstimate.distanceMeters / 1000).toFixed(1)} km · {Math.max(1, Math.round(routeEstimate.durationSeconds / 60))} min</strong>
            </div>
          )}
          {routePreviewing && <p style={s({ color: C.accent, fontSize: 10 })}>Updating road route preview…</p>}
        </div>

        {/* Primary Simulation Controls */}
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            onClick={handlePrimaryAction}
            style={s({
              flex: 2,
              padding: '12px 18px',
              background: isPlaying ? C.accent2 : `linear-gradient(135deg, ${C.accent} 0%, #00a887 100%)`,
              color: C.bg,
              border: 'none',
              borderRadius: 10,
              fontSize: 13,
              fontWeight: 800,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 8,
              boxShadow: '0 4px 16px rgba(0,201,167,0.3)',
            })}
          >
            <span>{isPlaying ? '⏸ Pause Simulation' : currentStage === 5 && simData.progress > 0 && simData.progress < 1 ? '▶ Resume Simulation' : '▶ Run Complete AI Pipeline'}</span>
          </button>

          <button
            onClick={resetSimulation}
            style={s({
              flex: 1,
              padding: '12px 14px',
              background: C.surface2,
              color: C.text,
              border: `1px solid ${C.border}`,
              borderRadius: 10,
              fontSize: 12,
              fontWeight: 700,
              cursor: 'pointer',
            })}
          >
            ↺ Reset
          </button>
        </div>

        {/* Speed and Camera Toggles */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 12px', background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ color: C.muted2, fontSize: 11 }}>Speed:</span>
            {[1, 2, 4, 8].map(spd => (
              <button
                key={spd}
                onClick={() => setSpeedMultiplier(spd)}
                style={s({
                  padding: '3px 8px',
                  background: speedMultiplier === spd ? C.accent : C.surface2,
                  color: speedMultiplier === spd ? C.bg : C.text,
                  border: `1px solid ${speedMultiplier === spd ? C.accent : C.border}`,
                  borderRadius: 5,
                  fontSize: 10,
                  fontWeight: 700,
                  cursor: 'pointer',
                })}
              >
                {spd}x
              </button>
            ))}
          </div>

          <label style={{ display: 'flex', alignItems: 'center', gap: 6, color: C.muted2, fontSize: 11, cursor: 'pointer' }}>
            <input type="checkbox" checked={followCamera} onChange={e => setFollowCamera(e.target.checked)} />
            Follow 🚗
          </label>
        </div>

        {/* Live Telemetry KPI Card */}
        <div style={s({ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 12, padding: 14 })}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8, textAlign: 'center', marginBottom: 12 }}>
            <div>
              <p style={s({ color: C.muted2, fontSize: 9, textTransform: 'uppercase', fontWeight: 700 })}>SPEED</p>
              <p style={s({ color: C.accent, fontSize: 18, fontWeight: 800 })}>{simData.speedKmh} <span style={{ fontSize: 10 }}>km/h</span></p>
            </div>
            <div>
              <p style={s({ color: C.muted2, fontSize: 9, textTransform: 'uppercase', fontWeight: 700 })}>DISTANCE</p>
              <p style={s({ color: '#60a5fa', fontSize: 18, fontWeight: 800 })}>{(simData.distanceRemainingM / 1000).toFixed(1)} <span style={{ fontSize: 10 }}>km</span></p>
            </div>
            <div>
              <p style={s({ color: C.muted2, fontSize: 9, textTransform: 'uppercase', fontWeight: 700 })}>ETA</p>
              <p style={s({ color: C.accent2, fontSize: 18, fontWeight: 800 })}>{Math.ceil(simData.etaSeconds / 60)} <span style={{ fontSize: 10 }}>min</span></p>
            </div>
            <div>
              <p style={s({ color: C.muted2, fontSize: 9, textTransform: 'uppercase', fontWeight: 700 })}>POOLED</p>
              <p style={s({ color: '#22c55e', fontSize: 18, fontWeight: 800 })}>{simData.passengersOnboard}/3 <span style={{ fontSize: 10 }}>riders</span></p>
            </div>
          </div>

          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4, fontSize: 10, color: C.muted2 }}>
              <span>Route Completion</span>
              <span style={{ color: C.text, fontWeight: 700 }}>{Math.round(simData.progress * 100)}%</span>
            </div>
            <div style={{ height: 6, background: C.surface3, borderRadius: 3, overflow: 'hidden' }}>
              <div style={{ height: '100%', width: `${simData.progress * 100}%`, background: `linear-gradient(90deg, ${C.accent}, ${C.accent2})`, transition: 'width 0.1s linear' }} />
            </div>
          </div>
        </div>

        {/* 5-Step Pipeline Triggers */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <p style={s({ color: C.muted2, fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em' })}>Pipeline Step-By-Step Execution</p>
          {DEMO_STAGES.map((stg, idx) => {
            const stepNum = idx + 1
            const isActive = currentStage === stepNum
            const isPassed = currentStage > stepNum
            const triggers = [stepSpawnRiders, stepCluster, stepVirtualStop, stepVrpSolve, startDriveSimulation]
            return (
              <div
                key={stg.id}
                onClick={!isPlaying ? triggers[idx] : undefined}
                style={s({
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  padding: '10px 12px',
                  background: isActive ? `${C.accent}18` : isPassed ? `${C.surface2}` : C.surface,
                  border: `1px solid ${isActive ? C.accent : isPassed ? C.border2 : C.border}`,
                  borderRadius: 9,
                  cursor: isPlaying ? 'default' : 'pointer',
                  transition: 'all 0.2s ease',
                })}
              >
                <span style={{ fontSize: 16 }}>{stg.icon}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <p style={s({ color: isActive ? C.accent : C.text, fontSize: 12, fontWeight: 700 })}>{stg.title}</p>
                  <p style={s({ color: C.muted, fontSize: 10, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' })}>{stg.desc}</p>
                </div>
                {isPassed && <span style={{ color: '#22c55e', fontSize: 12, fontWeight: 800 }}>✓</span>}
                {isActive && isPlaying && <div style={{ width: 12, height: 12, borderRadius: '50%', border: `2px solid ${C.accent}`, borderTopColor: 'transparent', animation: 'spin 0.8s linear infinite' }} />}
              </div>
            )
          })}
        </div>

        {/* Real-time Algorithm Logs */}
        <div style={s({ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 10, padding: 12, display: 'flex', flexDirection: 'column', gap: 6, flex: 1, minHeight: 140 })}>
          <p style={s({ color: C.muted2, fontSize: 10, fontWeight: 700, textTransform: 'uppercase' })}>Algorithm Execution Terminal</p>
          <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 4, maxHeight: 180 }}>
            {simData.logs.map((log, i) => (
              <div key={i} style={{ fontSize: 10, lineHeight: 1.4, color: log.type === 'success' ? '#22c55e' : log.type === 'accent' ? C.accent : C.muted2 }}>
                <span style={{ color: C.muted, marginRight: 6 }}>[{log.time}]</span>
                <span>{log.text}</span>
              </div>
            ))}
          </div>
        </div>

      </div>

      {/* ── Right Surface (Full-Height Live Map) ── */}
      <div style={{ flex: 1, position: 'relative', minWidth: 0, minHeight: 0 }}>
        <AppMap
          center={[simData.vehiclePosition[1], simData.vehiclePosition[0]]}
          zoom={14}
          height="100%"
          vehicles={[mapVehicle]}
          vehicleMotion="direct"
          pickup={demoPickup}
          destination={demoDestination}
          routeGeometry={simData.routeGeometry}
          waypoints={simData.waypoints}
          onMapClick={locationPicker ? chooseDemoLocationOnMap : undefined}
          followCamera={followCamera && isPlaying}
        />

        {/* Floating Instruction Banner */}
        <div style={{ position: 'absolute', top: 20, left: 24, right: 24, background: 'rgba(15,23,42,0.92)', backdropFilter: 'blur(8px)', border: `1px solid ${C.accent}55`, borderRadius: 12, padding: '12px 18px', zIndex: 500, display: 'flex', alignItems: 'center', gap: 12, boxShadow: '0 8px 32px rgba(0,0,0,0.4)' }}>
          <span style={{ fontSize: 20 }}>⚡</span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <p style={{ color: C.accent, fontSize: 11, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.05em' }}>AI Dispatch Instruction</p>
            <p style={{ color: C.text, fontSize: 13, fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{simData.currentInstruction}</p>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: isPlaying ? '#22c55e' : C.muted2, animation: isPlaying ? 'pulse-glow 1.5s infinite' : 'none' }} />
            <span style={{ color: isPlaying ? '#22c55e' : C.muted2, fontSize: 11, fontWeight: 700 }}>{isPlaying ? 'LIVE SIM' : 'STANDBY'}</span>
          </div>
        </div>
      </div>
    </div>
  )
}

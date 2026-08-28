import { useState, useEffect, useRef, useCallback } from 'react'
import { C, s } from '../ui/tokens.js'
import { ridesApi, trackingApi, routeApi, vehiclesApi, createTrackingWS } from '../services/api.js'
import { useAuth } from '@clerk/clerk-react'
import AppMap from '../components/AppMap'
import { DEMO_PRESETS } from '../config/demoPresets.js'

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
  const simTimerRef = useRef(null)
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

  // Interactive Driver Route Drive Simulation
  const toggleDriveSimulation = () => {
    if (simActive) {
      if (simTimerRef.current) clearInterval(simTimerRef.current)
      setSimActive(false)
      setSimSpeed(0)
      toast('info', 'GPS Simulation Paused')
      return
    }

    setSimActive(true)
    toast('success', 'Driver Navigation Active', 'Simulating live road traversal to Virtual Stop #1 and MG Road.')
    const path = DEMO_PRESETS.indiranagar.roadPath
    let p = simProgress
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
        toast('success', 'Route Navigation Finished', 'All dropoffs completed.')
        return
      }

      setSimProgress(p)
      const totalSegments = path.length - 1
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

      // Push telemetry
      if (myVehicle) {
        setMyVehicle(prev => ({ ...prev, lat: currLat, lng: currLng }))
      }
    }, 80)
  }

  useEffect(() => {
    return () => {
      if (simTimerRef.current) clearInterval(simTimerRef.current)
    }
  }, [])

  if (view === 'driver-map') {
    return (
      <LiveMapView
        tracking={tracking}
        myVehicle={myVehicle}
        onBack={()=>setView('driver-home')}
        onUpdateLoc={updateLocation}
        updating={updatingLoc}
        simActive={simActive}
        simProgress={simProgress}
        simSpeed={simSpeed}
        simCoords={simCoords}
        simBearing={simBearing}
        onToggleSim={toggleDriveSimulation}
      />
    )
  }

  if (view === 'driver-routes') {
    return <RoutesView routes={routes} loading={loading} onBack={()=>setView('driver-home')} onStartNav={()=>{ setView('driver-map'); toggleDriveSimulation() }} />
  }

  // Driver dashboard home
  const activeVehicles = tracking.vehicles.filter((v) => v.status !== 'idle').length
  const pendingRides   = rides.filter((r) => r.status === 'assigned').length

  return (
    <div style={s({ padding:28 })}>
      <h1 style={s({ color:C.text, fontSize:22, fontWeight:800, fontFamily:'Bricolage Grotesque,sans-serif', marginBottom:4 })}>Driver Dashboard</h1>
      <p style={s({ color:C.muted, fontSize:13, marginBottom:24 })}>Welcome back, {user.name.split(' ')[0]} · Fleet Dispatch Connected</p>

      {/* Stats */}
      <div style={s({ display:'flex', gap:14, marginBottom:24, flexWrap:'wrap' })}>
        {[
          { label:'My Vehicle',      val: myVehicle?.license_plate || 'KA-01-TEST-99', icon:'🚗', col:C.accent },
          { label:'Active Vehicles', val: String(activeVehicles || 1),                 icon:'📡', col:'#60a5fa' },
          { label:'Assigned Rides',  val: String(pendingRides || 3),                  icon:'🛻', col:C.accent2 },
          { label:'My Routes',       val: String(routes.length || 1),                 icon:'📍', col:C.accent3 },
        ].map(stat => (
          <div key={stat.label} style={s({ flex:'1 1 160px', background:C.surface, border:`1px solid ${C.border}`, borderRadius:12, padding:'16px 18px' })}>
            <div style={s({ display:'flex', justifyContent:'space-between', alignItems:'flex-start' })}>
              <p style={s({ color:C.muted2, fontSize:11, fontWeight:700, textTransform:'uppercase', letterSpacing:'0.07em' })}>{stat.label}</p>
              <span style={{ fontSize:18 }}>{stat.icon}</span>
            </div>
            <p style={s({ color:stat.col, fontSize:24, fontWeight:800, fontFamily:'Bricolage Grotesque,sans-serif', marginTop:8 })}>{stat.val}</p>
          </div>
        ))}
      </div>

      {/* Quick actions */}
      <div style={s({ display:'flex', gap:10, marginBottom:24, flexWrap:'wrap' })}>
        <button onClick={()=>setView('driver-map')} style={s({ padding:'10px 18px', background:C.accent, color:C.bg, border:'none', borderRadius:9, fontSize:13, fontWeight:800, cursor:'pointer', display:'flex', alignItems:'center', gap:6 })}>
          <span>🧭</span>
          <span>Open Live Navigation Map</span>
        </button>
        <button onClick={updateLocation} disabled={updatingLoc} style={s({ padding:'10px 18px', background:C.surface2, color:C.text, border:`1px solid ${C.border2}`, borderRadius:9, fontSize:13, fontWeight:600, cursor:'pointer' })}>
          {updatingLoc ? '⏳ Updating…' : '📡 Push GPS Telemetry'}
        </button>
        <button onClick={()=>setView('driver-routes')} style={s({ padding:'10px 18px', background:C.surface2, color:C.text, border:`1px solid ${C.border2}`, borderRadius:9, fontSize:13, fontWeight:600, cursor:'pointer' })}>📍 My Assigned Routes</button>
      </div>

      <div style={s({ display:'flex', gap:20, flexWrap:'wrap' })}>
        {/* Assigned rides */}
        <div style={s({ flex:'1 1 380px', background:C.surface, border:`1px solid ${C.border}`, borderRadius:14, padding:20 })}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
            <p style={s({ color:C.text, fontSize:14, fontWeight:700 })}>Assigned Shared Passenger Manifest</p>
            <span style={s({ fontSize: 10, color: C.accent, fontWeight: 800, background: `${C.accent}18`, padding: '2px 8px', borderRadius: 5 })}>3 Pooled</span>
          </div>

          <div style={s({ display:'flex', flexDirection:'column', gap:8 })}>
            {[
              { id: 101, name: 'Ananya Sharma', pickup: 'Indiranagar 100 Feet Rd', dest: 'MG Road Metro', status: 'assigned', fare: '₹45' },
              { id: 102, name: 'Rohan Mehta', pickup: 'Indiranagar 12th Main', dest: 'Church Street', status: 'assigned', fare: '₹42' },
              { id: 103, name: 'Priya Iyer', pickup: 'CMH Road Junction', dest: 'Brigade Road', status: 'assigned', fare: '₹48' },
            ].map(ride => (
              <div key={ride.id} style={s({ padding:'12px 14px', background:C.surface2, border:`1px solid ${C.border}`, borderRadius:9 })}>
                <div style={s({ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:6 })}>
                  <p style={s({ color:C.text, fontSize:12, fontWeight:700 })}>👤 {ride.name} · {ride.fare}</p>
                  <StatusBadge status={ride.status} />
                </div>
                <p style={s({ color:C.muted2, fontSize:11, marginBottom:4 })}>📍 {ride.pickup}</p>
                <p style={s({ color:C.muted2, fontSize:11, marginBottom:10 })}>🎯 {ride.dest}</p>
                <div style={s({ display:'flex', gap:6 })}>
                  <ActionBtn label="Board" color={C.accent} onClick={()=>updateRideStatus(ride.id,'in_progress')} />
                  <ActionBtn label="Dropoff" color='#22c55e' onClick={()=>updateRideStatus(ride.id,'completed')} />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Vehicle fleet status */}
        <div style={s({ flex:'1 1 280px', background:C.surface, border:`1px solid ${C.border}`, borderRadius:14, padding:20 })}>
          <p style={s({ color:C.text, fontSize:14, fontWeight:700, marginBottom:14 })}>Vehicle Diagnostics & Status</p>
          <div style={s({ display:'flex', flexDirection:'column', gap:10 })}>
            <div style={s({ padding: '12px', background: C.surface2, borderRadius: 8, border: `1px solid ${C.border}` })}>
              <p style={s({ color: C.muted2, fontSize: 11, fontWeight: 700 })}>ASSIGNED VEHICLE</p>
              <p style={s({ color: C.text, fontSize: 16, fontWeight: 800, marginTop: 2 })}>{myVehicle?.license_plate || 'KA-01-TEST-99'}</p>
              <p style={s({ color: C.muted, fontSize: 11 })}>Tata Tigor EV · Capacity: 6 passengers</p>
            </div>
            <div style={s({ padding: '12px', background: C.surface2, borderRadius: 8, border: `1px solid ${C.border}` })}>
              <p style={s({ color: C.muted2, fontSize: 11, fontWeight: 700 })}>BATTERY / RANGE</p>
              <p style={s({ color: '#22c55e', fontSize: 16, fontWeight: 800, marginTop: 2 })}>88% · 195 km remaining</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── Live Navigation Map View ──────────────────────────────────────────────────
function LiveMapView({ myVehicle, onBack, onUpdateLoc, updating, simActive, simProgress, simSpeed, simCoords, simBearing, onToggleSim }) {
  const roadPath = DEMO_PRESETS.indiranagar.roadPath
  const vehicle = {
    id: myVehicle?.id || 99,
    license_plate: myVehicle?.license_plate || 'KA-01-TEST-99',
    status: simActive ? 'active' : 'idle',
    lat: simCoords[1],
    lng: simCoords[0],
  }

  const waypoints = [
    { lat: 12.9784, lng: 77.6408, waypoint_type: 'depot', label: 'Depot' },
    { lat: 12.97192, lng: 77.64124, waypoint_type: 'pickup', label: 'Stop 1' },
    { lat: 12.9756, lng: 77.6066, waypoint_type: 'destination', label: 'MG Road' },
  ]

  let navInstruction = 'Head South on 100 Feet Rd towards Virtual Stop #1'
  if (simProgress > 0.3 && simProgress < 0.7) navInstruction = 'Turn Right onto Old Airport Rd / Trinity Corridor'
  if (simProgress >= 0.7) navInstruction = 'Arriving at Destination: MG Road Metro Station'

  return (
    <div style={{ display:'flex', flexDirection:'column', flex:1, minHeight:0, position: 'relative' }}>
      {/* Turn-by-Turn Navigation HUD */}
      <div style={{ padding:'12px 20px', borderBottom:`1px solid var(--border)`, display:'flex', alignItems:'center', gap:14, background:'var(--bg2)', flexShrink:0, zIndex: 10 }}>
        <button onClick={onBack} style={s({ background:'none', border:'none', color:C.muted2, cursor:'pointer', fontSize:13 })}>← Back</button>
        
        {/* Maneuver box */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flex: 1, minWidth: 0 }}>
          <div style={{ width: 34, height: 34, borderRadius: 8, background: C.accent, color: C.bg, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18, fontWeight: 800 }}>
            {simProgress > 0.3 ? '↱' : '↑'}
          </div>
          <div>
            <p style={s({ color: C.text, fontSize: 13, fontWeight: 800 })}>{navInstruction}</p>
            <p style={s({ color: C.muted2, fontSize: 11 })}>{simActive ? `${simSpeed} km/h · ${Math.round((1 - simProgress) * 4.2 * 10) / 10} km to destination` : 'Ready to start driving'}</p>
          </div>
        </div>

        {/* Simulation Play/Pause button */}
        <button
          onClick={onToggleSim}
          style={s({
            padding: '8px 16px',
            background: simActive ? C.accent2 : `linear-gradient(135deg, ${C.accent} 0%, #00a887 100%)`,
            color: C.bg,
            border: 'none',
            borderRadius: 8,
            fontSize: 12,
            fontWeight: 800,
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: 6,
          })}
        >
          <span>{simActive ? '⏸ Pause GPS Drive' : '▶ Start GPS Drive Simulation'}</span>
        </button>

        <button onClick={onUpdateLoc} disabled={updating} style={s({ padding:'8px 14px', background:C.surface2, color:C.text, border:`1px solid ${C.border2}`, borderRadius:8, fontSize:12, fontWeight:600, cursor:'pointer' })}>
          {updating ? '⏳ Updating…' : '📡 Real GPS'}
        </button>
      </div>

      {/* Map */}
      <div style={{ flex:1, minWidth:0, minHeight:0, position: 'relative' }}>
        <AppMap
          center={[simCoords[1], simCoords[0]]}
          zoom={14}
          height="100%"
          vehicles={[vehicle]}
          routeGeometry={roadPath}
          waypoints={waypoints}
          followCamera={simActive}
        />

        {/* Floating Speedometer & Status HUD */}
        {simActive && (
          <div style={{ position: 'absolute', bottom: 24, left: 24, background: 'rgba(15,23,42,0.85)', backdropFilter: 'blur(8px)', border: `1px solid ${C.accent}55`, borderRadius: 14, padding: '12px 18px', zIndex: 500, display: 'flex', alignItems: 'center', gap: 16, boxShadow: '0 8px 32px rgba(0,0,0,0.4)' }}>
            <div>
              <p style={{ color: C.muted2, fontSize: 10, fontWeight: 700, textTransform: 'uppercase' }}>SPEED</p>
              <p style={{ color: C.accent, fontSize: 24, fontWeight: 800, fontFamily: 'Bricolage Grotesque,sans-serif' }}>{simSpeed} <span style={{ fontSize: 12 }}>km/h</span></p>
            </div>
            <div style={{ height: 30, width: 1, background: C.border }} />
            <div>
              <p style={{ color: C.muted2, fontSize: 10, fontWeight: 700, textTransform: 'uppercase' }}>NEXT STOP</p>
              <p style={{ color: C.text, fontSize: 12, fontWeight: 700 }}>Indiranagar 100 Ft Rd (Stop 1)</p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Routes View ──────────────────────────────────────────────────────────────
function RoutesView({ routes, loading, onBack, onStartNav }) {
  const [selected, setSelected] = useState(routes[0] || null)
  return (
    <div style={s({ padding:28, maxWidth:860 })}>
      <div style={s({ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:20 })}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <button onClick={onBack} style={s({ background:'none', border:'none', color:C.muted2, cursor:'pointer', fontSize:13 })}>← Back</button>
          <h1 style={s({ color:C.text, fontSize:20, fontWeight:800, fontFamily:'Bricolage Grotesque,sans-serif' })}>My Assigned Routes</h1>
        </div>
        <button onClick={onStartNav} style={s({ padding: '9px 16px', background: C.accent, color: C.bg, border: 'none', borderRadius: 8, fontSize: 12, fontWeight: 800, cursor: 'pointer' })}>
          🧭 Start Route Navigation
        </button>
      </div>

      <div style={s({ display:'flex', gap:16, flexWrap: 'wrap' })}>
        <div style={s({ flex:'1 1 300px' })}>
          {loading && <p style={s({ color:C.muted, fontSize:13 })}>Loading…</p>}
          <div style={s({ display:'flex', flexDirection:'column', gap:8 })}>
            <div onClick={()=>setSelected(routes[0])} style={s({ padding:'14px 16px', background:C.surface2, border:`1px solid ${C.accent}`, borderRadius:10, cursor:'pointer' })}>
              <div style={s({ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:4 })}>
                <p style={s({ color:C.text, fontSize:13, fontWeight:800 })}>Indiranagar → MG Road Multi-Stop</p>
                <span style={s({ fontSize:10, color:C.accent, background:`${C.accent}18`, padding:'2px 7px', borderRadius:5, fontWeight:700 })}>ACTIVE ROUTE</span>
              </div>
              <p style={s({ color:C.muted2, fontSize:11 })}>Vehicle KA-01-TEST-99 · 4.2 km · 3 Stops</p>
              <p style={s({ color:C.muted, fontSize:11, marginTop: 4 })}>Optimized by OR-Tools CVRP</p>
            </div>
          </div>
        </div>

        {/* Route Detail Map Preview */}
        <div style={s({ flex:'1 1 340px', background:C.surface, border:`1px solid ${C.border}`, borderRadius:12, padding:18, display:'flex', flexDirection:'column', gap:14 })}>
          <p style={s({ color:C.text, fontSize:13, fontWeight:700 })}>Route Map & Waypoints</p>
          <div style={{ height: 260, borderRadius: 8, overflow: 'hidden' }}>
            <AppMap
              center={[12.9756, 77.6250]}
              zoom={13}
              height="100%"
              routeGeometry={DEMO_PRESETS.indiranagar.roadPath}
              waypoints={[
                { lat: 12.9784, lng: 77.6408, waypoint_type: 'depot', label: 'Depot' },
                { lat: 12.97192, lng: 77.64124, waypoint_type: 'pickup', label: 'Stop 1' },
                { lat: 12.9756, lng: 77.6066, waypoint_type: 'destination', label: 'MG Road' },
              ]}
            />
          </div>
          <button onClick={onStartNav} style={s({ width: '100%', padding: '10px', background: C.accent, color: C.bg, border: 'none', borderRadius: 8, fontSize: 12, fontWeight: 800, cursor: 'pointer' })}>
            ▶ Launch Interactive Simulation
          </button>
        </div>
      </div>
    </div>
  )
}

function StatusBadge({ status }) {
  const col = status === 'completed' ? '#22c55e' : status === 'in_progress' ? '#00c9a7' : '#60a5fa'
  return <span style={s({ fontSize:10, fontWeight:700, textTransform:'uppercase', color:col, background:col+'22', padding:'2px 7px', borderRadius:5 })}>{status.replace('_',' ')}</span>
}

function ActionBtn({ label, color, onClick }) {
  return (
    <button onClick={onClick} style={s({ padding:'5px 10px', background:`${color}20`, border:`1px solid ${color}60`, color, borderRadius:6, fontSize:11, fontWeight:700, cursor:'pointer' })}>{label}</button>
  )
}

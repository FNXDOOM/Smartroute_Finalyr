import { useState, useEffect, useRef, useCallback } from 'react'
import { C, s } from '../ui/tokens.js'
import { ridesApi, trackingApi, routeApi, vehiclesApi, createTrackingWS } from '../services/api.js'
import { useAuth } from '@clerk/clerk-react'
import AppMap from '../components/AppMap'

export default function DriverView({ user, view, setView, toast }) {
  const { getToken } = useAuth()
  const [vehicles,   setVehicles]   = useState([])
  const [rides,      setRides]      = useState([])
  const [routes,     setRoutes]     = useState([])
  const [tracking,   setTracking]   = useState({ vehicles:[], events:[] })
  const [loading,    setLoading]    = useState(true)
  const [myVehicle,  setMyVehicle]  = useState(null)
  const [updatingLoc,setUpdatingLoc]= useState(false)
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
          if (msg.type === 'tracking_snapshot' || msg.type === 'vehicle_location_update') {
            setTracking({ vehicles: msg.vehicles || [], events: msg.events || [] })
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
      navigator.geolocation.getCurrentPosition(async (pos) => {
        await trackingApi.updateLocation(myVehicle.id, { lat: pos.coords.latitude, lng: pos.coords.longitude })
        toast('success','Location updated')
        setUpdatingLoc(false)
      }, async () => {
        // fallback: use fixed Bengaluru coords with slight randomness for demo
        const lat = 12.9784 + (Math.random()-0.5)*0.05
        const lng = 77.6408 + (Math.random()-0.5)*0.05
        await trackingApi.updateLocation(myVehicle.id, { lat, lng })
        toast('success','Location updated (simulated)')
        setUpdatingLoc(false)
      })
    } catch(e) { toast('error','Failed to update',e?.response?.data?.detail||''); setUpdatingLoc(false) }
  }

  const updateRideStatus = async (rideId, status) => {
    try {
      await ridesApi.updateStatus(rideId, status)
      setRides(prev => prev.map(r => r.id===rideId ? {...r, status} : r))
      toast('success', `Ride #${rideId} → ${status}`)
    } catch(e) { toast('error','Failed', e?.response?.data?.detail||'') }
  }

  if (view === 'driver-map')    return <LiveMapView tracking={tracking} myVehicle={myVehicle} onBack={()=>setView('driver-home')} onUpdateLoc={updateLocation} updating={updatingLoc} />
  if (view === 'driver-routes') return <RoutesView routes={routes} loading={loading} onBack={()=>setView('driver-home')} />

  // Driver dashboard home
  const activeVehicles = tracking.vehicles.filter((v) => v.status !== 'idle').length
  const pendingRides   = rides.filter((r) => r.status === 'assigned').length

  return (
    <div style={s({ padding:28 })}>
      <h1 style={s({ color:C.text, fontSize:22, fontWeight:800, fontFamily:'Bricolage Grotesque,sans-serif', marginBottom:4 })}>Driver Dashboard</h1>
      <p style={s({ color:C.muted, fontSize:13, marginBottom:24 })}>Welcome back, {user.name.split(' ')[0]}</p>

      {/* Stats */}
      <div style={s({ display:'flex', gap:14, marginBottom:24, flexWrap:'wrap' })}>
        {[
          { label:'My Vehicle',      val: myVehicle?.license_plate || '—',  icon:'🚗', col:C.accent },
          { label:'Active Vehicles', val: String(activeVehicles),             icon:'📡', col:'#60a5fa' },
          { label:'Assigned Rides',  val: String(pendingRides),              icon:'🛻', col:C.accent2 },
          { label:'My Routes',       val: String(routes.length),             icon:'📍', col:C.accent3 },
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
        <button onClick={()=>setView('driver-map')} style={s({ padding:'10px 18px', background:C.accent, color:C.bg, border:'none', borderRadius:9, fontSize:13, fontWeight:700, cursor:'pointer' })}>🗺️ Live Map</button>
        <button onClick={updateLocation} disabled={updatingLoc} style={s({ padding:'10px 18px', background:C.surface2, color:C.text, border:`1px solid ${C.border2}`, borderRadius:9, fontSize:13, fontWeight:600, cursor:'pointer' })}>
          {updatingLoc ? '⏳ Updating…' : '📡 Update Location'}
        </button>
        <button onClick={()=>setView('driver-routes')} style={s({ padding:'10px 18px', background:C.surface2, color:C.text, border:`1px solid ${C.border2}`, borderRadius:9, fontSize:13, fontWeight:600, cursor:'pointer' })}>📍 My Routes</button>
      </div>

      <div style={s({ display:'flex', gap:20, flexWrap:'wrap' })}>
        {/* Assigned rides */}
        <div style={s({ flex:'1 1 380px', background:C.surface, border:`1px solid ${C.border}`, borderRadius:14, padding:20 })}>
          <p style={s({ color:C.text, fontSize:14, fontWeight:700, marginBottom:14 })}>Assigned Rides</p>
          {loading && <p style={s({ color:C.muted, fontSize:13 })}>Loading…</p>}
          {!loading && rides.length === 0 && <p style={s({ color:C.muted, fontSize:13 })}>No assigned rides.</p>}
          <div style={s({ display:'flex', flexDirection:'column', gap:8 })}>
            {rides.slice(0,8).map(ride => (
              <div key={ride.id} style={s({ padding:'12px 14px', background:C.surface2, border:`1px solid ${C.border}`, borderRadius:9 })}>
                <div style={s({ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:6 })}>
                  <p style={s({ color:C.text, fontSize:12, fontWeight:700 })}>#{ride.id} — {ride.ride_option_name||'Standard'}</p>
                  <StatusBadge status={ride.status} />
                </div>
                <p style={s({ color:C.muted2, fontSize:11, marginBottom:8 })}>📍 {ride.pickup_label||`${ride.pickup_lat?.toFixed(3)},${ride.pickup_lng?.toFixed(3)}`}</p>
                <p style={s({ color:C.muted2, fontSize:11, marginBottom:10 })}>🎯 {ride.destination_label||`${ride.dest_lat?.toFixed(3)},${ride.dest_lng?.toFixed(3)}`}</p>
                <div style={s({ display:'flex', gap:6 })}>
                  {ride.status === 'assigned'     && <ActionBtn label="Start"    color={C.accent}  onClick={()=>updateRideStatus(ride.id,'in_progress')} />}
                  {ride.status === 'in_progress'  && <ActionBtn label="Complete" color='#22c55e'    onClick={()=>updateRideStatus(ride.id,'completed')} />}
                  {['assigned','in_progress'].includes(ride.status) && <ActionBtn label="Arriving" color='#60a5fa' onClick={()=>updateRideStatus(ride.id,'arriving')} />}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Vehicle fleet status */}
        <div style={s({ flex:'1 1 280px', background:C.surface, border:`1px solid ${C.border}`, borderRadius:14, padding:20 })}>
          <p style={s({ color:C.text, fontSize:14, fontWeight:700, marginBottom:14 })}>Fleet Status</p>
          <div style={s({ display:'flex', flexDirection:'column', gap:6 })}>
            {vehicles.slice(0,8).map(v => (
              <div key={v.id} style={s({ display:'flex', justifyContent:'space-between', alignItems:'center', padding:'9px 12px', background:C.surface2, border:`1px solid ${C.border}`, borderRadius:8 })}>
                <div>
                  <p style={s({ color:C.text, fontSize:12, fontWeight:700 })}>{v.license_plate}</p>
                  <p style={s({ color:C.muted, fontSize:11 })}>Cap: {v.capacity}</p>
                </div>
                <StatusBadge status={v.status} />
              </div>
            ))}
            {vehicles.length === 0 && !loading && <p style={s({ color:C.muted, fontSize:13 })}>No vehicles.</p>}
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── Live Map View ─────────────────────────────────────────────────────────────
function LiveMapView({ tracking, myVehicle, onBack, onUpdateLoc, updating }) {
  const events = tracking.events || []
  const vehicles = tracking.vehicles || []
  const mapCenter = myVehicle?.lat
    ? [myVehicle.lat, myVehicle.lng]
    : vehicles.find((v)=>v.lat)
      ? [vehicles.find((v)=>v.lat).lat, vehicles.find((v)=>v.lat).lng]
      : [12.9784, 77.6408]

  return (
    <div style={{ display:'flex', flexDirection:'column', flex:1, minHeight:0 }}>
      {/* Header */}
      <div style={{ padding:'12px 20px', borderBottom:`1px solid var(--border)`, display:'flex', alignItems:'center', gap:12, background:'var(--bg2)', flexShrink:0 }}>
        <button onClick={onBack} style={s({ background:'none', border:'none', color:C.muted2, cursor:'pointer', fontSize:13 })}>← Back</button>
        <p style={s({ color:C.text, fontSize:14, fontWeight:700 })}>Live Fleet Map</p>
        <span style={s({ color:C.accent, fontSize:12 })}>● {vehicles.filter((v)=>v.lat).length} vehicles live</span>
        <button onClick={onUpdateLoc} disabled={updating} style={s({ marginLeft:'auto', padding:'7px 14px', background:C.accent, color:C.bg, border:'none', borderRadius:7, fontSize:12, fontWeight:700, cursor:'pointer' })}>
          {updating ? '⏳ Updating…' : '📡 Push My Location'}
        </button>
      </div>

      {/* Map + events sidebar */}
      <div style={{ flex:1, display:'flex', overflow:'hidden', minHeight:0 }}>
        <div style={{ flex:1, minWidth:0, minHeight:0 }}>
          <AppMap center={mapCenter} zoom={13} height="100%" vehicles={vehicles} />
        </div>

        {/* Events sidebar */}
        <div style={s({ width:260, flexShrink:0, overflowY:'auto', background:C.bg2, borderLeft:`1px solid ${C.border}`, padding:14 })}>
          <p style={s({ color:C.text, fontSize:12, fontWeight:700, marginBottom:10 })}>📡 Live Events</p>
          {events.length === 0 && <p style={s({ color:C.muted, fontSize:12 })}>Waiting for events…</p>}
          <div style={s({ display:'flex', flexDirection:'column', gap:6 })}>
            {events.slice(0,20).map((e) => (
              <div key={e.id} style={s({ padding:'8px 10px', background:C.surface, borderRadius:7, borderLeft:`3px solid ${C.accent}40` })}>
                <p style={s({ color:C.text, fontSize:11, fontWeight:600 })}>{e.event_type?.replace(/_/g,' ')}</p>
                <p style={s({ color:C.muted2, fontSize:10, marginTop:2 })}>V#{e.vehicle_id} · {e.lat?.toFixed(4)}, {e.lng?.toFixed(4)}</p>
                <p style={s({ color:C.muted, fontSize:10 })}>{e.created_at ? new Date(e.created_at).toLocaleTimeString() : ''}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── Routes View ──────────────────────────────────────────────────────────────
function RoutesView({ routes, loading, onBack }) {
  const [selected, setSelected] = useState(null)
  return (
    <div style={s({ padding:28, maxWidth:860 })}>
      <div style={s({ display:'flex', alignItems:'center', gap:12, marginBottom:20 })}>
        <button onClick={onBack} style={s({ background:'none', border:'none', color:C.muted2, cursor:'pointer', fontSize:13 })}>← Back</button>
        <h1 style={s({ color:C.text, fontSize:20, fontWeight:800, fontFamily:'Bricolage Grotesque,sans-serif' })}>My Routes</h1>
      </div>
      <div style={s({ display:'flex', gap:16 })}>
        <div style={s({ flex:'1 1 300px' })}>
          {loading && <p style={s({ color:C.muted, fontSize:13 })}>Loading…</p>}
          {!loading && routes.length === 0 && <p style={s({ color:C.muted, fontSize:14 })}>No routes yet.</p>}
          <div style={s({ display:'flex', flexDirection:'column', gap:8 })}>
            {routes.map(r => (
              <div key={r.id} onClick={()=>setSelected(r)} style={s({ padding:'12px 14px', background:selected?.id===r.id?C.surface2:C.surface, border:`1px solid ${selected?.id===r.id?C.accent:C.border}`, borderRadius:10, cursor:'pointer' })}>
                <div style={s({ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:4 })}>
                  <p style={s({ color:C.text, fontSize:12, fontWeight:700, fontFamily:'monospace' })}>{r.route_id?.slice(0,22)}</p>
                  <span style={s({ fontSize:10, color:C.accent, background:`${C.accent}18`, padding:'2px 7px', borderRadius:5, fontWeight:700 })}>{r.status}</span>
                </div>
                <p style={s({ color:C.muted2, fontSize:11 })}>Vehicle #{r.vehicle_id} · {r.total_distance_meters ? `${(r.total_distance_meters/1000).toFixed(2)} km` : '—'}</p>
                <p style={s({ color:C.muted, fontSize:11 })}>{r.waypoints?.length || 0} waypoints · {r.created_at ? new Date(r.created_at).toLocaleString() : ''}</p>
              </div>
            ))}
          </div>
        </div>
        {selected && (
          <div style={s({ flex:'1 1 300px', background:C.surface, border:`1px solid ${C.border}`, borderRadius:12, padding:18, display:'flex', flexDirection:'column', gap:14 })}>
            <p style={s({ color:C.text, fontSize:13, fontWeight:700 })}>Route Detail</p>
            <div style={s({ display:'flex', flexDirection:'column', gap:8 })}>
              <InfoRow label="Route ID"    val={selected.route_id} mono />
              <InfoRow label="Vehicle"     val={`#${selected.vehicle_id}`} />
              <InfoRow label="Distance"    val={selected.total_distance_meters ? `${(selected.total_distance_meters/1000).toFixed(2)} km` : '—'} />
              <InfoRow label="Est. time"   val={selected.estimated_duration_seconds ? `${Math.round(selected.estimated_duration_seconds/60)} min` : '—'} />
              <InfoRow label="Waypoints"   val={String(selected.waypoints?.length || 0)} />
            </div>
            {/* Route map */}
            {selected.waypoints?.length > 0 && (
              <AppMap
                center={[selected.waypoints[0].lat, selected.waypoints[0].lng]}
                zoom={13}
                height={260}
                waypoints={selected.waypoints}
              />
            )}
            <p style={s({ color:C.muted2, fontSize:12, fontWeight:700 })}>Waypoints</p>
            <div style={s({ display:'flex', flexDirection:'column', gap:5, maxHeight:200, overflowY:'auto' })}>
              {(selected.waypoints||[]).map((wp, i) => (
                <div key={i} style={s({ display:'flex', alignItems:'center', gap:10, padding:'7px 10px', background:C.surface2, borderRadius:7 })}>
                  <div style={s({ width:22, height:22, borderRadius:'50%', background:wp.waypoint_type==='depot'?C.surface3:`${C.accent}20`, display:'flex', alignItems:'center', justifyContent:'center', fontSize:11, fontWeight:700, color:wp.waypoint_type==='depot'?C.muted:C.accent, flexShrink:0 })}>{i+1}</div>
                  <div>
                    <p style={s({ color:C.text, fontSize:11, fontWeight:600 })}>{wp.waypoint_type.toUpperCase()}</p>
                    <p style={s({ color:C.muted, fontSize:10 })}>{wp.lat?.toFixed(4)}, {wp.lng?.toFixed(4)}</p>
                  </div>
                  {wp.passenger_ids?.length > 0 && <span style={s({ marginLeft:'auto', color:C.muted2, fontSize:10 })}>👤 {wp.passenger_ids.length}</span>}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Shared helpers ───────────────────────────────────────────────────────────
const STATUS_COLOR = {
  pending:'#f59e0b', clustered:'#a78bfa', assigned:'#60a5fa',
  arriving:'#00c9a7', in_progress:'#00c9a7', completed:'#22c55e', cancelled:'#f43f5e',
  idle:'#7a90b0', active:'#00c9a7', en_route:'#60a5fa', offline:'#f43f5e', solved:'#22c55e',
}
function StatusBadge({ status }) {
  const col = STATUS_COLOR[status] || '#7a90b0'
  return <span style={s({ fontSize:10, fontWeight:700, textTransform:'uppercase', letterSpacing:'0.07em', color:col, background:col+'22', padding:'2px 7px', borderRadius:5, flexShrink:0 })}>{status.replace(/_/g,' ')}</span>
}
function ActionBtn({ label, color, onClick }) {
  return <button onClick={onClick} style={s({ padding:'5px 10px', background:color+'22', border:`1px solid ${color}55`, color, fontSize:11, fontWeight:700, borderRadius:6, cursor:'pointer' })}>{label}</button>
}
function InfoRow({ label, val, mono=false }) {
  return (
    <div style={s({ display:'flex', justifyContent:'space-between', alignItems:'center', padding:'7px 10px', background:C.surface2, borderRadius:7 })}>
      <p style={s({ color:C.muted2, fontSize:11 })}>{label}</p>
      <p style={s({ color:C.text, fontSize:12, fontWeight:600, fontFamily:mono?'monospace':'inherit', maxWidth:180, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' })}>{val}</p>
    </div>
  )
}

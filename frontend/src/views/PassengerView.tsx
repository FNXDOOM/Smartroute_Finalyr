import { useState, useEffect, useRef, useCallback } from 'react'
import { useAuth } from '@clerk/clerk-react'
import { C, s, AppUser, View, Toast } from '../SwiftApp'
import { ridesApi, vehiclesApi, geocodeApi, routingApi, createTrackingWS } from '../services/api.js'
import { useWebSocket } from '../hooks/useWebSocket.js'
import AppMap from '../components/AppMap'

interface Props { user:AppUser; view:View; setView:(v:View)=>void; toast:(t:Toast['type'],title:string,body?:string)=>void }

const RIDE_TIERS = [
  { id:'swift-x',   name:'SwiftX',    desc:'Affordable shared ride', eta:'3 min', price:'₹12–15', icon:'S', seats:4 },
  { id:'swift-xl',  name:'SwiftXL',   desc:'Extra space, small group', eta:'6 min', price:'₹18–22', icon:'X', seats:6 },
  { id:'swift-lux', name:'Lux Black', desc:'Premium, top-rated driver', eta:'8 min', price:'₹32–40', icon:'L', seats:4 },
  { id:'swift-moto',name:'Moto',      desc:'Fast, budget solo',        eta:'2 min', price:'₹6–9',   icon:'M', seats:1 },
]

export default function PassengerView({ user, view, setView, toast }: Props) {
  const [trips,    setTrips]    = useState<any[]>([])
  const [loading,  setLoading]  = useState(true)
  const [selected, setSelected] = useState<string>('swift-x')
  const [pickup,   setPickup]   = useState('')
  const [dest,     setDest]     = useState('')
  const [booking,  setBooking]  = useState(false)
  const [activeRide, setActiveRide] = useState<any>(null)
  const [rideVehicle, setRideVehicle] = useState<any>(null)
  const [vehicles, setVehicles] = useState<any[]>([])
  const [pickupPoint, setPickupPoint] = useState({ lat:12.9784, lng:77.6408, label:'Current location' })
  const [destinationPoint, setDestinationPoint] = useState<any>(null)
  const [routeGeometry, setRouteGeometry] = useState<[number,number][]>([])
  const [routeEstimate, setRouteEstimate] = useState<any>(null)
  const [suggestions, setSuggestions] = useState<any[]>([])
  const [suggestionField, setSuggestionField] = useState<'pickup'|'destination'|null>(null)
  const [pickupConfirmed, setPickupConfirmed] = useState(false)
  const [destinationConfirmed, setDestinationConfirmed] = useState(false)
  const [locationError, setLocationError] = useState('')
  const [geocoding, setGeocoding] = useState(false)
  const [gpsActive, setGpsActive] = useState(false)
  const [gpsLoading, setGpsLoading] = useState(false)
  const pollRef = useRef<any>(null)
  const gpsWatchRef = useRef<number | null>(null)
  const gpsReverseDoneRef = useRef(false)
  const { getToken } = useAuth()
  const [trackingToken, setTrackingToken] = useState<string|null>(null)

  useEffect(() => {
    getToken().then(token => setTrackingToken(token)).catch(() => {})
    vehiclesApi.list().then(data => setVehicles(Array.isArray(data) ? data : [])).catch(() => {})
  }, [getToken])

  const handleTrackingMessage = useCallback((message:any) => {
    if (message.type === 'tracking_snapshot') {
      setVehicles(Array.isArray(message.vehicles) ? message.vehicles : [])
    } else if (message.type === 'vehicle_location_update' && message.vehicle) {
      setVehicles(prev => prev.some(v => v.id === message.vehicle.id)
        ? prev.map(v => v.id === message.vehicle.id ? { ...v, ...message.vehicle } : v)
        : [...prev, message.vehicle])
      if (rideVehicle?.id === message.vehicle.id) setRideVehicle((prev:any) => ({ ...prev, ...message.vehicle }))
    }
  }, [rideVehicle?.id])

  useWebSocket(createTrackingWS, trackingToken, handleTrackingMessage, true)

  useEffect(() => () => {
    if (gpsWatchRef.current !== null) navigator.geolocation?.clearWatch(gpsWatchRef.current)
  }, [])

  useEffect(() => {
    const query = suggestionField === 'pickup' ? pickup : dest
    if (!suggestionField || query.trim().length < 3) {
      setSuggestions([])
      return
    }
    const timer = window.setTimeout(() => {
      geocodeApi.suggest(query.trim(), gpsActive ? pickupPoint : undefined)
        .then(results => setSuggestions(results))
        .catch(() => setSuggestions([]))
    }, 350)
    return () => window.clearTimeout(timer)
  }, [pickup, dest, suggestionField, gpsActive, pickupPoint.lat, pickupPoint.lng])

  const useCurrentLocation = () => {
    if (!navigator.geolocation) {
      setLocationError('GPS is not available in this browser.')
      return
    }
    setGpsLoading(true)
    setLocationError('')
    gpsReverseDoneRef.current = false
    const onPosition = (position: GeolocationPosition) => {
      const { latitude, longitude } = position.coords
      setPickupPoint({ lat: latitude, lng: longitude, label:'Current location' })
      if (!gpsReverseDoneRef.current) {
        gpsReverseDoneRef.current = true
        geocodeApi.reverse(latitude, longitude).then(point => {
          setPickupPoint(point)
          setPickup(point.label)
        }).catch(() => {
          setGpsActive(false)
          setLocationError('SmartRoute currently operates only in India.')
        })
      }
      setPickup('Current location')
      setGpsActive(true)
      setPickupConfirmed(true)
      setSuggestionField(null)
      setGpsLoading(false)
    }
    const onError = (error: GeolocationPositionError) => {
      setGpsLoading(false)
      setGpsActive(false)
      setLocationError(error.code === error.PERMISSION_DENIED
        ? 'Location permission is blocked. Allow location access and try again.'
        : 'Unable to get your location. Try again outdoors or check GPS settings.')
    }
    navigator.geolocation.getCurrentPosition(onPosition, onError, {
      enableHighAccuracy: true,
      maximumAge: 10000,
      timeout: 12000,
    })
    if (gpsWatchRef.current !== null) navigator.geolocation.clearWatch(gpsWatchRef.current)
    gpsWatchRef.current = navigator.geolocation.watchPosition(onPosition, onError, {
      enableHighAccuracy: true,
      maximumAge: 5000,
      timeout: 15000,
    })
  }

  const chooseSuggestion = (field:'pickup'|'destination', point:any) => {
    if (field === 'pickup') {
      setPickup(point.label)
      setPickupPoint(point)
      setPickupConfirmed(true)
      setGpsActive(false)
    } else {
      setDest(point.label)
      setDestinationPoint(point)
      setDestinationConfirmed(true)
    }
    setSuggestions([])
    setSuggestionField(null)
  }

  useEffect(() => {
    ridesApi.getMyRides()
      .then(data => { setTrips(Array.isArray(data)?data:[]); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  // Poll active ride vehicle
  useEffect(() => {
    if (!activeRide) { clearInterval(pollRef.current); return }
    const poll = async () => {
      try {
        const v = await ridesApi.getVehicle(activeRide.id)
        setRideVehicle(v)
        const r = await ridesApi.getById(activeRide.id)
        setActiveRide(r)
        if (r.status === 'completed') { clearInterval(pollRef.current); toast('success','Ride completed!') }
      } catch {}
    }
    poll()
    pollRef.current = setInterval(poll, 5000)
    return () => clearInterval(pollRef.current)
  }, [activeRide?.id])

  const handleBook = async () => {
    if (!dest.trim()) { toast('warning','Enter a destination'); return }
    if (!pickupConfirmed) { toast('warning','Choose a pickup suggestion or use GPS'); return }
    if (!destinationConfirmed || !destinationPoint) { toast('warning','Choose a destination suggestion'); return }
    setBooking(true)
    const tier = RIDE_TIERS.find(t=>t.id===selected)!
    try {
      setGeocoding(true)
      const resolvedPickup = pickupPoint
      const resolvedDestination = destinationPoint
      const route = await routingApi.route(resolvedPickup, resolvedDestination)
      setRouteEstimate(route)
      if (route?.geometry?.length > 1) {
        setRouteGeometry(route.geometry.map(([lng, lat]:[number,number]) => [lat, lng] as [number,number]))
      }
      setLocationError('')
      const ride = await ridesApi.create({
        pickup_lat: resolvedPickup.lat, pickup_lng: resolvedPickup.lng,
        dest_lat: resolvedDestination.lat, dest_lng: resolvedDestination.lng,
        pickup_label: resolvedPickup.label || pickup || 'Current location',
        destination_label: resolvedDestination.label || dest,
        ride_option_id: tier.id, ride_option_name: tier.name, ride_option_price: tier.price,
      })
      setActiveRide(ride)
      setTrips(prev => [ride, ...prev])
      toast('success','Ride requested!','Waiting for dispatch…')
    } catch(e:any) {
      const message = e?.response?.data?.detail || e?.message || 'Try again'
      setLocationError(message.includes('route') || message.includes('Route') ? 'No drivable route found for these locations.' : '')
      toast('error','Failed to book ride', message)
    } finally { setGeocoding(false); setBooking(false) }
  }

  const handleCancel = async () => {
    if (!activeRide) return
    try {
      await ridesApi.cancel(activeRide.id)
      setActiveRide(null); setRideVehicle(null)
      setTrips(prev => prev.map(t => t.id===activeRide.id?{...t,status:'cancelled'}:t))
      toast('info','Ride cancelled')
    } catch(e:any) { toast('error','Cannot cancel', e?.response?.data?.detail||'') }
  }

  if (view === 'trips') return <TripsView trips={trips} loading={loading} setView={setView} setActiveRide={setActiveRide} />
  if (view === 'trip-detail') return activeRide ? <TripDetail ride={activeRide} vehicle={rideVehicle} onCancel={handleCancel} onBack={()=>setView('home')} /> : <div onClick={()=>setView('home')} style={s({padding:28,color:C.muted,cursor:'pointer'})}>← Back</div>
  if (view === 'tracking') return <TrackingView ride={activeRide} vehicle={rideVehicle} onBack={()=>setView('home')} />

  // Home / Booking — split layout: form left, live map right
  const pickupCoords  = { lat:pickupPoint.lat, lng:pickupPoint.lng, label: pickup||'Current location' }
  const destCoords    = destinationPoint || null
  const mapCenter:[number,number] = destinationPoint
    ? [(pickupPoint.lat + destinationPoint.lat) / 2, (pickupPoint.lng + destinationPoint.lng) / 2]
    : (gpsActive || !!pickup.trim()) ? [pickupPoint.lat, pickupPoint.lng] : [12.9568, 77.6305]

  return (
    <div style={{ display:'flex', flex:1, minHeight:0, overflow:'hidden' }}>

      {/* ── Left panel ── */}
      <div className="booking-panel" style={{ width:340, flexShrink:0, overflowY:'auto', padding:24, background:'var(--bg)', borderRight:'1px solid var(--border)' }}>
        <h1 style={s({ color:C.text, fontSize:20, fontWeight:800, fontFamily:'Bricolage Grotesque,sans-serif', marginBottom:4 })}>Book a Ride</h1>
        <p style={s({ color:C.muted, fontSize:12, marginBottom:18 })}>Smart shared dispatch · flat fares</p>

        {/* Active ride banner */}
        {activeRide && (
          <div className="ride-active" style={s({ background:`${C.accent}12`, border:`1px solid ${C.accent}40`, borderRadius:10, padding:'12px 14px', marginBottom:16 })}>
            <p style={s({ color:C.accent, fontSize:12, fontWeight:700 })}>Ride active — {activeRide.status.replace('_',' ')}</p>
            <p style={s({ color:C.muted2, fontSize:11, marginTop:2 })}>→ {activeRide.destination_label}</p>
            <button onClick={()=>setView('trip-detail')} style={s({ marginTop:8, background:C.accent, color:C.bg, border:'none', borderRadius:7, padding:'5px 12px', fontSize:11, fontWeight:700, cursor:'pointer' })}>Track →</button>
          </div>
        )}

        {/* Inputs */}
          <div style={s({ display:'flex', flexDirection:'column', gap:8, marginBottom:14 })}>
          <div style={s({ display:'flex', alignItems:'center', gap:8, background:C.surface2, border:`1px solid ${C.border2}`, borderRadius:8, padding:'9px 11px' })}>
            <span>📍</span>
            <input value={pickup} onFocus={()=>setSuggestionField('pickup')} onChange={e=>{ setPickup(e.target.value); setPickupConfirmed(false); setGpsActive(false) }} placeholder="Pickup location" style={s({ flex:1, background:'none', border:'none', color:C.text, fontSize:12, outline:'none' })} />
            <button onClick={useCurrentLocation} disabled={gpsLoading} title="Use current GPS location" style={s({ border:'none', background:'none', color:gpsActive?C.accent:C.muted2, cursor:gpsLoading?'wait':'pointer', fontSize:11, fontWeight:700, whiteSpace:'nowrap' })}>
              {gpsLoading ? 'Locating…' : gpsActive ? 'GPS on' : 'Use GPS'}
            </button>
          </div>
          {suggestionField === 'pickup' && suggestions.length > 0 && (
            <SuggestionList items={suggestions} onChoose={point=>chooseSuggestion('pickup', point)} />
          )}
        {locationError && <p style={s({ color:C.danger, fontSize:11, marginTop:-6, marginBottom:10 })}>{locationError}</p>}
          <div style={s({ display:'flex', alignItems:'center', gap:8, background:C.surface2, border:`1px solid ${C.border2}`, borderRadius:8, padding:'9px 11px' })}>
            <span>🎯</span>
            <input value={dest} onFocus={()=>setSuggestionField('destination')} onChange={e=>{ setDest(e.target.value); setDestinationConfirmed(false); setDestinationPoint(null); setRouteGeometry([]); setRouteEstimate(null) }} placeholder="Destination" style={s({ flex:1, background:'none', border:'none', color:C.text, fontSize:12, outline:'none' })} />
          </div>
        {suggestionField === 'destination' && suggestions.length > 0 && (
            <SuggestionList items={suggestions} onChoose={point=>chooseSuggestion('destination', point)} />
          )}
        </div>

        {routeEstimate && (
          <div style={s({ display:'flex', justifyContent:'space-between', padding:'9px 11px', marginBottom:14, background:C.surface2, border:`1px solid ${C.border}`, borderRadius:8, color:C.muted2, fontSize:11 })}>
            <span>Route estimate</span>
            <strong style={s({ color:C.text })}>{(routeEstimate.distanceMeters / 1000).toFixed(1)} km · {Math.max(1, Math.round(routeEstimate.durationSeconds / 60))} min</strong>
          </div>
        )}

        {/* Ride tiers */}
        <div style={s({ display:'flex', flexDirection:'column', gap:6, marginBottom:14 })}>
          {RIDE_TIERS.map(tier => {
            const active = selected === tier.id
            return (
              <div className="ride-tier" key={tier.id} onClick={()=>setSelected(tier.id)} style={s({ display:'flex', alignItems:'center', justifyContent:'space-between', padding:'9px 11px', borderRadius:8, border:`1px solid ${active?C.accent:C.border}`, background:active?`${C.accent}10`:'transparent', cursor:'pointer' })}>
                <div style={s({ display:'flex', alignItems:'center', gap:8 })}>
                  <span style={{ fontSize:18 }}>{tier.icon}</span>
                  <div>
                    <p style={s({ color:C.text, fontSize:12, fontWeight:700 })}>{tier.name}</p>
                    <p style={s({ color:C.muted2, fontSize:10 })}>{tier.desc} · {tier.eta}</p>
                  </div>
                </div>
                <p style={s({ color:active?C.accent:C.text, fontSize:12, fontWeight:700 })}>{tier.price}</p>
              </div>
            )
          })}
        </div>

        <button className="primary-action" onClick={handleBook} disabled={booking||!!activeRide} style={s({ width:'100%', padding:'11px', background:C.accent, color:C.bg, border:'none', borderRadius:8, fontSize:13, fontWeight:700, cursor:booking||activeRide?'not-allowed':'pointer', opacity:booking||activeRide?0.6:1, marginBottom:20 })}>
          {geocoding ? 'Finding locations…' : booking ? 'Booking…' : activeRide ? 'Ride in progress' : 'Request Ride'}
        </button>

        {/* Recent */}
        <div style={s({ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:10 })}>
          <p style={s({ color:C.text, fontSize:13, fontWeight:700 })}>Recent Rides</p>
          <button onClick={()=>setView('trips')} style={s({ background:'none', border:'none', color:C.accent, fontSize:11, fontWeight:700, cursor:'pointer' })}>All →</button>
        </div>
        {loading ? <p style={s({ color:C.muted, fontSize:12 })}>Loading…</p> :
         trips.length === 0 ? <p style={s({ color:C.muted, fontSize:12 })}>No rides yet.</p> :
         trips.slice(0,4).map(t => <TripCard key={t.id} trip={t} onClick={()=>{ setActiveRide(t); setView('trip-detail') }} />)
        }
      </div>

      {/* ── Right map ── */}
      <div className="map-surface" style={{ flex:1, position:'relative', minWidth:0, minHeight:0 }}>
        <div style={{ position:'absolute', inset:0 }}>
          <AppMap
            center={mapCenter}
            zoom={12}
            height="100%"
            pickup={pickupCoords}
            destination={destCoords}
            routeGeometry={routeGeometry}
            vehicles={vehicles.filter(v => v.status !== 'offline')}
          />
        </div>
        {/* Tip overlay */}
        <div style={{ position:'absolute', top:12, left:'50%', transform:'translateX(-50%)', background:'rgba(255,255,255,0.94)', border:`1px solid var(--border)`, boxShadow:'0 2px 10px rgba(0,0,0,0.12)', borderRadius:20, padding:'7px 14px', pointerEvents:'none', zIndex:500 }}>
          <p style={{ color:'var(--muted2)', fontSize:11 }}>India · Smart shared rides</p>
        </div>
      </div>
    </div>
  )
}

// ─── Status badge ─────────────────────────────────────────────────────────────
const STATUS_COLOR: Record<string,string> = {
  pending:'#f59e0b', clustered:'#a78bfa', assigned:'#60a5fa',
  arriving:'#00c9a7', in_progress:'#00c9a7', completed:'#22c55e', cancelled:'#f43f5e',
}
function StatusBadge({ status }: { status:string }) {
  const col = STATUS_COLOR[status] || '#7a90b0'
  return <span style={s({ fontSize:11, fontWeight:700, textTransform:'uppercase', letterSpacing:'0.07em', color:col, background:col+'22', padding:'2px 8px', borderRadius:6 })}>{status.replace('_',' ')}</span>
}

// ─── Trip Card ────────────────────────────────────────────────────────────────
function TripCard({ trip, onClick }: { trip:any; onClick:()=>void }) {
  return (
    <div onClick={onClick} style={s({ display:'flex', alignItems:'center', justifyContent:'space-between', padding:'10px 12px', background:C.surface2, border:`1px solid ${C.border}`, borderRadius:9, cursor:'pointer', marginBottom:6, transition:'border-color 0.15s' })}>
      <div style={{ minWidth:0 }}>
        <p style={s({ color:C.text, fontSize:12, fontWeight:700, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' })}>→ {trip.destination_label || `${trip.dest_lat?.toFixed(3)}, ${trip.dest_lng?.toFixed(3)}`}</p>
        <p style={s({ color:C.muted, fontSize:11, marginTop:2 })}>{trip.request_time ? new Date(trip.request_time).toLocaleString() : ''}</p>
      </div>
      <StatusBadge status={trip.status} />
    </div>
  )
}

// ─── Trips View ───────────────────────────────────────────────────────────────
function TripsView({ trips, loading, setView, setActiveRide }: { trips:any[]; loading:boolean; setView:(v:any)=>void; setActiveRide:(r:any)=>void }) {
  return (
    <div style={s({ padding:28, maxWidth:720 })}>
      <div style={s({ display:'flex', alignItems:'center', gap:12, marginBottom:20 })}>
        <button onClick={()=>setView('home')} style={s({ background:'none', border:'none', color:C.muted2, cursor:'pointer', fontSize:13 })}>← Back</button>
        <h1 style={s({ color:C.text, fontSize:20, fontWeight:800, fontFamily:'Bricolage Grotesque,sans-serif' })}>My Trips</h1>
      </div>
      {loading && <p style={s({ color:C.muted, fontSize:13 })}>Loading…</p>}
      {!loading && trips.length === 0 && <p style={s({ color:C.muted, fontSize:14 })}>No trips yet.</p>}
      <div style={s({ display:'flex', flexDirection:'column', gap:8 })}>
        {trips.map(t => (
          <div key={t.id} onClick={()=>{ setActiveRide(t); setView('trip-detail') }} style={s({ display:'flex', justifyContent:'space-between', alignItems:'center', padding:'14px 16px', background:C.surface, border:`1px solid ${C.border}`, borderRadius:10, cursor:'pointer' })}>
            <div>
              <div style={s({ display:'flex', alignItems:'center', gap:8, marginBottom:4 })}>
                <span style={s({ color:C.muted2, fontSize:11 })}>#{t.id}</span>
                <StatusBadge status={t.status} />
              </div>
              <p style={s({ color:C.text, fontSize:13, fontWeight:600 })}>📍 {t.pickup_label || 'Pickup'} → 🎯 {t.destination_label || 'Destination'}</p>
              <p style={s({ color:C.muted, fontSize:11, marginTop:2 })}>{t.ride_option_name || 'Standard'} · {t.request_time ? new Date(t.request_time).toLocaleString() : ''}</p>
            </div>
            <span style={s({ color:C.muted, fontSize:18 })}>›</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── Trip Detail ──────────────────────────────────────────────────────────────
function TripDetail({ ride, vehicle, onCancel, onBack }: { ride:any; vehicle:any; onCancel:()=>void; onBack:()=>void }) {
  const canCancel = ['pending','clustered'].includes(ride.status)
  return (
    <div style={s({ padding:28, maxWidth:580 })}>
      <button onClick={onBack} style={s({ background:'none', border:'none', color:C.muted2, cursor:'pointer', fontSize:13, marginBottom:20 })}>← Back</button>
      <div style={s({ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:20 })}>
        <h1 style={s({ color:C.text, fontSize:20, fontWeight:800, fontFamily:'Bricolage Grotesque,sans-serif' })}>Ride #{ride.id}</h1>
        <StatusBadge status={ride.status} />
      </div>
      <div style={s({ display:'flex', flexDirection:'column', gap:12 })}>
        <InfoCard label="From" value={ride.pickup_label || `${ride.pickup_lat}, ${ride.pickup_lng}`} />
        <InfoCard label="To"   value={ride.destination_label || `${ride.dest_lat}, ${ride.dest_lng}`} />
        <InfoCard label="Ride type" value={ride.ride_option_name || 'Standard'} />
        {ride.ride_option_price && <InfoCard label="Fare" value={ride.ride_option_price} />}
        {ride.h3_index  && <InfoCard label="H3 cell"  value={ride.h3_index} mono />}
        {ride.cluster_id && <InfoCard label="Cluster" value={`#${ride.cluster_id}`} />}
        {ride.request_time && <InfoCard label="Requested" value={new Date(ride.request_time).toLocaleString()} />}
      </div>

      {vehicle && (
        <div style={s({ marginTop:16, padding:'14px 16px', background:`${C.accent}10`, border:`1px solid ${C.accent}30`, borderRadius:10 })}>
          <p style={s({ color:C.accent, fontSize:12, fontWeight:700, marginBottom:8 })}>🚗 Assigned Vehicle</p>
          <div style={s({ display:'flex', gap:20 })}>
            <div><p style={s({ color:C.muted2, fontSize:11 })}>Plate</p><p style={s({ color:C.text, fontSize:13, fontWeight:700 })}>{vehicle.license_plate}</p></div>
            <div><p style={s({ color:C.muted2, fontSize:11 })}>Status</p><p style={s({ color:C.text, fontSize:13, fontWeight:700 })}>{vehicle.status}</p></div>
            {vehicle.lat && <div><p style={s({ color:C.muted2, fontSize:11 })}>Location</p><p style={s({ color:C.text, fontSize:13, fontWeight:700 })}>{vehicle.lat.toFixed(4)}, {vehicle.lng.toFixed(4)}</p></div>}
          </div>
        </div>
      )}
      {!vehicle && ['assigned','arriving','in_progress'].includes(ride.status) && (
        <div style={s({ marginTop:16, padding:'12px 16px', background:C.surface2, border:`1px solid ${C.border}`, borderRadius:10 })}>
          <p style={s({ color:C.muted2, fontSize:13 })}>⏳ Vehicle assignment pending…</p>
        </div>
      )}
      {canCancel && (
        <button onClick={onCancel} style={s({ marginTop:20, width:'100%', padding:'11px', background:'transparent', border:`1px solid ${C.danger}`, color:C.danger, borderRadius:9, fontSize:13, fontWeight:700, cursor:'pointer' })}>Cancel Ride</button>
      )}
    </div>
  )
}

// ─── Live Tracking View ───────────────────────────────────────────────────────
function TrackingView({ ride, vehicle, onBack }: { ride:any; vehicle:any; onBack:()=>void }) {
  const pickupCoords = ride ? { lat:ride.pickup_lat, lng:ride.pickup_lng, label:ride.pickup_label } : null
  const destCoords   = ride ? { lat:ride.dest_lat,   lng:ride.dest_lng,   label:ride.destination_label } : null
  const vList        = vehicle?.lat ? [vehicle] : []
  const center:[number,number] = vehicle?.lat ? [vehicle.lat, vehicle.lng] : ride ? [ride.pickup_lat, ride.pickup_lng] : [12.9784, 77.6408]

  return (
    <div style={{ display:'flex', flexDirection:'column', flex:1, minHeight:0 }}>
      {/* Header bar */}
      <div style={s({ padding:'12px 20px', borderBottom:`1px solid ${C.border}`, display:'flex', alignItems:'center', gap:12, background:C.bg2, flexShrink:0 })}>
        <button onClick={onBack} style={s({ background:'none', border:'none', color:C.muted2, cursor:'pointer', fontSize:13 })}>← Back</button>
        <p style={s({ color:C.text, fontSize:14, fontWeight:700 })}>Live Tracking</p>
        {ride && <StatusBadge status={ride.status} />}
        {vehicle && <p style={s({ color:C.accent, fontSize:12, marginLeft:'auto' })}>🚗 {vehicle.license_plate}</p>}
        {!vehicle && ride && <p style={s({ color:C.muted2, fontSize:12, marginLeft:'auto' })}>⏳ Awaiting vehicle…</p>}
      </div>
      {/* Full-height map */}
      <div style={{ flex:1, minHeight:0 }}>
        {!ride
          ? <div style={s({ padding:28 })}><p style={s({ color:C.muted, fontSize:14 })}>No active ride.</p></div>
          : <AppMap center={center} zoom={14} height="100%" vehicles={vList} pickup={pickupCoords} destination={destCoords} />
        }
      </div>
    </div>
  )
}

// ─── Helpers ──────────────────────────────────────────────────────────────────
function InfoCard({ label, value, mono=false }: { label:string; value:string; mono?:boolean }) {
  return (
    <div style={s({ display:'flex', justifyContent:'space-between', alignItems:'center', padding:'10px 14px', background:C.surface2, border:`1px solid ${C.border}`, borderRadius:8 })}>
      <p style={s({ color:C.muted2, fontSize:12 })}>{label}</p>
      <p style={s({ color:C.text, fontSize:13, fontWeight:600, fontFamily:mono?'monospace':'inherit' })}>{value}</p>
    </div>
  )
}

function SuggestionList({ items, onChoose }: { items:any[]; onChoose:(item:any)=>void }) {
  return (
    <div style={s({ background:C.surface, border:`1px solid ${C.border}`, borderRadius:8, boxShadow:'0 8px 20px rgba(0,0,0,.12)', overflow:'hidden', marginTop:-2, marginBottom:2, position:'relative', zIndex:20 })}>
      {items.map((item, index) => (
        <button key={`${item.lat}-${item.lng}-${index}`} onMouseDown={event=>event.preventDefault()} onClick={()=>onChoose(item)} style={s({ display:'block', width:'100%', textAlign:'left', border:'none', borderBottom:index < items.length-1 ? `1px solid ${C.border}` : 'none', background:C.surface, color:C.text, padding:'10px 12px', cursor:'pointer', fontSize:11 })}>
          <span style={s({ display:'block', fontWeight:700 })}>{item.label.split(',')[0]}</span>
          <span style={s({ display:'block', color:C.muted, marginTop:2, whiteSpace:'nowrap', overflow:'hidden', textOverflow:'ellipsis' })}>{item.label}</span>
        </button>
      ))}
    </div>
  )
}

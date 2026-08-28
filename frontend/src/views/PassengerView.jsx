import { useState, useEffect, useRef, useCallback } from 'react'
import { useAuth } from '@clerk/clerk-react'
import { C, s } from '../ui/tokens.js'
import { ridesApi, geocodeApi, routingApi, createTrackingWS } from '../services/api.js'
import { useWebSocket } from '../hooks/useWebSocket.js'
import AppMap from '../components/AppMap'

const RIDE_TIERS = [
  { id:'swift-x',   name:'SwiftX',    desc:'Affordable shared ride', eta:'3 min', price:'₹12–15', icon:'S', seats:4 },
  { id:'swift-xl',  name:'SwiftXL',   desc:'Extra space, small group', eta:'6 min', price:'₹18–22', icon:'X', seats:6 },
  { id:'swift-lux', name:'Lux Black', desc:'Premium, top-rated driver', eta:'8 min', price:'₹32–40', icon:'L', seats:4 },
  { id:'swift-moto',name:'Moto',      desc:'Fast, budget solo',        eta:'2 min', price:'₹6–9',   icon:'M', seats:1 },
]

export default function PassengerView({ view, setView, toast }) {
  const [trips,    setTrips]    = useState([])
  const [loading,  setLoading]  = useState(true)
  const [selected, setSelected] = useState('swift-x')
  const [pickup,   setPickup]   = useState('')
  const [dest,     setDest]     = useState('')
  const [booking,  setBooking]  = useState(false)
  const [activeRide, setActiveRide] = useState(null)
  const [viewingRide, setViewingRide] = useState(null)
  const [rideVehicle, setRideVehicle] = useState(null)
  const [vehicles, setVehicles] = useState([])
  const [pickupPoint, setPickupPoint] = useState({ lat:12.9784, lng:77.6408, label:'Current location' })
  const [destinationPoint, setDestinationPoint] = useState(null)
  const [routeGeometry, setRouteGeometry] = useState([])
  const [routeEstimate, setRouteEstimate] = useState(null)
  const [suggestions, setSuggestions] = useState([])
  const [suggestionField, setSuggestionField] = useState(null)
  const [pickupConfirmed, setPickupConfirmed] = useState(false)
  const [destinationConfirmed, setDestinationConfirmed] = useState(false)
  const [locationError, setLocationError] = useState('')
  const [geocoding, setGeocoding] = useState(false)
  const [gpsActive, setGpsActive] = useState(false)
  const [gpsLoading, setGpsLoading] = useState(false)
  const [mapPickupMode, setMapPickupMode] = useState(false)
  const [mapPickupLoading, setMapPickupLoading] = useState(false)
  const [trafficRouting, setTrafficRouting] = useState(false)
  const pollRef = useRef(null)
  const gpsWatchRef = useRef(null)
  const gpsReverseDoneRef = useRef(false)
  const { getToken } = useAuth()

  const handleTrackingMessage = useCallback((message) => {
    if (message.type === 'tracking_snapshot') {
      setVehicles(Array.isArray(message.vehicles) ? message.vehicles : [])
    } else if (message.type === 'vehicle_location_update' && message.vehicle) {
      setVehicles(prev => prev.some(v => v.id === message.vehicle.id)
        ? prev.map(v => v.id === message.vehicle.id ? { ...v, ...message.vehicle } : v)
        : [...prev, message.vehicle])
      if (rideVehicle?.id === message.vehicle.id) setRideVehicle((prev) => ({ ...prev, ...message.vehicle }))
    }
  }, [rideVehicle?.id])

  useWebSocket(createTrackingWS, getToken, handleTrackingMessage, true)

  useEffect(() => () => {
    if (gpsWatchRef.current !== null) navigator.geolocation?.clearWatch(gpsWatchRef.current)
  }, [])

  useEffect(() => {
    const query = suggestionField === 'pickup' ? pickup : dest
    if (!suggestionField || query.trim().length < 3) return
    const timer = window.setTimeout(() => {
      geocodeApi.suggest(query.trim(), gpsActive ? pickupPoint : undefined)
        .then(results => setSuggestions(results))
        .catch(() => setSuggestions([]))
    }, 350)
    return () => window.clearTimeout(timer)
  }, [pickup, dest, suggestionField, gpsActive, pickupPoint])

  const useCurrentLocation = () => {
    if (!navigator.geolocation) {
      setLocationError('GPS is not available in this browser.')
      return
    }
    setGpsLoading(true)
    setLocationError('')
    gpsReverseDoneRef.current = false
    const onPosition = (position) => {
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
    const onError = (error) => {
      setGpsActive(false)
      setGpsLoading(false)
      setLocationError(error?.code === 1 ? 'Location permission was denied.' : 'Unable to determine your current location.')
    }
    navigator.geolocation.getCurrentPosition(onPosition, onError, { enableHighAccuracy: true, timeout: 8000, maximumAge: 10000 })
    if (gpsWatchRef.current !== null) navigator.geolocation.clearWatch(gpsWatchRef.current)
    gpsWatchRef.current = navigator.geolocation.watchPosition(onPosition, onError, { enableHighAccuracy: true, timeout: 10000, maximumAge: 10000 })
  }

  const chooseSuggestion = (field, point) => {
    if (field === 'pickup') {
      setPickupPoint(point)
      setPickup(point.label)
      setPickupConfirmed(true)
      setGpsActive(false)
    } else {
      setDestinationPoint(point)
      setDest(point.label)
      setDestinationConfirmed(true)
      if (pickupPoint) {
        routingApi.route(pickupPoint, point, { traffic: trafficRouting })
          .then(route => {
            setRouteEstimate(route)
            if (route?.geometry?.length > 1) setRouteGeometry(route.geometry)
          })
          .catch(() => {})
      }
    }
    setSuggestionField(null)
    setSuggestions([])
    setLocationError('')
  }

  const searchLocation = async (field) => {
    const query = field === 'pickup' ? pickup : dest
    if (!query.trim()) return
    setGeocoding(true)
    setLocationError('')
    try {
      const point = await geocodeApi.search(query.trim())
      chooseSuggestion(field, point)
    } catch (error) {
      setLocationError(error?.response?.data?.detail || error?.message || 'Location not found')
    } finally {
      setGeocoding(false)
    }
  }

  const choosePickupOnMap = async (lat, lng) => {
    setMapPickupLoading(true)
    setLocationError('')
    setRouteGeometry([])
    setRouteEstimate(null)
    setGpsActive(false)
    setPickupConfirmed(false)
    const fallback = { lat, lng, label: `Map location (${lat.toFixed(5)}, ${lng.toFixed(5)})` }
    try {
      const snapped = await geocodeApi.nearestRoad(lat, lng)
      const point = await geocodeApi.reverse(snapped.lat, snapped.lng)
      setPickupPoint({ ...point, lat: snapped.lat, lng: snapped.lng })
      setPickup(point.label || fallback.label)
    } catch {
      try {
        const point = await geocodeApi.reverse(lat, lng)
        setPickupPoint({ ...point, lat, lng })
        setPickup(point.label || fallback.label)
      } catch {
        setPickupPoint(fallback)
        setPickup(fallback.label)
      }
    } finally {
      setPickupConfirmed(true)
      setMapPickupMode(false)
      setMapPickupLoading(false)
    }
  }

  useEffect(() => {
    ridesApi.getMyRides()
      .then(data => { setTrips(Array.isArray(data)?data:[]); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  const activeRideId = activeRide?.id
  const activePickupLat = activeRide?.pickup_lat
  const activePickupLng = activeRide?.pickup_lng
  const activeDestinationLat = activeRide?.dest_lat
  const activeDestinationLng = activeRide?.dest_lng

  useEffect(() => {
    if (!activeRideId) return undefined
    let cancelled = false
    routingApi.route(
      { lat: activePickupLat, lng: activePickupLng },
      { lat: activeDestinationLat, lng: activeDestinationLng },
      { traffic: trafficRouting },
    ).then(route => {
      if (cancelled) return
      setRouteEstimate(route)
      setRouteGeometry(route?.geometry?.length > 1 ? route.geometry : [])
    }).catch(() => {
      if (!cancelled) setRouteGeometry([])
    })
    return () => { cancelled = true }
  }, [activeDestinationLat, activeDestinationLng, activePickupLat, activePickupLng, activeRideId, trafficRouting])

  useEffect(() => {
    if (!activeRideId) { clearInterval(pollRef.current); return }
    const poll = async () => {
      try {
        const v = await ridesApi.getVehicle(activeRideId)
        setRideVehicle(v)
        const r = await ridesApi.getById(activeRideId)
        setActiveRide(r)
        if (r.status === 'completed') { clearInterval(pollRef.current); toast('success','Ride completed!') }
      } catch (error) { void error }
    }
    poll()
    pollRef.current = setInterval(poll, 4000)
    return () => clearInterval(pollRef.current)
  }, [activeRideId, toast])

  const handleBook = async () => {
    if (!dest.trim()) { toast('warning','Enter a destination'); return }
    if (!pickupConfirmed) { toast('warning','Choose a pickup suggestion or use GPS'); return }
    if (!destinationConfirmed || !destinationPoint) { toast('warning','Choose a destination suggestion'); return }
    setBooking(true)
    const tier = RIDE_TIERS.find(t=>t.id===selected)
    try {
      setGeocoding(true)
      const resolvedPickup = pickupPoint
      const resolvedDestination = destinationPoint
      const route = await routingApi.route(resolvedPickup, resolvedDestination, { traffic: trafficRouting })
      setRouteEstimate(route)
      if (route?.geometry?.length > 1) setRouteGeometry(route.geometry)
      setLocationError('')
      const ride = await ridesApi.create({
        pickup_lat: resolvedPickup.lat, pickup_lng: resolvedPickup.lng,
        dest_lat: resolvedDestination.lat, dest_lng: resolvedDestination.lng,
        pickup_label: pickup, destination_label: dest,
        ride_option_id: selected,
        ride_option_name: tier?.name,
        ride_option_price: tier?.price,
      })
      setActiveRide(ride)
      setTrips(prev => [ride, ...prev.filter(t => t.id !== ride.id)])
      toast('success','Ride Requested!','Finding nearby riders to pool with…')
    } catch(e) { toast('error','Booking failed', e?.response?.data?.detail||e?.message||'') }
    finally { setBooking(false); setGeocoding(false) }
  }

  const handleCancel = async () => {
    if (!activeRide) return
    try {
      await ridesApi.cancel(activeRide.id)
      setActiveRide(null); setRideVehicle(null)
      setRouteGeometry([]); setRouteEstimate(null)
      setTrips(prev => prev.map(t => t.id===activeRide.id?{...t,status:'cancelled'}:t))
      toast('info','Ride cancelled')
    } catch(e) { toast('error','Cannot cancel', e?.response?.data?.detail||'') }
  }

  // Opening a trip from Recent Rides / My Trips should only take over Home's
  // "Active Booking" card (and live vehicle polling) for rides still actually
  // in progress. Completed/cancelled rides open read-only via viewingRide so
  // they stop lingering on Home after the user navigates back.
  const openTrip = useCallback((trip) => {
    if (['completed', 'cancelled'].includes(trip.status)) {
      setViewingRide(trip)
    } else {
      setActiveRide(trip)
    }
    setView('trip-detail')
  }, [setView])

  if (view === 'trips') return <TripsView trips={trips} loading={loading} setView={setView} onOpenTrip={openTrip} title="My Trips" />
  if (view === 'recent-rides') return <TripsView trips={trips} loading={loading} setView={setView} onOpenTrip={openTrip} title="Recent Rides" />
  if (view === 'trip-detail') {
    const detailRide = activeRide || viewingRide
    return detailRide
      ? <TripDetail ride={detailRide} vehicle={activeRide ? rideVehicle : null} onCancel={handleCancel} onBack={()=>{ setViewingRide(null); setView('home') }} />
      : <div onClick={()=>setView('home')} style={s({padding:28,color:C.muted,cursor:'pointer'})}>← Back</div>
  }
  if (view === 'tracking') return <TrackingView ride={activeRide} vehicle={rideVehicle} routeGeometry={routeGeometry} onBack={()=>setView('home')} />

  // Home / Booking layout
  const pickupCoords  = { lat:pickupPoint.lat, lng:pickupPoint.lng, label: pickup||'Current location' }
  const destCoords    = destinationPoint || null
  // Normal passenger rides show a vehicle only after the backend assigns one.
  // The presentation screen owns its synthetic vehicle separately.
  const mapVehicle = rideVehicle
  const mapPickupPulse = !!activeRide && ['pending', 'clustered'].includes(activeRide.status)
  const mapPickup = activeRide ? { lat:activeRide.pickup_lat, lng:activeRide.pickup_lng, label:activeRide.pickup_label } : pickupCoords
  const mapDestination = activeRide ? { lat:activeRide.dest_lat, lng:activeRide.dest_lng, label:activeRide.destination_label } : destCoords
  
  const mapVehicleAnimation = mapVehicle && activeRide && routeGeometry.length > 1
    ? {
        key: `${mapVehicle.id}:${activeRide.status}:${routeGeometry.length}`,
        vehicleId: mapVehicle.id,
        path: ['pending', 'clustered', 'assigned', 'arriving'].includes(activeRide.status)
          ? [[mapVehicle.lng, mapVehicle.lat], [activeRide.pickup_lng, activeRide.pickup_lat]]
          : routeGeometry,
        durationMs: activeRide.status === 'in_progress' ? 18000 : 8000,
        loop: true,
      }
    : null

  const mapCenter = activeRide
    ? [(activeRide.pickup_lat + activeRide.dest_lat) / 2, (activeRide.pickup_lng + activeRide.dest_lng) / 2]
    : destinationPoint
    ? [(pickupPoint.lat + destinationPoint.lat) / 2, (pickupPoint.lng + destinationPoint.lng) / 2]
    : (gpsActive || !!pickup.trim()) ? [pickupPoint.lat, pickupPoint.lng] : [12.9784, 77.6408]

  return (
    <div style={{ display:'flex', flex:1, minHeight:0, overflow:'hidden', position:'relative' }}>

      {/* ── Left booking & active ride panel ── */}
      <div className="booking-panel" style={{ width:360, flexShrink:0, overflowY:'auto', padding:24, background:'var(--bg)', borderRight:'1px solid var(--border)', display:'flex', flexDirection:'column', gap:14 }}>
        <div>
          <h1 style={s({ color:C.text, fontSize:20, fontWeight:800, fontFamily:'Bricolage Grotesque,sans-serif', marginBottom:4 })}>Book a Ride</h1>
          <p style={s({ color:C.muted, fontSize:12 })}>Smart shared dispatch · flat fares</p>
        </div>

        {/* 6-Stage Transit Stepper for Active Ride */}
        {activeRide && (
          <div style={s({ background: C.surface, border: `1px solid ${C.accent}55`, borderRadius: 12, padding: '14px 16px', boxShadow: '0 4px 16px rgba(0,0,0,0.1)' })}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
              <div>
                <span style={s({ fontSize: 10, color: C.muted2, fontWeight: 700, textTransform: 'uppercase' })}>Active Booking</span>
                <p style={s({ color: C.text, fontSize: 13, fontWeight: 800 })}>Ride #{activeRide.id} · {activeRide.ride_option_name || 'SwiftX'}</p>
              </div>
              <StatusBadge status={activeRide.status} />
            </div>

            {/* Stepper progress dots */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12, position: 'relative' }}>
              <div style={{ position: 'absolute', top: 9, left: 10, right: 10, height: 2, background: C.surface3, zIndex: 1 }} />
              {[
                { key: 'pending', label: 'Requested' },
                { key: 'clustered', label: 'Clustered' },
                { key: 'assigned', label: 'Assigned' },
                { key: 'arriving', label: 'Arriving' },
                { key: 'in_progress', label: 'In Transit' },
                { key: 'completed', label: 'Delivered' },
              ].map((step, idx) => {
                const statuses = ['pending', 'clustered', 'assigned', 'arriving', 'in_progress', 'completed']
                const currentIdx = statuses.indexOf(activeRide.status)
                const isPassed = currentIdx >= idx
                const isCurrent = activeRide.status === step.key
                return (
                  <div key={step.key} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, zIndex: 2 }}>
                    <div style={{
                      width: 20, height: 20, borderRadius: '50%',
                      background: isCurrent ? C.accent : isPassed ? '#22c55e' : C.surface3,
                      border: `2px solid ${isCurrent ? '#ffffff' : 'transparent'}`,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: 9, fontWeight: 800, color: isPassed ? '#ffffff' : C.muted2,
                      boxShadow: isCurrent ? `0 0 10px ${C.accent}` : 'none',
                    }}>
                      {isPassed && !isCurrent ? '✓' : idx + 1}
                    </div>
                    <span style={{ fontSize: 8.5, fontWeight: isCurrent ? 800 : 600, color: isCurrent ? C.accent : isPassed ? C.text : C.muted }}>{step.label}</span>
                  </div>
                )
              })}
            </div>

            {/* Driver card preview */}
            {mapVehicle && (
              <div style={s({ background: C.surface2, border: `1px solid ${C.border}`, borderRadius: 8, padding: '10px 12px', display: 'flex', alignItems: 'center', gap: 10 })}>
                <div style={{ width: 34, height: 34, borderRadius: '50%', background: C.accent, color: C.bg, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 13 }}>RK</div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <p style={s({ color: C.text, fontSize: 12, fontWeight: 700 })}>Rajesh Kumar <span style={{ color: '#f59e0b', fontSize: 10 }}>★ 4.9</span></p>
                    <span style={s({ color: C.accent, fontSize: 11, fontWeight: 800 })}>{mapVehicle.license_plate}</span>
                  </div>
                  <p style={s({ color: C.muted2, fontSize: 10 })}>Tata Tigor EV · White · 3 seats shared</p>
                </div>
              </div>
            )}

            <div style={{ display: 'flex', gap: 6, marginTop: 10 }}>
              <button onClick={()=>setView('tracking')} style={s({ flex: 1, padding: '8px', background: C.accent, color: C.bg, border: 'none', borderRadius: 7, fontSize: 11, fontWeight: 800, cursor: 'pointer' })}>🗺️ Fullscreen Tracking</button>
              <button onClick={handleCancel} style={s({ padding: '8px 12px', background: 'transparent', border: `1px solid ${C.danger}`, color: C.danger, borderRadius: 7, fontSize: 11, fontWeight: 700, cursor: 'pointer' })}>Cancel</button>
            </div>
          </div>
        )}

        {/* Inputs */}
        <div style={s({ display:'flex', flexDirection:'column', gap:8 })}>
          <div style={s({ display:'flex', flexDirection:'column', gap:6, background:C.surface2, border:`1px solid ${C.border2}`, borderRadius:8, padding:'9px 11px' })}>
            <div style={s({ display:'flex', alignItems:'center', gap:8, minWidth:0 })}>
              <span>📍</span>
              <input value={pickup} onFocus={()=>setSuggestionField('pickup')} onKeyDown={e=>{ if(e.key==='Enter') { e.preventDefault(); void searchLocation('pickup') } }} onChange={e=>{ setPickup(e.target.value); setSuggestions([]); setPickupConfirmed(false); setGpsActive(false); setMapPickupMode(false) }} placeholder="Pickup location" style={s({ flex:1, minWidth:0, background:'none', border:'none', color:C.text, fontSize:12, outline:'none' })} />
            </div>
            <div style={s({ display:'flex', justifyContent:'flex-end', alignItems:'center', gap:8, paddingLeft:25 })}>
              <button onClick={()=>{ setMapPickupMode(value => !value); setSuggestionField(null) }} disabled={mapPickupLoading} title="Choose pickup on map" style={s({ border:'none', background:'none', color:mapPickupMode?C.accent:C.muted2, cursor:mapPickupLoading?'wait':'pointer', fontSize:11, fontWeight:700, whiteSpace:'nowrap', padding:0 })}>
                {mapPickupLoading ? 'Selecting…' : mapPickupMode ? 'Cancel map' : 'Choose on map'}
              </button>
              <button onClick={useCurrentLocation} disabled={gpsLoading || mapPickupLoading} title="Use current GPS location" style={s({ border:'none', background:'none', color:gpsActive?C.accent:C.muted2, cursor:gpsLoading?'wait':'pointer', fontSize:11, fontWeight:700, whiteSpace:'nowrap', padding:0 })}>
                {gpsLoading ? 'Locating…' : gpsActive ? 'GPS on' : 'Use GPS'}
              </button>
            </div>
          </div>
          {suggestionField === 'pickup' && suggestions.length > 0 && (
            <SuggestionList items={suggestions} onChoose={point=>chooseSuggestion('pickup', point)} />
          )}
          {locationError && <p style={s({ color:C.danger, fontSize:11, marginTop:-6, marginBottom:4 })}>{locationError}</p>}
          <div style={s({ display:'flex', alignItems:'center', gap:8, background:C.surface2, border:`1px solid ${C.border2}`, borderRadius:8, padding:'9px 11px' })}>
            <span>🎯</span>
            <input value={dest} onFocus={()=>setSuggestionField('destination')} onKeyDown={e=>{ if(e.key==='Enter') { e.preventDefault(); void searchLocation('destination') } }} onChange={e=>{ setDest(e.target.value); setSuggestions([]); setDestinationConfirmed(false); setDestinationPoint(null); setRouteGeometry([]); setRouteEstimate(null) }} placeholder="Destination" style={s({ flex:1, background:'none', border:'none', color:C.text, fontSize:12, outline:'none' })} />
          </div>
          {suggestionField === 'destination' && suggestions.length > 0 && (
            <SuggestionList items={suggestions} onChoose={point=>chooseSuggestion('destination', point)} />
          )}
        </div>

        {routeEstimate && (
          <div style={s({ display:'flex', justifyContent:'space-between', padding:'9px 11px', background:C.surface2, border:`1px solid ${C.border}`, borderRadius:8, color:C.muted2, fontSize:11 })}>
            <span>Route estimate</span>
            <strong style={s({ color:C.text })}>{(routeEstimate.distanceMeters / 1000).toFixed(1)} km · {Math.max(1, Math.round(routeEstimate.durationSeconds / 60))} min</strong>
          </div>
        )}

        <label style={s({ display:'flex', alignItems:'center', gap:8, color:C.muted2, fontSize:11, cursor:'pointer' })}>
          <input type="checkbox" checked={trafficRouting} onChange={e=>setTrafficRouting(e.target.checked)} />
          Use live traffic for route and ETA
        </label>

        {/* Ride tiers */}
        <div style={s({ display:'flex', flexDirection:'column', gap:6 })}>
          {RIDE_TIERS.map(tier => {
            const active = selected === tier.id
            return (
              <div className="ride-tier" key={tier.id} onClick={()=>setSelected(tier.id)} style={s({ display:'flex', alignItems:'center', justifyContent:'space-between', padding:'9px 11px', borderRadius:8, border:`1px solid ${active?C.accent:C.border}`, background:active?`${C.accent}10`:'transparent', cursor:'pointer' })}>
                <div style={s({ display:'flex', alignItems:'center', gap:8 })}>
                  <span style={{ fontSize:16, fontWeight:800 }}>{tier.icon}</span>
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

        <button className="primary-action" onClick={handleBook} disabled={booking||!!activeRide} style={s({ width:'100%', padding:'11px', background:C.accent, color:C.bg, border:'none', borderRadius:8, fontSize:13, fontWeight:700, cursor:booking||activeRide?'not-allowed':'pointer', opacity:booking||activeRide?0.6:1 })}>
          {geocoding ? 'Finding locations…' : booking ? 'Booking…' : activeRide ? 'Ride in progress' : 'Request Ride'}
        </button>

        {/* Recent */}
        <div>
          <div style={s({ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:10 })}>
            <p style={s({ color:C.text, fontSize:13, fontWeight:700 })}>Recent Rides</p>
            <button onClick={()=>setView('trips')} style={s({ background:'none', border:'none', color:C.accent, fontSize:11, fontWeight:700, cursor:'pointer' })}>All →</button>
          </div>
          {loading ? <p style={s({ color:C.muted, fontSize:12 })}>Loading…</p> :
           trips.length === 0 ? <p style={s({ color:C.muted, fontSize:12 })}>No rides yet.</p> :
           trips.slice(0,3).map(t => <TripCard key={t.id} trip={t} onClick={()=>openTrip(t)} />)
          }
        </div>
      </div>

      {/* ── Right live map ── */}
      <div className="map-surface" style={{ flex:1, position:'relative', minWidth:0, minHeight:0 }}>
        <div style={{ position:'absolute', inset:0 }}>
          <AppMap
            center={mapCenter}
            zoom={13}
            height="100%"
            pickup={mapPickup}
            destination={mapDestination}
            routeGeometry={routeGeometry}
            vehicles={activeRide ? [mapVehicle] : vehicles.filter(v => v.status !== 'offline')}
            vehicleAnimation={mapVehicleAnimation}
            pickupPulse={mapPickupPulse}
            onMapClick={mapPickupMode ? choosePickupOnMap : undefined}
          />
        </div>
        {mapPickupMode && (
          <div style={{ position:'absolute', top:54, left:'50%', transform:'translateX(-50%)', background:C.bg2, border:`1px solid ${C.accent}`, boxShadow:'0 2px 10px rgba(0,0,0,0.18)', borderRadius:20, padding:'8px 15px', zIndex:500, pointerEvents:'none' }}>
            <p style={{ color:C.text, fontSize:12, fontWeight:700 }}>Tap the map to choose pickup</p>
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Status badge ─────────────────────────────────────────────────────────────
const STATUS_COLOR = {
  pending:'#f59e0b', clustered:'#a78bfa', assigned:'#60a5fa',
  arriving:'#00c9a7', in_progress:'#00c9a7', completed:'#22c55e', cancelled:'#f43f5e',
}
function StatusBadge({ status }) {
  const col = STATUS_COLOR[status] || '#7a90b0'
  return <span style={s({ fontSize:10, fontWeight:800, textTransform:'uppercase', letterSpacing:'0.07em', color:col, background:col+'22', padding:'2px 8px', borderRadius:6 })}>{status.replace('_',' ')}</span>
}

function TripCard({ trip, onClick }) {
  return (
    <div onClick={onClick} style={s({ display:'flex', alignItems:'center', justifyContent:'space-between', padding:'9px 11px', background:C.surface2, border:`1px solid ${C.border}`, borderRadius:8, cursor:'pointer', marginBottom:6 })}>
      <div style={{ minWidth:0 }}>
        <p style={s({ color:C.text, fontSize:11, fontWeight:700, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' })}>→ {trip.destination_label || `${trip.dest_lat?.toFixed(3)}, ${trip.dest_lng?.toFixed(3)}`}</p>
        <p style={s({ color:C.muted, fontSize:10, marginTop:1 })}>{trip.request_time ? new Date(trip.request_time).toLocaleTimeString() : ''}</p>
      </div>
      <StatusBadge status={trip.status} />
    </div>
  )
}

function TripsView({ trips, loading, setView, onOpenTrip, title = 'My Trips' }) {
  return (
    <div style={s({ padding:28, maxWidth:720 })}>
      <div style={s({ display:'flex', alignItems:'center', gap:12, marginBottom:20 })}>
        <button onClick={()=>setView('home')} style={s({ background:'none', border:'none', color:C.muted2, cursor:'pointer', fontSize:13 })}>← Back</button>
        <h1 style={s({ color:C.text, fontSize:20, fontWeight:800, fontFamily:'Bricolage Grotesque,sans-serif' })}>{title}</h1>
      </div>
      {loading && <p style={s({ color:C.muted, fontSize:13 })}>Loading…</p>}
      {!loading && trips.length === 0 && <p style={s({ color:C.muted, fontSize:14 })}>No trips yet.</p>}
      <div style={s({ display:'flex', flexDirection:'column', gap:8 })}>
        {trips.map(t => (
          <div key={t.id} onClick={()=>onOpenTrip(t)} style={s({ display:'flex', justifyContent:'space-between', alignItems:'center', padding:'14px 16px', background:C.surface, border:`1px solid ${C.border}`, borderRadius:10, cursor:'pointer' })}>
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

function TripDetail({ ride, vehicle, onCancel, onBack }) {
  const canCancel = ['pending','clustered'].includes(ride.status)
  return (
    <div style={s({ padding:28, maxWidth:580 })}>
      <button onClick={onBack} style={s({ background:'none', border:'none', color:C.muted2, cursor:'pointer', fontSize:13, marginBottom:20 })}>← Back</button>
      <div style={s({ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:20 })}>
        <h1 style={s({ color:C.text, fontSize:20, fontWeight:800, fontFamily:'Bricolage Grotesque,sans-serif' })}>Ride #{ride.id}</h1>
        <StatusBadge status={ride.status} />
      </div>
      <div style={s({ display:'flex', flexDirection:'column', gap:10 })}>
        <InfoCard label="From" value={ride.pickup_label || `${ride.pickup_lat}, ${ride.pickup_lng}`} />
        <InfoCard label="To"   value={ride.destination_label || `${ride.dest_lat}, ${ride.dest_lng}`} />
        <InfoCard label="Ride tier" value={ride.ride_option_name || 'Standard'} />
        {ride.ride_option_price && <InfoCard label="Fare" value={ride.ride_option_price} />}
        {ride.h3_index  && <InfoCard label="H3 cell"  value={ride.h3_index} mono />}
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
      {canCancel && (
        <button onClick={onCancel} style={s({ marginTop:20, width:'100%', padding:'11px', background:'transparent', border:`1px solid ${C.danger}`, color:C.danger, borderRadius:9, fontSize:13, fontWeight:700, cursor:'pointer' })}>Cancel Ride</button>
      )}
    </div>
  )
}

function TrackingView({ ride, vehicle, routeGeometry, onBack }) {
  const pickupCoords = ride ? { lat:ride.pickup_lat, lng:ride.pickup_lng, label:ride.pickup_label } : null
  const destCoords   = ride ? { lat:ride.dest_lat,   lng:ride.dest_lng,   label:ride.destination_label } : null
  const displayVehicle = vehicle
  const trackingPickupPulse = !!ride && ['pending', 'clustered'].includes(ride.status)
  const vList = displayVehicle?.lat != null ? [displayVehicle] : []
  const center = displayVehicle?.lat != null ? [displayVehicle.lat, displayVehicle.lng] : ride ? [ride.pickup_lat, ride.pickup_lng] : [12.9784, 77.6408]
  
  const vehicleAnimation = displayVehicle && routeGeometry?.length > 1
    ? {
        key: `${displayVehicle.id}:${ride?.status}:${routeGeometry.length}`,
        vehicleId: displayVehicle.id,
        path: ['pending', 'clustered', 'assigned', 'arriving'].includes(ride?.status)
          ? [[displayVehicle.lng, displayVehicle.lat], [ride.pickup_lng, ride.pickup_lat]]
          : routeGeometry,
        durationMs: ride?.status === 'in_progress' ? 18000 : 8000,
        loop: true,
      }
    : null

  return (
    <div style={{ display:'flex', flexDirection:'column', flex:1, minHeight:0 }}>
      <div style={s({ padding:'12px 20px', borderBottom:`1px solid ${C.border}`, display:'flex', alignItems:'center', gap:12, background:C.bg2, flexShrink:0 })}>
        <button onClick={onBack} style={s({ background:'none', border:'none', color:C.muted2, cursor:'pointer', fontSize:13 })}>← Back</button>
        <p style={s({ color:C.text, fontSize:14, fontWeight:700 })}>Live Ride Tracking</p>
        {ride && <StatusBadge status={ride.status} />}
        {displayVehicle
          ? <p style={s({ color:C.accent, fontSize:12, marginLeft:'auto', fontWeight:700 })}>🚗 {displayVehicle.license_plate}</p>
          : ride && <p style={s({ color:C.muted2, fontSize:12, marginLeft:'auto' })}>⏳ Awaiting vehicle assignment…</p>}
      </div>
      <div style={{ flex:1, minHeight:0 }}>
        {!ride
          ? <div style={s({ padding:28 })}><p style={s({ color:C.muted, fontSize:14 })}>No active ride.</p></div>
          : <AppMap center={center} zoom={14} height="100%" vehicles={vList} pickup={pickupCoords} destination={destCoords} routeGeometry={routeGeometry} vehicleAnimation={vehicleAnimation} pickupPulse={trackingPickupPulse} followCamera={ride.status === 'in_progress'} />
        }
      </div>
    </div>
  )
}

function InfoCard({ label, value, mono=false }) {
  return (
    <div style={s({ display:'flex', justifyContent:'space-between', alignItems:'center', padding:'10px 14px', background:C.surface2, border:`1px solid ${C.border}`, borderRadius:8 })}>
      <p style={s({ color:C.muted2, fontSize:12 })}>{label}</p>
      <p style={s({ color:C.text, fontSize:13, fontWeight:600, fontFamily:mono?'monospace':'inherit' })}>{value}</p>
    </div>
  )
}

function SuggestionList({ items, onChoose }) {
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

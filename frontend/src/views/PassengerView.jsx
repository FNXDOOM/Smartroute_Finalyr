import { useState, useEffect, useRef, useCallback } from 'react'
import { useAuth } from '@clerk/clerk-react'
import {
  ArrowLeft, ArrowRight, Bike, CarFront, CheckCircle2, ChevronRight, CircleDot,
  Clock, Crown, Loader2, LocateFixed, MapPin, Navigation, Search, Users, X, Zap,
} from 'lucide-react'
import { ridesApi, geocodeApi, routingApi, createTrackingWS } from '../services/api.js'
import { useWebSocket } from '../hooks/useWebSocket.js'
import AppMap from '../components/AppMap'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Separator } from '@/components/ui/separator'
import { Switch } from '@/components/ui/switch'
import { Progress } from '@/components/ui/progress'
import { ScrollArea } from '@/components/ui/scroll-area'
import { StatusBadge, PageHeader, DashboardEmptyState, LoadingRows, MapLegend } from '@/components/dashboard-shared'

const RIDE_TIERS = [
  { id: 'swift-x', name: 'SwiftX', desc: 'Affordable shared ride', eta: '3 min', price: '₹12–15', Icon: CarFront, seats: 4 },
  { id: 'swift-xl', name: 'SwiftXL', desc: 'Extra space, small group', eta: '6 min', price: '₹18–22', Icon: Users, seats: 6 },
  { id: 'swift-lux', name: 'Lux Black', desc: 'Premium, top-rated driver', eta: '8 min', price: '₹32–40', Icon: Crown, seats: 4 },
  { id: 'swift-moto', name: 'Moto', desc: 'Fast, budget solo', eta: '2 min', price: '₹6–9', Icon: Bike, seats: 1 },
]

const RIDE_STAGES = ['pending', 'clustered', 'assigned', 'arriving', 'in_progress', 'completed']
const RIDE_STAGE_LABELS = { pending: 'Requested', clustered: 'Clustered', assigned: 'Assigned', arriving: 'Arriving', in_progress: 'In transit', completed: 'Delivered' }

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
  const dismissTimeoutRef = useRef(null)
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

  const clearActiveRideState = useCallback(() => {
    if (dismissTimeoutRef.current) { clearTimeout(dismissTimeoutRef.current); dismissTimeoutRef.current = null }
    setActiveRide(null); setRideVehicle(null)
    setRouteGeometry([]); setRouteEstimate(null)
  }, [])

  useEffect(() => {
    if (!activeRideId) { clearInterval(pollRef.current); return undefined }
    const poll = async () => {
      try {
        const v = await ridesApi.getVehicle(activeRideId)
        setRideVehicle(v)
        const r = await ridesApi.getById(activeRideId)
        setActiveRide(r)
        setTrips(prev => prev.map(t => t.id === r.id ? r : t))
        if (r.status === 'completed' || r.status === 'cancelled') {
          clearInterval(pollRef.current)
          if (r.status === 'completed') toast('success', 'Ride completed!', 'Tap Dismiss to book a new ride.')
          else toast('info', 'Ride ' + r.status)
          // Auto-dismiss finished card to allow new bookings.
          if (dismissTimeoutRef.current) clearTimeout(dismissTimeoutRef.current)
          dismissTimeoutRef.current = setTimeout(() => {
            setActiveRide(null); setRideVehicle(null)
            setRouteGeometry([]); setRouteEstimate(null)
            dismissTimeoutRef.current = null
          }, 8000)
        }
      } catch (error) { void error }
    }
    poll()
    pollRef.current = setInterval(poll, 4000)
    return () => {
      clearInterval(pollRef.current)
      if (dismissTimeoutRef.current) { clearTimeout(dismissTimeoutRef.current); dismissTimeoutRef.current = null }
    }
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
      if (dismissTimeoutRef.current) { clearTimeout(dismissTimeoutRef.current); dismissTimeoutRef.current = null }
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
      clearActiveRideState()
      setTrips(prev => prev.map(t => t.id===activeRide.id?{...t,status:'cancelled'}:t))
      toast('info','Ride cancelled')
    } catch(e) { toast('error','Cannot cancel', e?.response?.data?.detail||'') }
  }

  // Only active trips take over Home booking card.
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
      ? <TripDetail ride={detailRide} vehicle={activeRide ? rideVehicle : null} onCancel={handleCancel} onBack={() => { setViewingRide(null); setView('home') }} />
      : <div className="p-7"><Button variant="ghost" size="sm" onClick={() => setView('home')}><ArrowLeft className="h-4 w-4" /> Back home</Button></div>
  }
  if (view === 'tracking') return <TrackingView ride={activeRide} vehicle={rideVehicle} routeGeometry={routeGeometry} onBack={()=>setView('home')} />

  // Home booking layout
  const pickupCoords  = { lat:pickupPoint.lat, lng:pickupPoint.lng, label: pickup||'Current location' }
  const destCoords    = destinationPoint || null
  // Show vehicle only after backend assigns one.
  const mapVehicle = rideVehicle
  // Simulate driver marker from ride stage.
  const simDriver = (!mapVehicle && activeRide && activeRide.pickup_lat != null && activeRide.dest_lat != null
    && ['assigned', 'arriving', 'in_progress'].includes(activeRide.status))
    ? (() => {
        const st = activeRide.status
        if (st === 'in_progress') {
          const path = routeGeometry.length > 1
            ? routeGeometry
            : [[activeRide.pickup_lng, activeRide.pickup_lat], [activeRide.dest_lng, activeRide.dest_lat]]
          return {
            vehicle: { id: 'sim-driver', license_plate: 'Your driver', status: 'en_route', lat: path[0][1], lng: path[0][0] },
            path,
            durationMs: 18000,
            label: "You're on your way — sit back",
          }
        }
        const off = st === 'arriving' ? 0.004 : 0.012
        const start = [activeRide.pickup_lng + off, activeRide.pickup_lat + off * 0.6]
        return {
          vehicle: { id: 'sim-driver', license_plate: 'Your driver', status: 'en_route', lat: start[1], lng: start[0] },
          path: [start, [activeRide.pickup_lng, activeRide.pickup_lat]],
          durationMs: st === 'arriving' ? 12000 : 25000,
          label: st === 'arriving' ? 'Driver arriving at your pickup' : 'Driver found — on the way to you',
        }
      })()
    : null
  const displayVehicle = mapVehicle || simDriver?.vehicle || null
  const isRideActive = !!activeRide && !['completed', 'cancelled'].includes(activeRide.status)
  const mapPickupPulse = !!activeRide && ['pending', 'clustered'].includes(activeRide.status)
  const mapPickup = activeRide ? { lat:activeRide.pickup_lat, lng:activeRide.pickup_lng, label:activeRide.pickup_label } : pickupCoords
  const mapDestination = activeRide ? { lat:activeRide.dest_lat, lng:activeRide.dest_lng, label:activeRide.destination_label } : destCoords
  
  const mapVehicleAnimation = displayVehicle && activeRide && isRideActive && (routeGeometry.length > 1 || simDriver)
    ? mapVehicle
      ? {
          key: `${mapVehicle.id}:${activeRide.status}:${routeGeometry.length}`,
          vehicleId: mapVehicle.id,
          path: ['pending', 'clustered', 'assigned', 'arriving'].includes(activeRide.status)
            ? [[mapVehicle.lng, mapVehicle.lat], [activeRide.pickup_lng, activeRide.pickup_lat]]
            : routeGeometry,
          durationMs: activeRide.status === 'in_progress' ? 18000 : 8000,
          loop: true,
        }
      : {
          key: `sim-driver:${activeRide.id}:${activeRide.status}`,
          vehicleId: displayVehicle.id,
          path: simDriver.path,
          durationMs: simDriver.durationMs,
          loop: true,
        }
    : null

  const mapCenter = activeRide
    ? [(activeRide.pickup_lat + activeRide.dest_lat) / 2, (activeRide.pickup_lng + activeRide.dest_lng) / 2]
    : destinationPoint
    ? [(pickupPoint.lat + destinationPoint.lat) / 2, (pickupPoint.lng + destinationPoint.lng) / 2]
    : (gpsActive || !!pickup.trim()) ? [pickupPoint.lat, pickupPoint.lng] : [12.9784, 77.6408]

  const activeStageIndex = activeRide ? RIDE_STAGES.indexOf(activeRide.status) : -1
  const activeProgress = activeRide ? Math.max(0, Math.min(100, ((activeStageIndex + 1) / RIDE_STAGES.length) * 100)) : 0

  return (
    <div className="booking-layout relative flex min-h-0 flex-1 flex-col overflow-hidden lg:block">
      {/* ── Floating booking panel: bottom sheet on mobile, floating card on desktop ── */}
      <div className="relative z-10 order-2 flex min-h-0 flex-1 flex-col lg:pointer-events-none lg:absolute lg:bottom-6 lg:left-6 lg:top-6 lg:order-none lg:w-[400px] lg:flex-none">
      <ScrollArea className="booking-panel pointer-events-auto max-h-[62dvh] w-full min-h-0 flex-1 overflow-y-auto rounded-t-[16px] border-t border-[#E2E2E2] bg-white shadow-[0_-8px_30px_rgba(0,0,0,0.12)] lg:max-h-none lg:h-full lg:rounded-2xl lg:border lg:bg-white lg:shadow-[0_8px_24px_rgba(0,0,0,0.12)] dark:border-[#333333] dark:bg-[#1F1F1F]">
        <div className="mx-auto mt-2.5 h-1 w-10 shrink-0 rounded-full bg-[#D6D6D6] lg:hidden" aria-hidden="true" />
        <div className="flex flex-col gap-5 p-5 md:p-7">
          <div>
            <p className="uber-eyebrow mb-1.5">Request a ride</p>
            <h2 className="text-[28px] font-bold leading-tight tracking-[-0.02em]">Where to?</h2>
            <p className="mt-1 text-[14px] text-[#6B6B6B] dark:text-[#AFAFAF]">Flat fares · No surge · Shared options</p>
          </div>

          {/* Active booking — 6-stage stepper */}
          {activeRide && (
            <Card className="border-black shadow-none dark:border-white">
              <CardContent className="space-y-3 p-5">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-[#8A8A8A]">Active booking</p>
                    <p className="mt-1 truncate text-[15px] font-bold tracking-[-0.01em]">Ride #{activeRide.id} · {activeRide.ride_option_name || 'SwiftX'}</p>
                  </div>
                  <StatusBadge status={activeRide.status} />
                </div>

                <div>
                  <Progress value={activeProgress} className="h-1.5 bg-[#EEEEEE] dark:bg-[#333333]" aria-label={`Ride stage ${activeStageIndex + 1} of ${RIDE_STAGES.length}`} />
                  <ol className="mt-2.5 grid grid-cols-3 gap-1 sm:grid-cols-6" aria-label="Ride progress">
                    {RIDE_STAGES.map((key, idx) => {
                      const passed = activeStageIndex >= idx
                      const current = activeRide.status === key
                      return (
                        <li key={key} className="flex min-w-0 flex-col items-center gap-1 text-center">
                          <span
                            className={cn(
                              'flex h-6 w-6 items-center justify-center rounded-full text-[11px] font-bold',
                              current ? 'bg-black text-white ring-2 ring-black/20 dark:bg-white dark:text-black dark:ring-white/30'
                                : passed ? 'bg-black text-white dark:bg-white dark:text-black'
                                  : 'bg-[#EEEEEE] text-[#8A8A8A] dark:bg-[#333333] dark:text-[#8A8A8A]',
                            )}
                            aria-current={current ? 'step' : undefined}
                          >
                            {passed && !current ? <CheckCircle2 className="h-3 w-3" /> : idx + 1}
                          </span>
                          <span className={cn('hidden truncate text-[10px] font-medium leading-tight sm:block', current ? 'text-black dark:text-white' : passed ? 'text-[#333333] dark:text-[#E2E2E2]' : 'text-[#8A8A8A]')}>
                            {RIDE_STAGE_LABELS[key]}
                          </span>
                          <span className={cn('truncate text-[10px] font-medium leading-tight sm:hidden', current ? 'text-black dark:text-white' : 'text-[#8A8A8A]')}>
                            {current ? RIDE_STAGE_LABELS[key] : idx + 1}
                          </span>
                        </li>
                      )
                    })}
                  </ol>
                </div>

                {displayVehicle && (
                  <div className="flex items-center gap-3 rounded-xl border border-[#E2E2E2] bg-[#F6F6F6] p-3 dark:border-[#333333] dark:bg-[#2A2A2A]">
                    <Avatar className="h-10 w-10 shrink-0 rounded-lg">
                      <AvatarFallback className="rounded-lg bg-black text-[13px] font-bold text-white dark:bg-white dark:text-black">{mapVehicle ? 'RK' : 'D'}</AvatarFallback>
                    </Avatar>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-2">
                        <p className="truncate text-[13px] font-semibold">
                          {mapVehicle ? 'Rajesh Kumar' : 'Your driver'}
                          {mapVehicle && <span className="ml-1.5 text-[12px] font-semibold text-black dark:text-white">★ 4.9</span>}
                        </p>
                        <Badge variant="secondary" className="shrink-0 font-mono text-[11px]">{displayVehicle.license_plate}</Badge>
                      </div>
                      <p className="mt-0.5 truncate text-[12px] text-[#6B6B6B] dark:text-[#AFAFAF]">{mapVehicle ? 'Tata Tigor EV · White · 3 seats shared' : simDriver?.label || 'On the way'}</p>
                    </div>
                  </div>
                )}

                {isRideActive ? (
                  <div className="flex gap-2">
                    <Button className="flex-1" size="sm" onClick={() => setView('tracking')}>
                      <Navigation className="h-3.5 w-3.5" /> Fullscreen tracking
                    </Button>
                    <Button variant="outline" size="sm" onClick={handleCancel} className="text-destructive hover:text-destructive">
                      Cancel
                    </Button>
                  </div>
                ) : (
                  <div className="flex flex-col gap-1.5">
                    <p className="text-center text-[11px] text-muted-foreground">Auto-dismisses in a few seconds…</p>
                    <Button className="w-full" size="sm" onClick={clearActiveRideState}>Dismiss · Book new ride</Button>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {/* Pickup / destination */}
          <div className="space-y-3">
            <div className="space-y-2">
              <Label htmlFor="pickup-input" className="text-[13px] font-semibold">Pickup</Label>
              <div className="flex min-h-[52px] items-center gap-2.5 rounded-lg border border-[#D6D6D6] bg-white px-4 transition-[border-color,box-shadow] duration-150 focus-within:border-black focus-within:ring-[3px] focus-within:ring-black/10 dark:border-[#333333] dark:bg-[#1F1F1F] dark:focus-within:border-white dark:focus-within:ring-white/15">
                <MapPin className="h-[18px] w-[18px] shrink-0 text-[#6B6B6B]" aria-hidden="true" />
                <Input
                  id="pickup-input"
                  value={pickup}
                  onFocus={() => setSuggestionField('pickup')}
                  onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); void searchLocation('pickup') } }}
                  onChange={e => { setPickup(e.target.value); setSuggestions([]); setPickupConfirmed(false); setGpsActive(false); setMapPickupMode(false) }}
                  placeholder="Pickup location"
                  className="h-[50px] border-0 bg-transparent px-0 shadow-none hover:border-transparent focus-visible:border-transparent focus-visible:ring-0"
                  autoComplete="off"
                />
              </div>
              <div className="flex items-center justify-end gap-1">
                <Button variant="ghost" size="sm" className="h-8 text-[12px] font-medium" onClick={() => { setMapPickupMode(v => !v); setSuggestionField(null) }} disabled={mapPickupLoading}>
                  {mapPickupLoading ? <><Loader2 className="h-3 w-3 animate-spin" /> Selecting…</> : mapPickupMode ? 'Cancel map pick' : 'Choose on map'}
                </Button>
                <Button variant="ghost" size="sm" className="h-8 gap-1.5 text-[12px] font-medium" onClick={useCurrentLocation} disabled={gpsLoading || mapPickupLoading}>
                  <LocateFixed className="h-3.5 w-3.5" />{gpsLoading ? 'Locating…' : gpsActive ? 'GPS on' : 'Use GPS'}
                </Button>
              </div>
            </div>
            {suggestionField === 'pickup' && suggestions.length > 0 && (
              <SuggestionList items={suggestions} onChoose={point => chooseSuggestion('pickup', point)} />
            )}
            {locationError && <p role="alert" className="rounded-lg border border-[#D93025]/25 bg-[#D93025]/10 px-3 py-2 text-[13px] text-[#D93025]">{locationError}</p>}
            <div className="space-y-2">
              <Label htmlFor="dest-input" className="text-[13px] font-semibold">Destination</Label>
              <div className="flex min-h-[52px] items-center gap-2.5 rounded-lg border border-[#D6D6D6] bg-white px-4 transition-[border-color,box-shadow] duration-150 focus-within:border-black focus-within:ring-[3px] focus-within:ring-black/10 dark:border-[#333333] dark:bg-[#1F1F1F] dark:focus-within:border-white dark:focus-within:ring-white/15">
                <Search className="h-[18px] w-[18px] shrink-0 text-[#6B6B6B]" aria-hidden="true" />
                <Input
                  id="dest-input"
                  value={dest}
                  onFocus={() => setSuggestionField('destination')}
                  onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); void searchLocation('destination') } }}
                  onChange={e => { setDest(e.target.value); setSuggestions([]); setDestinationConfirmed(false); setDestinationPoint(null); setRouteGeometry([]); setRouteEstimate(null) }}
                  placeholder="Where to?"
                  className="h-[50px] border-0 bg-transparent px-0 shadow-none hover:border-transparent focus-visible:border-transparent focus-visible:ring-0"
                  autoComplete="off"
                />
              </div>
            </div>
            {suggestionField === 'destination' && suggestions.length > 0 && (
              <SuggestionList items={suggestions} onChoose={point => chooseSuggestion('destination', point)} />
            )}
          </div>

          {routeEstimate && (
            <div className="flex items-center justify-between rounded-xl border border-[#E2E2E2] bg-[#F6F6F6] px-4 py-3 text-[13px] dark:border-[#333333] dark:bg-[#2A2A2A]">
              <span className="flex items-center gap-2 text-[#545454] dark:text-[#AFAFAF]"><Clock className="h-4 w-4" /> Route estimate</span>
              <strong className="tabular-nums text-black dark:text-white">{(routeEstimate.distanceMeters / 1000).toFixed(1)} km · {Math.max(1, Math.round(routeEstimate.durationSeconds / 60))} min</strong>
            </div>
          )}

          <div className="flex items-center justify-between gap-3 rounded-xl border border-[#E2E2E2] px-4 py-3 dark:border-[#333333]">
            <Label htmlFor="traffic-switch" className="cursor-pointer text-[13px] font-medium normal-case tracking-normal">Use live traffic for route and ETA</Label>
            <Switch id="traffic-switch" checked={trafficRouting} onCheckedChange={setTrafficRouting} aria-label="Use live traffic" />
          </div>

          {/* Ride tiers — price/status first, details second */}
          <div>
            <p className="mb-2.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-[#8A8A8A]">Choose a ride</p>
            <div className="flex flex-col gap-2" role="radiogroup" aria-label="Ride options">
              {RIDE_TIERS.map(tier => {
                const active = selected === tier.id
                const TierIcon = tier.Icon
                return (
                  <button
                    key={tier.id}
                    role="radio"
                    aria-checked={active}
                    onClick={() => setSelected(tier.id)}
                    className={cn(
                      'ride-tier flex items-center justify-between gap-3 rounded-xl border p-3 text-left focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-black dark:focus-visible:outline-white',
                      active ? 'border-black bg-[#F6F6F6] shadow-[0_2px_8px_rgba(0,0,0,0.08)] dark:border-white dark:bg-[#2A2A2A]' : 'border-[#E2E2E2] bg-white hover:border-[#AFAFAF] dark:border-[#333333] dark:bg-transparent',
                    )}
                  >
                    <span className="flex min-w-0 items-center gap-3">
                      <span className={cn('flex h-11 w-11 shrink-0 items-center justify-center rounded-lg', active ? 'bg-black text-white dark:bg-white dark:text-black' : 'bg-[#F6F6F6] text-[#545454] dark:bg-[#2A2A2A] dark:text-[#AFAFAF]')}>
                        <TierIcon className="h-[18px] w-[18px]" aria-hidden="true" />
                      </span>
                      <span className="min-w-0">
                        <span className="block truncate text-[15px] font-semibold leading-tight tracking-[-0.01em]">{tier.name}</span>
                        <span className="mt-0.5 block truncate text-[12px] text-[#6B6B6B] dark:text-[#AFAFAF]">{tier.desc} · {tier.eta} · {tier.seats} seats</span>
                      </span>
                    </span>
                    <span className="shrink-0 text-[15px] font-bold tabular-nums">{tier.price}</span>
                  </button>
                )
              })}
            </div>
          </div>

          <Button className="primary-action uber-cta h-[52px] w-full text-[16px]" onClick={handleBook} disabled={booking || isRideActive} size="lg">
            {geocoding ? <><Loader2 className="h-4 w-4 animate-spin" /> Finding locations…</>
              : booking ? <><Loader2 className="h-4 w-4 animate-spin" /> Booking…</>
                : isRideActive ? 'Ride in progress'
                  : <>Request ride</>}
          </Button>

          {/* Recent */}
          <div>
            <div className="mb-2.5 flex items-center justify-between">
              <p className="text-[15px] font-semibold tracking-[-0.01em]">Recent rides</p>
              <Button variant="ghost" size="sm" className="h-8 gap-1 text-[13px] font-medium" onClick={() => setView('trips')}>
                View all <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
            {loading ? <LoadingRows count={3} height="h-[56px]" />
              : trips.length === 0 ? <DashboardEmptyState icon={CircleDot} title="No rides yet" hint="Your recent bookings will appear here once you request your first ride." />
                : <div className="flex flex-col gap-2">{trips.slice(0, 3).map(t => <TripCard key={t.id} trip={t} onClick={() => openTrip(t)} />)}</div>
            }
          </div>
        </div>
      </ScrollArea>
      </div>

      {/* ── Live map: centerpiece, full-bleed ── */}
      <div className="map-surface order-1 relative h-[38dvh] min-h-[280px] w-full shrink-0 overflow-hidden lg:absolute lg:inset-0 lg:order-none lg:h-full lg:rounded-none">
        <div className="absolute inset-0">
          <AppMap
            center={mapCenter}
            zoom={13}
            height="100%"
            pickup={mapPickup}
            destination={mapDestination}
            routeGeometry={routeGeometry}
            vehicles={activeRide && displayVehicle ? [displayVehicle] : activeRide ? [] : vehicles.filter(v => v.status !== 'offline')}
            vehicleAnimation={mapVehicleAnimation}
            pickupPulse={mapPickupPulse}
            onMapClick={mapPickupMode ? choosePickupOnMap : undefined}
            style={{ borderRadius: 0 }}
          />
        </div>
        {mapPickupMode && (
          <div className="pointer-events-none absolute left-1/2 top-4 z-10 -translate-x-1/2">
            <Badge className="border-[#E2E2E2] bg-white px-3 py-1.5 text-[13px] font-semibold text-black shadow-[0_8px_24px_rgba(0,0,0,0.12)]">Tap the map to choose pickup</Badge>
          </div>
        )}
        {isRideActive && activeRide && (
          <button
            onClick={() => setView('tracking')}
            className="absolute left-1/2 top-4 z-10 hidden -translate-x-1/2 items-center gap-2.5 rounded-lg border border-[#E2E2E2] bg-white py-2 pl-4 pr-2 text-[13px] font-semibold text-black shadow-[0_8px_24px_rgba(0,0,0,0.12)] transition-colors duration-150 hover:border-black focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-black lg:left-[calc(448px+((100%-448px)/2))] lg:flex"
          >
            <span className="h-2 w-2 animate-pulse rounded-full bg-black" aria-hidden="true" />
            Ride #{activeRide.id} · {RIDE_STAGE_LABELS[activeRide.status] || activeRide.status.replace(/_/g, ' ')}
            <span className="rounded-md bg-black px-2.5 py-1 text-[12px] font-semibold text-white">Track</span>
          </button>
        )}
        <div className="absolute bottom-4 left-4 z-10 hidden rounded-xl border border-[#E2E2E2] bg-white px-3 py-2.5 shadow-[0_2px_8px_rgba(0,0,0,0.08)] lg:block">
          <MapLegend
            items={[
              { color: '#000000', label: 'Pickup' },
              { color: '#545454', label: 'Drop-off' },
              { color: '#000000', label: 'Vehicle' },
            ]}
          />
        </div>
        {routeEstimate && (
          <Card className="absolute bottom-4 right-4 z-10 border-[#E2E2E2] bg-white shadow-[0_2px_8px_rgba(0,0,0,0.08)]">
            <CardContent className="mob-data flex items-center gap-2 px-3.5 py-2.5 text-[13px]">
              <Navigation className="h-4 w-4 text-black" />
              <strong className="tabular-nums">{(routeEstimate.distanceMeters / 1000).toFixed(1)} km</strong>
              <span className="text-[#6B6B6B]">· {Math.max(1, Math.round(routeEstimate.durationSeconds / 60))} min</span>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
}

function TripCard({ trip, onClick }) {
  return (
    <Card
      onClick={onClick}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick?.() } }}
      tabIndex={0}
      role="button"
      className="cursor-pointer shadow-none transition-[border-color,background-color] duration-150 hover:border-[#AFAFAF] hover:bg-[#F6F6F6] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-black"
    >
      <CardContent className="flex items-center justify-between gap-3 p-3.5">
        <div className="min-w-0">
          <p className="truncate text-[14px] font-semibold">→ {trip.destination_label || `${trip.dest_lat?.toFixed(3)}, ${trip.dest_lng?.toFixed(3)}`}</p>
          <p className="mt-0.5 text-[12px] text-[#6B6B6B]">{trip.request_time ? new Date(trip.request_time).toLocaleTimeString() : ''}</p>
        </div>
        <StatusBadge status={trip.status} />
      </CardContent>
    </Card>
  )
}

function TripsView({ trips, loading, setView, onOpenTrip, title = 'My Trips' }) {
  return (
    <div className="mx-auto w-full max-w-[720px] space-y-5 p-4 md:p-8">
      <PageHeader
        title={title}
        description={trips.length ? `${trips.length} booking${trips.length === 1 ? '' : 's'}` : 'Your ride history'}
        onBack={() => setView('home')}
        backLabel="Home"
      />
      {loading && <LoadingRows count={4} />}
      {!loading && trips.length === 0 && (
        <DashboardEmptyState
          icon={CircleDot}
          title="No trips yet"
          hint="Book your first ride from Home — it will show up here with live status."
          action={<Button size="sm" onClick={() => setView('home')}>Book a ride</Button>}
        />
      )}
      <div className="flex flex-col gap-2">
        {trips.map(t => (
          <Card
            key={t.id}
            onClick={() => onOpenTrip(t)}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onOpenTrip(t) } }}
            tabIndex={0}
            role="button"
            className="cursor-pointer shadow-none transition-[border-color,background-color] duration-150 hover:border-[#AFAFAF] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-black"
          >
            <CardContent className="flex items-center justify-between gap-3 p-4">
              <div className="min-w-0">
                <div className="mb-1.5 flex flex-wrap items-center gap-2">
                  <span className="font-mono text-[12px] text-[#8A8A8A]">#{t.id}</span>
                  <StatusBadge status={t.status} />
                </div>
                <p className="truncate text-[14px] font-semibold tracking-[-0.01em]">
                  {t.pickup_label || 'Pickup'} <ArrowRight className="mx-1 inline h-4 w-4 text-[#8A8A8A]" />
                  {t.destination_label || 'Destination'}
                </p>
                <p className="mt-1 truncate text-[12px] text-[#6B6B6B]">{t.ride_option_name || 'Standard'} · {t.request_time ? new Date(t.request_time).toLocaleString() : ''}</p>
              </div>
              <ChevronRight className="h-[18px] w-[18px] shrink-0 text-[#8A8A8A]" aria-hidden="true" />
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}

function TripDetail({ ride, vehicle, onCancel, onBack }) {
  const canCancel = ['pending', 'clustered'].includes(ride.status)
  return (
    <div className="mx-auto w-full max-w-[580px] space-y-5 p-4 md:p-8">
      <PageHeader title={`Ride #${ride.id}`} description={ride.request_time ? new Date(ride.request_time).toLocaleString() : undefined} onBack={onBack} backLabel="Back" actions={<StatusBadge status={ride.status} />} />
      <Card className="shadow-none">
        <CardContent className="flex flex-col gap-2 p-5">
          <InfoCard label="From" value={ride.pickup_label || `${ride.pickup_lat}, ${ride.pickup_lng}`} />
          <InfoCard label="To" value={ride.destination_label || `${ride.dest_lat}, ${ride.dest_lng}`} />
          <InfoCard label="Ride tier" value={ride.ride_option_name || 'Standard'} />
          {ride.ride_option_price && <InfoCard label="Fare" value={ride.ride_option_price} />}
          {ride.h3_index && <InfoCard label="H3 cell" value={ride.h3_index} mono />}
          {ride.request_time && <InfoCard label="Requested" value={new Date(ride.request_time).toLocaleString()} />}
        </CardContent>
      </Card>

      {vehicle && (
        <Card className="border-black shadow-none dark:border-white">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-[15px]"><CarFront className="h-[18px] w-[18px]" /> Assigned vehicle</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-x-8 gap-y-3 pb-5">
            <div><p className="text-[12px] text-[#6B6B6B]">Plate</p><p className="font-mono text-[14px] font-semibold">{vehicle.license_plate}</p></div>
            <div><p className="text-[12px] text-[#6B6B6B]">Status</p><p className="text-[14px] font-semibold capitalize">{vehicle.status}</p></div>
            {vehicle.lat && <div><p className="text-[12px] text-[#6B6B6B]">Location</p><p className="font-mono text-[14px] font-semibold">{vehicle.lat.toFixed(4)}, {vehicle.lng.toFixed(4)}</p></div>}
          </CardContent>
        </Card>
      )}
      {canCancel && (
        <Button variant="outline" onClick={onCancel} className="h-12 w-full text-[#D93025] hover:text-[#D93025]">
          <X className="h-4 w-4" /> Cancel ride
        </Button>
      )}
    </div>
  )
}

function TrackingView({ ride, vehicle, routeGeometry, onBack }) {
  const pickupCoords = ride ? { lat: ride.pickup_lat, lng: ride.pickup_lng, label: ride.pickup_label } : null
  const destCoords = ride ? { lat: ride.dest_lat, lng: ride.dest_lng, label: ride.destination_label } : null
  // Same driver simulation as Home.
  const simDriver = (!vehicle && ride && ride.pickup_lat != null && ride.dest_lat != null
    && ['assigned', 'arriving', 'in_progress'].includes(ride.status))
    ? (() => {
      if (ride.status === 'in_progress') {
        const path = routeGeometry?.length > 1
          ? routeGeometry
          : [[ride.pickup_lng, ride.pickup_lat], [ride.dest_lng, ride.dest_lat]]
        return { vehicle: { id: 'sim-driver', license_plate: 'Your driver', status: 'en_route', lat: path[0][1], lng: path[0][0] }, path, durationMs: 18000 }
      }
      const off = ride.status === 'arriving' ? 0.004 : 0.012
      const start = [ride.pickup_lng + off, ride.pickup_lat + off * 0.6]
      return {
        vehicle: { id: 'sim-driver', license_plate: 'Your driver', status: 'en_route', lat: start[1], lng: start[0] },
        path: [start, [ride.pickup_lng, ride.pickup_lat]],
        durationMs: ride.status === 'arriving' ? 12000 : 25000,
      }
    })()
    : null
  const displayVehicle = vehicle || simDriver?.vehicle || null
  const trackingPickupPulse = !!ride && ['pending', 'clustered'].includes(ride.status)
  const vList = displayVehicle?.lat != null ? [displayVehicle] : []
  const center = displayVehicle?.lat != null ? [displayVehicle.lat, displayVehicle.lng] : ride ? [ride.pickup_lat, ride.pickup_lng] : [12.9784, 77.6408]

  const vehicleAnimation = displayVehicle && (routeGeometry?.length > 1 || simDriver)
    ? vehicle
      ? {
        key: `${displayVehicle.id}:${ride?.status}:${routeGeometry.length}`,
        vehicleId: displayVehicle.id,
        path: ['pending', 'clustered', 'assigned', 'arriving'].includes(ride?.status)
          ? [[displayVehicle.lng, displayVehicle.lat], [ride.pickup_lng, ride.pickup_lat]]
          : routeGeometry,
        durationMs: ride?.status === 'in_progress' ? 18000 : 8000,
        loop: true,
      }
      : {
        key: `sim-driver:${ride?.id}:${ride?.status}`,
        vehicleId: displayVehicle.id,
        path: simDriver.path,
        durationMs: simDriver.durationMs,
        loop: true,
      }
    : null

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex shrink-0 flex-wrap items-center gap-2.5 border-b border-[#E2E2E2] bg-white px-4 py-3 md:px-8 dark:border-[#333333] dark:bg-black">
        <Button variant="ghost" size="sm" onClick={onBack} className="gap-1.5">
          <ArrowLeft className="h-4 w-4" /> Back
        </Button>
        <Separator orientation="vertical" className="h-5 bg-[#E2E2E2] dark:bg-[#333333]" />
        <p className="text-[15px] font-semibold tracking-[-0.01em]">Live ride tracking</p>
        {ride && <StatusBadge status={ride.status} />}
        <span className="ml-auto text-[13px] text-[#6B6B6B]">
          {displayVehicle
            ? <Badge variant="secondary" className="gap-1.5 font-mono text-[12px]"><CarFront className="h-3.5 w-3.5" /> {displayVehicle.license_plate}</Badge>
            : ride && 'Awaiting vehicle assignment…'}
        </span>
      </div>
      <div className="min-h-0 flex-1 bg-[#EEEEEE] dark:bg-[#111111]">
        {!ride
          ? <div className="mx-auto w-full max-w-[560px] p-4 md:p-8"><DashboardEmptyState icon={Navigation} title="No active ride" hint="Start a booking from Home to track it live here." action={<Button size="sm" onClick={onBack}>Back home</Button>} /></div>
          : <AppMap center={center} zoom={14} height="100%" vehicles={vList} pickup={pickupCoords} destination={destCoords} routeGeometry={routeGeometry} vehicleAnimation={vehicleAnimation} pickupPulse={trackingPickupPulse} followCamera={ride.status === 'in_progress'} />
        }
      </div>
    </div>
  )
}

function InfoCard({ label, value, mono = false }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-[#E2E2E2] bg-[#F6F6F6] px-3.5 py-2.5 dark:border-[#333333] dark:bg-[#2A2A2A]">
      <p className="shrink-0 text-[13px] text-[#6B6B6B] dark:text-[#AFAFAF]">{label}</p>
      <p className={cn('min-w-0 truncate text-right text-[14px] font-semibold', mono && 'font-mono tabular-nums')}>{value}</p>
    </div>
  )
}

function SuggestionList({ items, onChoose }) {
  return (
    <Card className="relative z-20 max-h-56 overflow-y-auto rounded-xl border-[#E2E2E2] shadow-[0_8px_24px_rgba(0,0,0,0.12)]" role="listbox" aria-label="Location suggestions">
      {items.map((item, index) => (
        <button
          key={`${item.lat}-${item.lng}-${index}`}
          role="option"
          aria-selected="false"
          onMouseDown={event => event.preventDefault()}
          onClick={() => onChoose(item)}
          className="block w-full border-b border-[#EEEEEE] px-4 py-2.5 text-left transition-colors duration-150 last:border-0 hover:bg-[#F6F6F6] focus-visible:bg-[#F6F6F6] focus-visible:outline-none dark:border-[#333333] dark:hover:bg-[#2A2A2A]"
        >
          <span className="block truncate text-[13px] font-semibold">{item.label.split(',')[0]}</span>
          <span className="mt-0.5 block truncate text-[12px] text-[#6B6B6B]">{item.label}</span>
        </button>
      ))}
    </Card>
  )
}

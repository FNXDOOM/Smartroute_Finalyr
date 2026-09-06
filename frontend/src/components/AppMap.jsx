/** Shared MapLibre map used by passenger, driver, and admin views. */
import { useEffect, useRef, useState } from 'react'
import { useAuth } from '@clerk/clerk-react'
import * as maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '')
const STADIA_STYLE_URL = `${API_BASE_URL}/maps/stadia/style.json`

function applyDarkMapTheme(map) {
  const layers = map.getStyle()?.layers || []
  for (const layer of layers) {
    const sourceLayer = String(layer['source-layer'] || '').toLowerCase()
    const layerId = layer.id.toLowerCase()
    try {
      if (layer.type === 'background') {
        map.setPaintProperty(layer.id, 'background-color', '#252a28')
      } else if (layer.type === 'fill' && sourceLayer.includes('water')) {
        map.setPaintProperty(layer.id, 'fill-color', '#182c2b')
      } else if (layer.type === 'fill' && (sourceLayer.includes('building') || layerId.includes('building'))) {
        map.setPaintProperty(layer.id, 'fill-color', '#2b322f')
        map.setPaintProperty(layer.id, 'fill-outline-color', '#37403b')
      } else if (layer.type === 'fill') {
        map.setPaintProperty(layer.id, 'fill-color', '#202624')
      } else if (layer.type === 'line' && (
        sourceLayer.includes('road') ||
        sourceLayer.includes('transport') ||
        sourceLayer.includes('highway') ||
        layerId.includes('road') ||
        layerId.includes('transport')
      )) {
        map.setPaintProperty(layer.id, 'line-color', '#56615b')
        map.setPaintProperty(layer.id, 'line-opacity', .72)
      } else if (layer.type === 'symbol') {
        map.setPaintProperty(layer.id, 'text-color', '#d7d4c8')
        map.setPaintProperty(layer.id, 'text-halo-color', '#141918')
        map.setPaintProperty(layer.id, 'text-opacity', .78)
      }
    } catch {
      // Some vendor layers expose a layout-only paint property set.
    }
  }
}

function backendMapUrl(url) {
  try {
    const parsed = new URL(url, window.location.origin)
    if (!parsed.pathname.startsWith('/maps/stadia/')) return url
    return `${API_BASE_URL}${parsed.pathname}${parsed.search}`
  } catch {
    return url
  }
}

const colours = {
  pickup: '#00c9a7',
  destination: '#f43f5e',
  depot: '#3b82f6',
  waypoint: '#a78bfa',
  route: '#00c9a7',
}

function markerElement(label, type = 'pickup') {
  const el = document.createElement('div')
  const inner = document.createElement('div')
  inner.className = 'sr-pin sr-drop'
  
  const isDepot = type === 'depot'
  const isDest = type === 'destination'
  const isHome = type === 'rider_home'
  const isVirtual = type === 'virtual_stop' || type === 'waypoint'

  const bg = isDest ? '#f43f5e' : isDepot ? '#3b82f6' : isHome ? '#f59e0b' : isVirtual ? '#a78bfa' : '#00c9a7'
  const borderRadius = isDest || isDepot || isHome ? '50%' : '50% 50% 50% 0'

  inner.style.cssText = `
    width: 32px;
    height: 32px;
    border-radius: ${borderRadius};
    background: ${bg};
    border: 2.5px solid #ffffff;
    box-shadow: 0 4px 12px rgba(0,0,0,0.4);
    display: flex;
    align-items: center;
    justify-content: center;
    color: #ffffff;
    font-size: 11px;
    font-weight: 800;
    font-family: sans-serif;
  `
  const span = document.createElement('span')
  span.textContent = label
  if (borderRadius.includes('0')) span.style.transform = 'rotate(45deg)'
  inner.appendChild(span)
  el.appendChild(inner)
  return el
}

function vehicleMarkerElement() {
  const el = document.createElement('div')
  // MapLibre owns the root marker transform. Applying the CSS drop animation
  // here would overwrite that transform and make the vehicle appear stuck or
  // disappear while setLngLat moves it.
  el.className = 'sr-vehicle-root'
  el.style.cssText = `position:relative;width:44px;height:44px;display:flex;align-items:center;justify-content:center;`

  // Headlight beam projecting in travel direction (top)
  const beam = document.createElement('div')
  beam.className = 'sr-vehicle-headlight'
  beam.style.cssText = `
    position: absolute;
    top: -20px;
    left: 50%;
    transform: translateX(-50%);
    width: 28px;
    height: 24px;
    background: radial-gradient(ellipse at bottom, rgba(255,240,150,0.6) 0%, rgba(255,240,150,0) 80%);
    clip-path: polygon(25% 100%, 75% 100%, 100% 0%, 0% 0%);
    pointer-events: none;
  `

  // Glowing pulse aura for active status
  const aura = document.createElement('div')
  aura.className = 'sr-vehicle-aura'
  aura.style.cssText = `
    position: absolute;
    inset: 4px;
    border-radius: 50%;
    background: var(--pin-color, #00c9a7);
    opacity: 0.35;
    animation: sr-pulse 2s cubic-bezier(0, .4, .3, 1) infinite;
    pointer-events: none;
  `

  // Vehicle circular body with directional heading arrow
  const inner = document.createElement('div')
  inner.className = 'sr-vehicle-body sr-drop'
  inner.style.cssText = `
    position: relative;
    width: 32px;
    height: 32px;
    border-radius: 50%;
    background: #0f172a;
    border: 2px solid var(--pin-color, #00c9a7);
    box-shadow: 0 4px 14px rgba(0,0,0,0.5), 0 0 8px var(--pin-color, #00c9a7);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 15px;
    z-index: 2;
  `
  inner.textContent = '🚗'

  // Direction pointer arrow at the front (top)
  const pointer = document.createElement('div')
  pointer.style.cssText = `
    position: absolute;
    top: -6px;
    left: 50%;
    transform: translateX(-50%);
    width: 0;
    height: 0;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-bottom: 7px solid var(--pin-color, #00c9a7);
  `
  inner.appendChild(pointer)

  el.appendChild(beam)
  el.appendChild(aura)
  el.appendChild(inner)
  return el
}

function pulseElement(color) {
  const el = document.createElement('div')
  el.style.cssText = 'position:relative;width:1px;height:1px;'
  for (let i = 0; i < 3; i += 1) {
    const ring = document.createElement('div')
    ring.className = `sr-pulse-ring sr-pulse-${i}`
    ring.style.setProperty('--pulse-color', color)
    el.appendChild(ring)
  }
  return el
}

function bearingBetween(from, to) {
  const toRad = d => (d * Math.PI) / 180
  const toDeg = r => (r * 180) / Math.PI
  const [lng1, lat1] = from
  const [lng2, lat2] = to
  const y = Math.sin(toRad(lng2 - lng1)) * Math.cos(toRad(lat2))
  const x = Math.cos(toRad(lat1)) * Math.sin(toRad(lat2)) - Math.sin(toRad(lat1)) * Math.cos(toRad(lng2 - lng1))
  return (toDeg(Math.atan2(y, x)) + 360) % 360
}

function popup(map, lngLat, html) {
  new maplibregl.Popup({ offset: 20, closeButton: true }).setLngLat(lngLat).setHTML(html).addTo(map)
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, character => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', "'":'&#39;', '"':'&quot;' }[character]))
}

function vehicleColor(status) {
  return status === 'active' || status === 'en_route' ? '#00c9a7' : status === 'idle' ? '#60a5fa' : '#f43f5e'
}

function cleanupMap(map, animationRef, routeAnimationRef, markersRef) {
  animationRef.current.forEach(frame => cancelAnimationFrame(frame))
  if (routeAnimationRef.current) cancelAnimationFrame(routeAnimationRef.current)
  if (map?.__smartRouteDraw?.frameId) cancelAnimationFrame(map.__smartRouteDraw.frameId)
  markersRef.current.forEach(marker => marker.remove())
  markersRef.current.clear()
  map?.__smartRouteMarkers?.forEach(marker => marker.remove())
  map?.__smartRoutePulse?.remove()
  map?.remove()
}

export default function AppMap({
  center = [12.9784, 77.6408],
  zoom = 13,
  height = '100%',
  vehicles = [],
  pickup,
  destination,
  routeGeometry = [],
  waypoints = [],
  walkingPaths = [],
  heatCells = [],
  onMapClick,
  style,
  vehicleAnimation = null,
  vehicleMotion = 'smooth',
  vehicleRenderMode = 'marker',
  mapLayerMarkers = false,
  pickupPulse = false,
  followCamera = false,
}) {
  const { getToken } = useAuth()
  const [mapError, setMapError] = useState('')
  const containerRef = useRef(null)
  const mapRef = useRef(null)
  const markersRef = useRef(new Map())
  const animationRef = useRef(new Map())
  const routeAnimationRef = useRef(null)
  const initialCenter = useRef(center)
  const initialZoom = useRef(zoom)
  const onMapClickRef = useRef(onMapClick)
  const fittedRouteRef = useRef(null)

  useEffect(() => { onMapClickRef.current = onMapClick }, [onMapClick])

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return undefined
    let cancelled = false
    let map = null
    let resizeObserver = null

    const initialize = async () => {
      let token
      try {
        token = await getToken()
      } catch {
        if (!cancelled) setMapError('Authentication token unavailable.')
        return
      }
      if (cancelled) return
      if (!token) {
        setMapError('Authentication token unavailable.')
        return
      }

      map = new maplibregl.Map({
        container: containerRef.current,
        style: STADIA_STYLE_URL,
        center: [initialCenter.current[1], initialCenter.current[0]],
        zoom: initialZoom.current,
        attributionControl: true,
        transformRequest: (url) => {
          const requestUrl = backendMapUrl(url)
          if (requestUrl.includes('/maps/stadia/')) {
            return { url: requestUrl, headers: { Authorization: `Bearer ${token}` } }
          }
          return { url: requestUrl }
        },
      })

      resizeObserver = new ResizeObserver(() => map?.resize())
      resizeObserver.observe(containerRef.current)
      requestAnimationFrame(() => map?.resize())

      map.on('error', (e) => {
        if (!map.isStyleLoaded()) {
          setMapError('Stadia map resources could not be loaded. Check the backend proxy and Stadia API key.')
        }
        console.warn('MapLibre event:', e?.error || e)
      })

      map.addControl(new maplibregl.NavigationControl({ showCompass: true }), 'top-right')
      map.on('click', event => onMapClickRef.current?.(event.lngLat.lat, event.lngLat.lng))

      map.on('load', () => {
        setMapError('')
        applyDarkMapTheme(map)
        
        // Add neon glowing route layers
        map.addSource('route', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
        map.addLayer({
          id: 'route-line-casing',
          type: 'line',
          source: 'route',
          paint: {
            'line-color': '#00c9a7',
            'line-width': 8,
            'line-opacity': 0.35,
            'line-blur': 3,
          },
        })
        map.addLayer({
          id: 'route-line',
          type: 'line',
          source: 'route',
          paint: {
            'line-color': '#00c9a7',
            'line-width': 4.5,
            'line-opacity': 0.95,
          },
        })

        // Dashed walking legs show how a rider reaches their assigned
        // virtual stop instead of implying a door-to-door pickup.
        map.addSource('walking', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
        map.addLayer({
          id: 'walking-lines',
          type: 'line',
          source: 'walking',
          paint: {
            'line-color': '#f59e0b',
            'line-width': 3,
            'line-opacity': 0.9,
            'line-dasharray': [1.5, 1.5],
          },
        })

        // WebGL-backed point layers stay on the map while React telemetry is
        // updating. This is more reliable than repeatedly mounting HTML
        // markers during a live route simulation.
        map.addSource('stops', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
        map.addLayer({
          id: 'stop-halos', type: 'circle', source: 'stops',
          paint: { 'circle-radius': 22, 'circle-color': ['get', 'color'], 'circle-opacity': .18, 'circle-blur': .35 },
        })
        map.addLayer({
          id: 'stop-points', type: 'circle', source: 'stops',
          paint: { 'circle-radius': 15, 'circle-color': ['get', 'color'], 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 2.5 },
        })
        map.addLayer({
          id: 'stop-labels', type: 'symbol', source: 'stops',
          layout: { 'text-field': ['get', 'markerLabel'], 'text-size': 11, 'text-allow-overlap': true },
          paint: { 'text-color': '#ffffff', 'text-halo-color': '#0f172a', 'text-halo-width': 1 },
        })

        map.addSource('vehicles', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
        map.addLayer({
          id: 'vehicle-halos', type: 'circle', source: 'vehicles',
          paint: { 'circle-radius': 28, 'circle-color': ['get', 'color'], 'circle-opacity': .2, 'circle-blur': .45 },
        })
        map.addLayer({
          id: 'vehicle-points', type: 'circle', source: 'vehicles',
          paint: { 'circle-radius': 18, 'circle-color': '#0f172a', 'circle-stroke-color': ['get', 'color'], 'circle-stroke-width': 3 },
        })
        map.addLayer({
          id: 'vehicle-labels', type: 'symbol', source: 'vehicles',
          layout: { 'text-field': '🚗', 'text-size': 15, 'text-allow-overlap': true },
          paint: { 'text-color': '#ffffff' },
        })

        // Heatmap demand cells
        map.addSource('heat', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
        map.addLayer({
          id: 'heat-circles',
          type: 'circle',
          source: 'heat',
          paint: {
            'circle-color': ['interpolate', ['linear'], ['get', 'intensity'], 0, '#60a5fa', .5, '#f59e0e', 1, '#f43f5e'],
            'circle-radius': 20,
            'circle-opacity': .55,
          },
        })

        updateOverlays(map, { routeGeometry, waypoints, walkingPaths, heatCells, pickup, destination, pickupPulse, mapLayerMarkers })
        syncMarkers(map, vehicles, markersRef, animationRef, vehicleAnimation, vehicleMotion, vehicleRenderMode)
        animateVehicleAlongPath(map, vehicleAnimation, markersRef, routeAnimationRef, followCamera)
      })

      mapRef.current = map
    }

    void initialize()
    return () => {
      cancelled = true
      resizeObserver?.disconnect()
      cleanupMap(map, animationRef, routeAnimationRef, markersRef)
      mapRef.current = null
    }
  }, [getToken])

  const [centerLat, centerLng] = center
  useEffect(() => {
    const map = mapRef.current
    if (map && !followCamera) map.easeTo({ center: [centerLng, centerLat], duration: 500 })
  }, [centerLat, centerLng, followCamera])

  useEffect(() => {
    const map = mapRef.current
    // A map may keep loading tiles even after its sources are ready. Check
    // the source itself, otherwise live simulation updates can be skipped and
    // leave the vehicle at its initial coordinate.
    if (map?.getSource('route')) {
      updateOverlays(map, { routeGeometry, waypoints, walkingPaths, heatCells, pickup, destination, pickupPulse, mapLayerMarkers })
    }
  }, [routeGeometry, waypoints, walkingPaths, heatCells, pickup, destination, pickupPulse, mapLayerMarkers])

  useEffect(() => {
    const map = mapRef.current
    if (!map?.getSource('vehicles')) return
    syncMarkers(map, vehicles, markersRef, animationRef, vehicleAnimation, vehicleMotion, vehicleRenderMode)
    if (vehicleMotion === 'direct' && followCamera) {
      const leader = vehicles.find(vehicle => vehicle.lat != null && vehicle.lng != null)
      if (leader) map.jumpTo({ center: [leader.lng, leader.lat] })
    }
    animateVehicleAlongPath(map, vehicleAnimation, markersRef, routeAnimationRef, followCamera)
  }, [vehicles, vehicleAnimation, vehicleMotion, vehicleRenderMode, followCamera])

  // Fit bounds when route appears
  useEffect(() => {
    const map = mapRef.current
    if (!map?.isStyleLoaded() || routeGeometry.length < 2 || followCamera) return
    const routeKey = `${routeGeometry.length}:${routeGeometry[0].join(',')}:${routeGeometry[routeGeometry.length - 1].join(',')}`
    if (fittedRouteRef.current === routeKey) return
    fittedRouteRef.current = routeKey
    const bounds = routeGeometry.reduce((b, coord) => b.extend(coord), new maplibregl.LngLatBounds(routeGeometry[0], routeGeometry[0]))
    map.fitBounds(bounds, { padding: 80, duration: 1000, maxZoom: 16 })
  }, [routeGeometry, followCamera])

  const cssHeight = typeof height === 'number' ? `${height}px` : height
  return (
    <div ref={containerRef} style={{ width: '100%', height: cssHeight, position: 'relative', borderRadius: 12, overflow: 'hidden', ...style }}>
      <style>{`
        .sr-drop { animation: sr-drop-in .45s cubic-bezier(.34,1.56,.64,1) both; }
        @keyframes sr-drop-in { 0% { transform: scale(0) translateY(-10px); opacity: 0 } 60% { transform: scale(1.15) translateY(0); opacity: 1 } 100% { transform: scale(1) } }
        .sr-pulse-ring { position:absolute; left:-18px; top:-18px; width:36px; height:36px; border-radius:50%; background:var(--pulse-color,#00c9a7); opacity:.55; animation: sr-pulse 2s cubic-bezier(0,.4,.3,1) infinite; pointer-events:none; }
        .sr-pulse-1 { animation-delay:.66s }
        .sr-pulse-2 { animation-delay:1.3s }
        @keyframes sr-pulse { from { transform:scale(.4); opacity:.55 } to { transform:scale(2.8); opacity:0 } }
        @keyframes pulse-glow { 0%, 100% { box-shadow: 0 0 15px rgba(0,201,167,0.4) } 50% { box-shadow: 0 0 25px rgba(0,201,167,0.7) } }
      `}</style>
      {mapError && (
        <div style={{ position:'absolute', inset:0, display:'flex', alignItems:'center', justifyContent:'center', padding:24, background:'rgba(37,42,40,.96)', color:'#d7d4c8', textAlign:'center', zIndex:2, pointerEvents:'none' }}>
          <span style={{ maxWidth:320, fontSize:12, lineHeight:1.5 }}>{mapError}</span>
        </div>
      )}
    </div>
  )
}

function updateOverlays(map, { routeGeometry, waypoints, walkingPaths, heatCells, pickup, destination, pickupPulse, mapLayerMarkers = false }) {
  const routeSource = map.getSource('route')
  if (routeSource) {
    const coords = routeGeometry.length > 1 ? routeGeometry : []
    drawRoute(map, routeSource, coords)
  }

  const walkingSource = map.getSource('walking')
  if (walkingSource) {
    walkingSource.setData({
      type: 'FeatureCollection',
      features: walkingPaths.filter(path => path?.geometry?.length > 1).map(path => ({
        type: 'Feature',
        properties: { label: path.label || '' },
        geometry: { type: 'LineString', coordinates: path.geometry },
      })),
    })
  }

  const heatSource = map.getSource('heat')
  if (heatSource) {
    const max = Math.max(1, ...heatCells.map(c => c.predicted_demand || c.historical_request_count || 0))
    heatSource.setData({
      type: 'FeatureCollection',
      features: heatCells.filter(c => c.latitude != null && c.longitude != null).map(c => ({
        type: 'Feature',
        properties: {
          h3: c.h3_index,
          historic: c.historical_request_count,
          predicted: c.predicted_demand?.toFixed?.(1),
          intensity: (c.predicted_demand || c.historical_request_count || 0) / max,
        },
        geometry: { type: 'Point', coordinates: [c.longitude, c.latitude] },
      })),
    })
  }

  map.__smartRouteMarkers?.forEach(marker => marker.remove())
  const next = []

  const add = (point, color, label, title, type = 'pickup', rotation = -45) => {
    if (point?.lat == null || point?.lng == null) return
    const element = markerElement(label, type)
    element.style.setProperty('--pin-color', color)
    const marker = new maplibregl.Marker({ element, anchor: 'bottom', rotation }).setLngLat([point.lng, point.lat]).addTo(map)
    const labelText = point.label || `${point.lat.toFixed(4)}, ${point.lng.toFixed(4)}`
    marker.getElement().addEventListener('click', () => popup(map, [point.lng, point.lat], `<b>${escapeHtml(title)}</b><br/>${escapeHtml(labelText)}`))
    next.push(marker)
  }

  const stopFeatures = []
  const addStopFeature = (point, color, markerLabel) => {
    if (point?.lat == null || point?.lng == null) return
    stopFeatures.push({ type: 'Feature', properties: { color, markerLabel }, geometry: { type: 'Point', coordinates: [point.lng, point.lat] } })
  }

  // Draw rich waypoints
  waypoints.forEach((wp, i) => {
    const isDepot = wp.waypoint_type === 'depot'
    const isPickup = wp.waypoint_type === 'pickup'
    const isHome = wp.waypoint_type === 'rider_home'
    const label = wp.marker_label || (isDepot ? '🏢' : isPickup ? `🚏 ${i}` : isHome ? '🏠' : '•')
    const col = isDepot ? colours.depot : isHome ? '#f59e0b' : colours.waypoint
    if (mapLayerMarkers) addStopFeature(wp, col, label)
    else add(wp, col, label, isDepot ? 'Depot Hub' : `Stop ${i}`, wp.waypoint_type)
  })

  if (pickup) {
    if (mapLayerMarkers) addStopFeature(pickup, colours.pickup, '▲')
    else add(pickup, colours.pickup, '▲', 'Pickup Stop', 'pickup')
  }
  if (destination) {
    if (mapLayerMarkers) addStopFeature(destination, colours.destination, '★')
    else add(destination, colours.destination, '★', 'Destination', 'destination', 0)
  }

  const stopsSource = map.getSource('stops')
  if (stopsSource) stopsSource.setData({ type: 'FeatureCollection', features: mapLayerMarkers ? stopFeatures : [] })

  map.__smartRouteMarkers = next

  // Pulse radar ring for rider search
  map.__smartRoutePulse?.remove()
  map.__smartRoutePulse = null
  if (pickupPulse && pickup?.lat != null && pickup?.lng != null) {
    map.__smartRoutePulse = new maplibregl.Marker({ element: pulseElement(colours.pickup), anchor: 'center' })
      .setLngLat([pickup.lng, pickup.lat]).addTo(map)
  }
}

function lineFeatureData(coords) {
  return {
    type: 'FeatureCollection',
    features: coords.length > 1 ? [{ type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: coords } }] : [],
  }
}

function drawRoute(map, routeSource, coords) {
  if (map.__smartRouteDraw?.frameId) cancelAnimationFrame(map.__smartRouteDraw.frameId)
  if (coords.length < 2) {
    routeSource.setData(lineFeatureData([]))
    map.__smartRouteDraw = null
    return
  }

  const routeKey = `${coords.length}:${coords[0].join(',')}:${coords[coords.length - 1].join(',')}`
  if (map.__smartRouteDraw?.key === routeKey) {
    routeSource.setData(lineFeatureData(coords))
    return
  }

  const cumulative = [0]
  for (let i = 1; i < coords.length; i += 1) {
    const [lng1, lat1] = coords[i - 1]
    const [lng2, lat2] = coords[i]
    cumulative.push(cumulative[i - 1] + Math.hypot(lng2 - lng1, lat2 - lat1))
  }
  const totalLength = cumulative[cumulative.length - 1] || 1

  const started = performance.now()
  const duration = Math.min(1400, Math.max(400, coords.length * 10))

  const drawFrame = now => {
    const progress = Math.min(1, (now - started) / duration)
    const eased = 1 - (1 - progress) * (1 - progress)
    const distance = totalLength * eased
    const partial = [coords[0]]
    for (let i = 1; i < coords.length; i += 1) {
      if (cumulative[i] <= distance) {
        partial.push(coords[i])
        continue
      }
      const prevDist = cumulative[i - 1]
      const segmentLength = cumulative[i] - prevDist
      const ratio = segmentLength ? (distance - prevDist) / segmentLength : 0
      const [lng1, lat1] = coords[i - 1]
      const [lng2, lat2] = coords[i]
      partial.push([lng1 + (lng2 - lng1) * ratio, lat1 + (lat2 - lat1) * ratio])
      break
    }
    routeSource.setData(lineFeatureData(partial))
    if (progress < 1) {
      map.__smartRouteDraw.frameId = requestAnimationFrame(drawFrame)
    } else {
      map.__smartRouteDraw.frameId = null
    }
  }
  map.__smartRouteDraw = { key: routeKey, frameId: requestAnimationFrame(drawFrame) }
}

function syncMarkers(map, vehicles, markersRef, animationRef, vehicleAnimation, vehicleMotion = 'smooth', vehicleRenderMode = 'marker') {
  if (vehicleRenderMode === 'geojson') {
    const source = map.getSource('vehicles')
    source?.setData({
      type: 'FeatureCollection',
      features: vehicles.filter(vehicle => vehicle.lat != null && vehicle.lng != null).map(vehicle => ({
        type: 'Feature',
        properties: { color: vehicleColor(vehicle.status), bearing: vehicle.bearing || 0 },
        geometry: { type: 'Point', coordinates: [vehicle.lng, vehicle.lat] },
      })),
    })
    return
  }
  const activeIds = new Set()
  const animatingId = vehicleAnimation?.vehicleId ? `vehicle-${vehicleAnimation.vehicleId}` : null

  vehicles.filter(v => v.lat != null && v.lng != null).forEach(vehicle => {
    const id = `vehicle-${vehicle.id}`
    activeIds.add(id)
    const target = [vehicle.lng, vehicle.lat]

    let marker = markersRef.current.get(id)
    if (!marker) {
      const element = vehicleMarkerElement()
      element.style.setProperty('--pin-color', vehicleColor(vehicle.status))
      marker = new maplibregl.Marker({ element, anchor: 'center' }).setLngLat(target).addTo(map)
      const route = vehicle.assigned_route_id ? `Route: ${escapeHtml(vehicle.assigned_route_id.slice(0, 18))}…` : ''
      marker.getElement().addEventListener('click', () => popup(map, target, `<b>${escapeHtml(vehicle.license_plate || 'Vehicle')}</b><br/>Status: ${escapeHtml(vehicle.status)}<br/>${route}`))
      markersRef.current.set(id, marker)
    }

    // Skip position overwrite if this vehicle is currently being path-animated
    if (id === animatingId) return

    const from = marker.getLngLat()
    if (vehicleMotion === 'direct') {
      if (animationRef.current.has(id)) cancelAnimationFrame(animationRef.current.get(id))
      animationRef.current.delete(id)
      marker.setLngLat(target)
      if (Math.hypot(target[0] - from.lng, target[1] - from.lat) > 1e-5) {
        marker.setRotation(bearingBetween([from.lng, from.lat], target))
      }
      return
    }

    const started = performance.now()
    const duration = 1200
    const fromArr = [from.lng, from.lat]
    if (Math.hypot(target[0] - fromArr[0], target[1] - fromArr[1]) > 1e-5) {
      marker.setRotation(bearingBetween(fromArr, target))
    }

    if (animationRef.current.has(id)) cancelAnimationFrame(animationRef.current.get(id))

    const animate = now => {
      const progress = Math.min(1, (now - started) / duration)
      const eased = progress * progress * (3 - 2 * progress)
      marker.setLngLat([from.lng + (target[0] - from.lng) * eased, from.lat + (target[1] - from.lat) * eased])
      if (progress < 1) animationRef.current.set(id, requestAnimationFrame(animate))
      else animationRef.current.delete(id)
    }
    animationRef.current.set(id, requestAnimationFrame(animate))
  })

  markersRef.current.forEach((marker, id) => {
    if (!activeIds.has(id) && id !== animatingId) {
      marker.remove()
      markersRef.current.delete(id)
    }
  })
}

function animateVehicleAlongPath(map, animation, markersRef, animationRef, followCamera = false) {
  if (animation?.key && animation.key === animationRef.animationKey) return
  if (animationRef.current) cancelAnimationFrame(animationRef.current)
  animationRef.animationKey = animation?.key || null
  if (!animation?.path?.length || !animation.vehicleId) return

  const markerId = `vehicle-${animation.vehicleId}`
  let marker = markersRef.current.get(markerId)
  if (!marker) {
    const element = vehicleMarkerElement()
    element.style.setProperty('--pin-color', '#00c9a7')
    marker = new maplibregl.Marker({ element, anchor: 'center' }).setLngLat(animation.path[0]).addTo(map)
    markersRef.current.set(markerId, marker)
  }

  const path = animation.path.filter(point => Array.isArray(point) && point.length >= 2)
  if (path.length < 2) return

  const started = performance.now()
  const startProgress = Math.max(0, Math.min(1, animation.startProgress || 0))
  const duration = Math.max(3000, (animation.durationMs || 16000) * (1 - startProgress))

  const frame = now => {
    const progress = startProgress + (1 - startProgress) * Math.min(1, (now - started) / duration)
    const { position, bearing } = interpolatePath(path, progress)
    marker.setLngLat(position)
    if (bearing != null) marker.setRotation(bearing)

    if (followCamera && map) {
      // This callback runs on every animation frame. A new easeTo transition
      // per frame queues camera animations and causes visible map jitter.
      map.jumpTo({ center: position, zoom: Math.max(14, map.getZoom()) })
    }

    if (progress < 1) {
      animationRef.current = requestAnimationFrame(frame)
    } else {
      animationRef.current = null
      if (animation.loop) {
        animateVehicleAlongPath(map, { ...animation, key: `${animation.key}_${Date.now()}` }, markersRef, animationRef, followCamera)
      }
    }
  }
  animationRef.current = requestAnimationFrame(frame)
}

function interpolatePath(path, progress) {
  const segmentLengths = []
  let totalLength = 0
  for (let i = 1; i < path.length; i += 1) {
    const dx = (path[i][0] - path[i - 1][0]) * Math.cos((path[i - 1][1] * Math.PI) / 180)
    const dy = path[i][1] - path[i - 1][1]
    const length = Math.hypot(dx, dy)
    segmentLengths.push(length)
    totalLength += length
  }
  if (!totalLength) return { position: path[0], bearing: null }

  let distance = totalLength * progress
  for (let i = 0; i < segmentLengths.length; i += 1) {
    const segmentLength = segmentLengths[i]
    if (distance <= segmentLength) {
      const ratio = segmentLength ? distance / segmentLength : 0
      const position = [
        path[i][0] + (path[i + 1][0] - path[i][0]) * ratio,
        path[i][1] + (path[i + 1][1] - path[i][1]) * ratio,
      ]
      const bearing = segmentLength > 1e-7 ? bearingBetween(path[i], path[i + 1]) : null
      return { position, bearing }
    }
    distance -= segmentLength
  }
  return { position: path[path.length - 1], bearing: null }
}

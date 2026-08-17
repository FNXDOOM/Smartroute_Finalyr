/** Shared MapLibre map used by passenger, driver, and admin views. */
import { useEffect, useRef } from 'react'
import * as maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'

const MAPTILER_KEY = import.meta.env.VITE_MAPTILER_KEY
const STADIA_KEY = import.meta.env.VITE_STADIA_API_KEY
const configuredStyle = import.meta.env.VITE_MAP_STYLE_URL
const FALLBACK_STYLE = { version: 8, sources: { carto: { type: 'raster', tiles: ['https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png'], tileSize: 256, attribution: '&copy; OpenStreetMap contributors &copy; CARTO' } }, layers: [{ id: 'carto-basemap', type: 'raster', source: 'carto' }] }
function defaultStyle() { if (configuredStyle) return configuredStyle; if (STADIA_KEY) return `https://tiles.stadiamaps.com/styles/alidade_smooth.json?api_key=${encodeURIComponent(STADIA_KEY)}`; if (MAPTILER_KEY) return `https://api.maptiler.com/maps/streets-v2/style.json?key=${encodeURIComponent(MAPTILER_KEY)}`; return FALLBACK_STYLE }
const colours = { pickup: '#00c9a7', destination: '#f43f5e', depot: '#4e6080', waypoint: '#a78bfa' }
function markerElement(color, label) { const el = document.createElement('div'); el.style.cssText = `width:28px;height:28px;border-radius:50% 50% 50% 0;background:${color};border:2px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,.5);transform:rotate(-45deg);display:flex;align-items:center;justify-content:center;color:#fff;font-size:11px;font-weight:800;`; const span = document.createElement('span'); span.textContent = label; span.style.transform = 'rotate(45deg)'; el.appendChild(span); return el }
function popup(map, lngLat, html) { new maplibregl.Popup({ offset: 20, closeButton: true }).setLngLat(lngLat).setHTML(html).addTo(map) }
function escapeHtml(value) { return String(value ?? '').replace(/[&<>'"]/g, character => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', "'":'&#39;', '"':'&quot;' }[character])) }
function vehicleColor(status) { return status === 'active' || status === 'en_route' ? '#00c9a7' : status === 'idle' ? '#7a90b0' : '#f43f5e' }
function asCoordinates(points) { return points.filter(p => p?.lat != null && p?.lng != null).map(p => [p.lng, p.lat]) }

export default function AppMap({ center = [12.9784, 77.6408], zoom = 13, height = '100%', vehicles = [], pickup, destination, routeGeometry = [], waypoints = [], heatCells = [], onMapClick, style }) {
  const containerRef = useRef(null); const mapRef = useRef(null); const markersRef = useRef(new Map()); const animationRef = useRef(new Map()); const initialCenter = useRef(center)
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return undefined
    const map = new maplibregl.Map({ container: containerRef.current, style: defaultStyle(), center: [initialCenter.current[1], initialCenter.current[0]], zoom, attributionControl: true })
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    map.on('click', event => onMapClick?.(event.lngLat.lat, event.lngLat.lng))
    map.on('load', () => { map.addSource('route', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } }); map.addLayer({ id: 'route-line', type: 'line', source: 'route', paint: { 'line-color': '#00c9a7', 'line-width': 4, 'line-opacity': .88, 'line-dasharray': [2, 1] } }); map.addSource('heat', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } }); map.addLayer({ id: 'heat-circles', type: 'circle', source: 'heat', paint: { 'circle-color': ['interpolate', ['linear'], ['get', 'intensity'], 0, '#60a5fa', .5, '#f59e0b', 1, '#f43f5e'], 'circle-radius': 18, 'circle-opacity': .55 } }); map.on('click', 'heat-circles', e => { const p = e.features?.[0]?.properties || {}; popup(map, e.lngLat, `<b>${escapeHtml(p.h3 || 'Demand zone')}</b><br/>Historic: ${escapeHtml(p.historic || 0)}<br/>Predicted: ${escapeHtml(p.predicted || '—')}`) }); updateOverlays(map, { routeGeometry, waypoints, heatCells, pickup, destination }); syncMarkers(map, vehicles, markersRef, animationRef) })
    mapRef.current = map
    return () => { animationRef.current.forEach(frame => cancelAnimationFrame(frame)); markersRef.current.forEach(marker => marker.remove()); markersRef.current.clear(); map.__smartRouteMarkers?.forEach(marker => marker.remove()); map.remove(); mapRef.current = null }
  }, [])
  useEffect(() => { const map = mapRef.current; if (map) map.easeTo({ center: [center[1], center[0]], duration: 500 }) }, [center[0], center[1]])
  useEffect(() => { const map = mapRef.current; if (map?.isStyleLoaded()) updateOverlays(map, { routeGeometry, waypoints, heatCells, pickup, destination }) }, [routeGeometry, waypoints, heatCells, pickup, destination])
  useEffect(() => { if (mapRef.current?.isStyleLoaded()) syncMarkers(mapRef.current, vehicles, markersRef, animationRef) }, [vehicles])
  const cssHeight = typeof height === 'number' ? `${height}px` : height
  return <div ref={containerRef} style={{ width: '100%', height: cssHeight, position: 'relative', borderRadius: 12, overflow: 'hidden', ...style }} />
}

function updateOverlays(map, { routeGeometry, waypoints, heatCells, pickup, destination }) {
  const routeSource = map.getSource('route')
  if (routeSource) { const coords = routeGeometry.length > 1 ? routeGeometry.map(([lng, lat]) => [lng, lat]) : asCoordinates([...waypoints].sort((a, b) => (a.sequence ?? 0) - (b.sequence ?? 0))); const fallback = coords.length > 1 ? coords : pickup?.lat != null && destination?.lat != null ? [[pickup.lng, pickup.lat], [destination.lng, destination.lat]] : []; routeSource.setData({ type: 'FeatureCollection', features: fallback.length > 1 ? [{ type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: fallback } }] : [] }) }
  const heatSource = map.getSource('heat'); if (heatSource) { const max = Math.max(1, ...heatCells.map(c => c.predicted_demand || c.historical_request_count || 0)); heatSource.setData({ type: 'FeatureCollection', features: heatCells.filter(c => c.latitude != null && c.longitude != null).map(c => ({ type: 'Feature', properties: { h3: c.h3_index, historic: c.historical_request_count, predicted: c.predicted_demand?.toFixed?.(1), intensity: (c.predicted_demand || c.historical_request_count || 0) / max }, geometry: { type: 'Point', coordinates: [c.longitude, c.latitude] } })) }) }
  map.__smartRouteMarkers?.forEach(marker => marker.remove()); const next = []; const add = (point, color, label, title) => { if (point?.lat == null || point?.lng == null) return; const marker = new maplibregl.Marker({ element: markerElement(color, label), anchor: 'bottom' }).setLngLat([point.lng, point.lat]).addTo(map); const labelText = point.label || `${point.lat.toFixed(4)}, ${point.lng.toFixed(4)}`; marker.getElement().addEventListener('click', () => popup(map, [point.lng, point.lat], `<b>${escapeHtml(title)}</b><br/>${escapeHtml(labelText)}`)); next.push(marker) }; waypoints.forEach((wp, i) => add(wp, wp.waypoint_type === 'depot' ? colours.depot : colours.waypoint, wp.waypoint_type === 'depot' ? 'D' : '•', `Stop ${i + 1}`)); add(pickup, colours.pickup, '▲', 'Pickup'); add(destination, colours.destination, '★', 'Destination'); map.__smartRouteMarkers = next
}

function syncMarkers(map, vehicles, markersRef, animationRef) {
  const activeIds = new Set(); vehicles.filter(v => v.lat != null && v.lng != null).forEach(vehicle => { const id = `vehicle-${vehicle.id}`; activeIds.add(id); const target = [vehicle.lng, vehicle.lat]; let marker = markersRef.current.get(id); if (!marker) { marker = new maplibregl.Marker({ element: markerElement(vehicleColor(vehicle.status), '🚗'), anchor: 'bottom' }).setLngLat(target).addTo(map); const route = vehicle.assigned_route_id ? `Route: ${escapeHtml(vehicle.assigned_route_id.slice(0, 18))}…` : ''; marker.getElement().addEventListener('click', () => popup(map, target, `<b>${escapeHtml(vehicle.license_plate || 'Vehicle')}</b><br/>Status: ${escapeHtml(vehicle.status)}<br/>${route}`)); markersRef.current.set(id, marker) } const from = marker.getLngLat(); const started = performance.now(); const duration = 1800; if (animationRef.current.has(id)) cancelAnimationFrame(animationRef.current.get(id)); const animate = now => { const progress = Math.min(1, (now - started) / duration); const eased = progress * progress * (3 - 2 * progress); marker.setLngLat([from.lng + (target[0] - from.lng) * eased, from.lat + (target[1] - from.lat) * eased]); if (progress < 1) animationRef.current.set(id, requestAnimationFrame(animate)); else animationRef.current.delete(id) }; animationRef.current.set(id, requestAnimationFrame(animate)) }); markersRef.current.forEach((marker, id) => { if (!activeIds.has(id)) { marker.remove(); markersRef.current.delete(id) } })
}

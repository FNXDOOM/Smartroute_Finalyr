/**
 * AppMap — shared Leaflet map component used across Passenger, Driver and Admin views.
 *
 * Props
 * ─────
 * center        [lat, lng]   initial / controlled center
 * zoom          number       initial zoom (default 13)
 * height        string|number container height (default '100%')
 * vehicles      array        live fleet positions  { id, license_plate, lat, lng, status }
 * pickup        {lat,lng}    pickup marker (passenger booking)
 * destination   {lat,lng}    destination marker
 * waypoints     array        route waypoints { lat, lng, waypoint_type, sequence }
 * heatCells     array        demand cells { latitude, longitude, predicted_demand, historical_request_count }
 * onMapClick    fn(lat,lng)  fired when user clicks map (for picking coordinates)
 * style         CSSProperties extra style overrides for wrapper
 */

import { useEffect, useRef } from 'react'
import {
  MapContainer, TileLayer, Marker, Popup, Polyline,
  CircleMarker, useMapEvents, useMap,
} from 'react-leaflet'
import L from 'leaflet'

// ─── Fix default marker icons (Vite asset pipeline) ──────────────────────────
import markerIcon2x   from 'leaflet/dist/images/marker-icon-2x.png'
import markerIcon     from 'leaflet/dist/images/marker-icon.png'
import markerShadow   from 'leaflet/dist/images/marker-shadow.png'
delete (L.Icon.Default.prototype as any)._getIconUrl
L.Icon.Default.mergeOptions({ iconRetinaUrl:markerIcon2x, iconUrl:markerIcon, shadowUrl:markerShadow })

// ─── Custom coloured div-icons ────────────────────────────────────────────────
const makeIcon = (color: string, label = '') =>
  L.divIcon({
    className: '',
    html: `<div style="width:28px;height:28px;border-radius:50% 50% 50% 0;background:${color};border:2px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,0.5);transform:rotate(-45deg);display:flex;align-items:center;justify-content:center">
             <span style="transform:rotate(45deg);color:#fff;font-size:11px;font-weight:800">${label}</span>
           </div>`,
    iconSize: [28, 28],
    iconAnchor: [14, 28],
    popupAnchor: [0, -30],
  })

const ICONS = {
  pickup:      makeIcon('#00c9a7', '▲'),
  destination: makeIcon('#f43f5e', '★'),
  depot:       makeIcon('#4e6080', 'D'),
  vehicle:     (status: string) => makeIcon(
    status === 'active' || status === 'en_route' ? '#00c9a7' :
    status === 'idle'   ? '#7a90b0' : '#f43f5e', '🚗'),
  waypoint:    makeIcon('#a78bfa', '•'),
}

// ─── Helper: recenter map when center prop changes ────────────────────────────
function Recenter({ center }: { center: [number,number] }) {
  const map = useMap()
  useEffect(() => { map.setView(center, map.getZoom(), { animate:true }) }, [center[0], center[1]])
  return null
}

// ─── Click handler ────────────────────────────────────────────────────────────
function ClickHandler({ onMapClick }: { onMapClick?: (lat:number,lng:number)=>void }) {
  useMapEvents({ click(e) { onMapClick?.(e.latlng.lat, e.latlng.lng) } })
  return null
}

// ─── Status colour for heat cells ────────────────────────────────────────────
function demandColour(intensity: number) {
  const r = Math.round(244 * intensity)
  const g = Math.round(63  * (1 - intensity * 0.8))
  const b = Math.round(94  * (1 - intensity))
  return `rgb(${r},${g},${b})`
}

// ─── Main component ───────────────────────────────────────────────────────────
interface AppMapProps {
  center?:       [number,number]
  zoom?:         number
  height?:       string | number
  vehicles?:     any[]
  pickup?:       { lat:number; lng:number; label?:string } | null
  destination?:  { lat:number; lng:number; label?:string } | null
  waypoints?:    any[]
  heatCells?:    any[]
  onMapClick?:   (lat:number,lng:number) => void
  style?:        React.CSSProperties
}

export default function AppMap({
  center       = [12.9784, 77.6408],
  zoom         = 13,
  height       = '100%',
  vehicles     = [],
  pickup,
  destination,
  waypoints    = [],
  heatCells    = [],
  onMapClick,
  style,
}: AppMapProps) {

  const routePoints: [number,number][] = waypoints
    .filter(w => w.lat && w.lng)
    .sort((a,b) => (a.sequence??0) - (b.sequence??0))
    .map(w => [w.lat, w.lng])

  const maxDemand = Math.max(1, ...heatCells.map(c => c.predicted_demand || c.historical_request_count || 0))

  // Normalise height to a CSS string
  const cssHeight = typeof height === 'number' ? `${height}px` : height

  return (
    <div style={{ width:'100%', height: cssHeight, position:'relative', borderRadius:12, overflow:'hidden', ...style }}>
      <MapContainer
        center={center}
        zoom={zoom}
        style={{ position:'absolute', inset:0, width:'100%', height:'100%' }}
        scrollWheelZoom
      >
        <TileLayer
          attribution='&copy; <a href="https://osm.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <Recenter center={center} />
        {onMapClick && <ClickHandler onMapClick={onMapClick} />}

        {/* ── Demand heat cells ── */}
        {heatCells.map((c,i) => {
          const intensity = (c.predicted_demand || c.historical_request_count || 0) / maxDemand
          return (
            <CircleMarker
              key={`heat-${i}`}
              center={[c.latitude, c.longitude]}
              radius={18}
              pathOptions={{ color:'transparent', fillColor:demandColour(intensity), fillOpacity: Math.max(0.2, intensity * 0.85) }}
            >
              <Popup>
                <b>{c.h3_index}</b><br/>
                Historic: {c.historical_request_count}<br/>
                Predicted: {c.predicted_demand?.toFixed(1) ?? '—'}
              </Popup>
            </CircleMarker>
          )
        })}

        {/* ── Route polyline ── */}
        {routePoints.length > 1 && (
          <Polyline
            positions={routePoints}
            pathOptions={{ color:'#00c9a7', weight:4, opacity:0.85, dashArray:'8 4' }}
          />
        )}

        {/* ── Waypoint markers ── */}
        {waypoints.map((wp,i) => (
          <Marker
            key={`wp-${i}`}
            position={[wp.lat, wp.lng]}
            icon={wp.waypoint_type === 'depot' ? ICONS.depot : ICONS.waypoint}
          >
            <Popup>
              <b>Stop {i+1}</b><br/>
              Type: {wp.waypoint_type}<br/>
              {wp.passenger_ids?.length > 0 && `Passengers: ${wp.passenger_ids.length}`}
            </Popup>
          </Marker>
        ))}

        {/* ── Vehicle markers ── */}
        {vehicles.filter(v => v.lat && v.lng).map(v => (
          <Marker
            key={`v-${v.id}`}
            position={[v.lat, v.lng]}
            icon={ICONS.vehicle(v.status)}
          >
            <Popup>
              <b>{v.license_plate}</b><br/>
              Status: {v.status}<br/>
              {v.assigned_route_id && `Route: ${v.assigned_route_id.slice(0,18)}…`}
            </Popup>
          </Marker>
        ))}

        {/* ── Pickup marker ── */}
        {pickup?.lat && (
          <Marker position={[pickup.lat, pickup.lng]} icon={ICONS.pickup}>
            <Popup><b>Pickup</b><br/>{pickup.label || `${pickup.lat.toFixed(4)}, ${pickup.lng.toFixed(4)}`}</Popup>
          </Marker>
        )}

        {/* ── Destination marker ── */}
        {destination?.lat && (
          <Marker position={[destination.lat, destination.lng]} icon={ICONS.destination}>
            <Popup><b>Destination</b><br/>{destination.label || `${destination.lat.toFixed(4)}, ${destination.lng.toFixed(4)}`}</Popup>
          </Marker>
        )}

        {/* ── Direct line pickup → destination ── */}
        {pickup?.lat && destination?.lat && routePoints.length === 0 && (
          <Polyline
            positions={[[pickup.lat, pickup.lng],[destination.lat, destination.lng]]}
            pathOptions={{ color:'#60a5fa', weight:2, opacity:0.6, dashArray:'6 4' }}
          />
        )}
      </MapContainer>
    </div>
  )
}

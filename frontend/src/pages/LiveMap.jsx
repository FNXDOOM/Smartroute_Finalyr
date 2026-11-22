import { useCallback, useEffect, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { Map, NavigationControl, setWorkerUrl } from 'maplibre-gl'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import 'maplibre-gl/dist/maplibre-gl.css'
import { installVehicleLayer } from '../map/VehicleLayer.jsx'
import { installRouteTrail } from '../map/RouteTrail.jsx'
import useRideSimulation, { CITY } from '../map/useRideSimulation.js'
import './live-map.css'

setWorkerUrl(workerUrl)

export default function LiveMap() {
  const container = useRef(null)
  const mapRef = useRef(null)
  const layers = useRef(null)
  const nextFollow = useRef(0)
  const [mapError, setMapError] = useState('')
  const [live, setLive] = useState(false)
  const [speed, setSpeed] = useState(1)
  const [selected, setSelected] = useState(1)
  const [follow, setFollow] = useState(false)
  const [hideTravelled, setHideTravelled] = useState(false)
  const [all, setAll] = useState(false)
  const [count, setCount] = useState(12)
  const draw = useCallback((fleet) => {
    if (!layers.current) return
    layers.current.vehicles.draw(fleet)
    layers.current.trails.draw(fleet, { hideTravelled, selected, all })
    const position = fleet.get(selected)?.animator?.sample?.position
    const now = performance.now()
    if (follow && position && now >= nextFollow.current) {
      nextFollow.current = now + 450
      mapRef.current.easeTo({ center: position, duration: 450, easing: (t) => t })
    }
  }, [hideTravelled, selected, follow, all])
  const { vehicles, connection } = useRideSimulation({ count, live, multiplier: speed, draw })

  useEffect(() => {
    let map
    try {
      map = new Map({ container: container.current, center: CITY, zoom: 12,
        style: 'https://tiles.openfreemap.org/styles/positron' })
    } catch {
      const timer = setTimeout(() => setMapError('Could not start the map. Check that WebGL is enabled.'), 0)
      return () => clearTimeout(timer)
    }
    mapRef.current = map
    map.addControl(new NavigationControl(), 'top-right')
    const controller = new AbortController()
    const onError = () => {
      if (!map.isStyleLoaded()) setMapError('Could not load map tiles. Check your internet connection.')
    }
    map.on('error', onError)
    map.once('load', async () => {
      try {
        const trails = installRouteTrail(map)
        const fleet = await installVehicleLayer(map, controller.signal)
        if (fleet) {
          layers.current = { trails, vehicles: fleet }
          setMapError('')
        }
      } catch {
        if (!controller.signal.aborted) setMapError('Could not load the fleet layer.')
      }
    })
    return () => {
      controller.abort()
      layers.current?.vehicles.destroy()
      layers.current?.trails.destroy()
      layers.current = null
      mapRef.current = null
      map.remove()
    }
  }, [])

  return (
    <main className="fleet-demo">
      <section className="fleet-map" aria-label="Bengaluru fleet map">
        <div ref={container} className="fleet-canvas" />
        {mapError && <p className="fleet-error" role="alert">{mapError}</p>}
        <div className="fleet-legend">
          <span>🔵 To pickup</span><span>⚫ To drop-off</span><span>⚪ Travelled</span>
        </div>
      </section>
      <aside className="fleet-sidebar">
        <header><p>SmartRoute / Bengaluru</p><h1>Fleet map</h1></header>
        <fieldset>
          <legend>Map controls</legend>
          <label><input type="checkbox" checked={live} onChange={(e) => setLive(e.target.checked)} /> Live mode</label>
          <label><input type="checkbox" checked={follow} onChange={(e) => { if (!e.target.checked) mapRef.current?.stop(); setFollow(e.target.checked) }} /> Follow selected vehicle</label>
          <label><input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} /> Show all trails</label>
          <label><input type="checkbox" checked={hideTravelled} onChange={(e) => setHideTravelled(e.target.checked)} /> Hide travelled paths</label>
          <label>Speed: {speed}× <input type="range" min="0" max="2" value={[1, 2, 5].indexOf(speed)}
            disabled={live} onChange={(e) => setSpeed([1, 2, 5][Number(e.target.value)])} /></label>
          <label>Fleet size <select value={count} disabled={live} onChange={(e) => setCount(Number(e.target.value))}>
            <option>12</option><option>25</option><option>50</option>
          </select></label>
        </fieldset>
        {live && <p role="status">{connection}</p>}
        <ul className="fleet-list" aria-label="Vehicles">
          {vehicles.map(({ id, type, status, eta, remaining }) => (
            <li key={id}><button type="button" aria-pressed={selected === id} onClick={() => setSelected(id)}>
              <strong>#{id} · {type}</strong>
              <span>{status === 'IDLE' ? 'Getting route' : status.replaceAll('_', ' ').toLowerCase()}
                {eta != null && ` · ${Math.ceil(eta / 60)} min · ${(remaining / 1000).toFixed(1)} km`}</span>
            </button></li>
          ))}
        </ul>
      </aside>
    </main>
  )
}

createRoot(document.getElementById('root')).render(<LiveMap />)

// MapLibre is the largest thing this app ships (~247 KiB gzipped). Importing it
// directly puts it in the executing chunk's import graph, so a view cannot run
// any of its code until the renderer has downloaded — even on screens that never
// draw a map. This boundary keeps MapLibre out of every view bundle and lets a
// map arrive after the surrounding chrome has already painted.
import { Suspense, lazy } from 'react'

const MapLibreMap = lazy(() => import('./AppMap'))

function MapFallback({ height }) {
  return (
    <div
      aria-busy="true"
      className="w-full animate-pulse bg-muted"
      style={{ height: typeof height === 'number' ? `${height}px` : height || '100%' }}
    />
  )
}

export default function AppMap(props) {
  return (
    <Suspense fallback={<MapFallback height={props.height} />}>
      <MapLibreMap {...props} />
    </Suspense>
  )
}

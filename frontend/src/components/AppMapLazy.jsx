// Keeps MapLibre (~247 KiB gzipped) out of every view bundle, with the Suspense boundary here so a map-chunk fetch only swaps the map, not the whole screen.
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

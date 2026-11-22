import { haversine, lerpAngle } from './routeUtils.js'

export const STALE_MS = 20_000

export function acceptFix(previous, point, now, timestamp) {
  if (previous && Number.isFinite(timestamp) && timestamp <= (previous.timestamp ?? -Infinity)) return null
  if (previous && (now - previous.now) < STALE_MS && haversine(previous.point, point) > 200) return null
  return { point, now, timestamp }
}

export function routeProgress(route, point, previous = null) {
  const fix = route.project(point, previous ?? 0)
  if (fix.offset > 65 || (previous != null && (fix.distance < previous - 8 || fix.distance > previous + 200))) return null
  return Math.max(previous ?? 0, fix.distance)
}

export function smoothHeading(from, to, dt) {
  return lerpAngle(from, to, 1 - 0.85 ** (dt * 60))
}

export function trailFeatures(route, distance, color) {
  const { position, segmentIndex } = route.pointAtDistance(distance)
  const line = (coordinates, tint) => ({
    type: 'Feature', properties: { tint }, geometry: { type: 'LineString', coordinates },
  })
  return {
    type: 'FeatureCollection',
    features: [
      ...(distance > 0 ? [line([...route.coords.slice(0, segmentIndex + 1), position], '#a1a1aa')] : []),
      ...(distance < route.length ? [line([position, ...route.coords.slice(segmentIndex + 1)], color)] : []),
    ],
  }
}

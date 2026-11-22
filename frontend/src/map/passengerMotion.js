import { buildRoute, haversine, lerpAngle } from './routeUtils.js'

export const STALE_MS = 20_000

export function acceptFix(previous, point, now, timestamp) {
  if (previous && Number.isFinite(timestamp) && timestamp <= (previous.timestamp ?? -Infinity)) return null
  if (previous && (now - previous.now) < STALE_MS && haversine(previous.point, point) > 200) return null
  return { point, now, timestamp }
}

export function routeProgress(route, point, previous = null) {
  const fix = route.project(point, previous ?? 0)
  if (fix.offset > 65) return null
  if (previous != null && (fix.distance < previous || fix.distance > previous + 200)) {
    const ahead = route.project(point, previous, previous, previous + 200)
    // At overlapping roads, prefer the nearly identical projection in the forward window.
    if (ahead.offset <= Math.min(65, fix.offset + 3)) return ahead.distance
    if (fix.distance < previous - 8 || fix.distance > previous + 200) return null
  }
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

export function lineFeatureData(coords) {
  return {
    type: 'FeatureCollection',
    features: coords.length > 1 ? [{ type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: coords } }] : [],
  }
}

export function animatePassengerFix(map, marker, vehicle, target, id, frames) {
  const coords = map.__trackingRoute
  const now = performance.now()
  const previous = marker.trackingMotion
  const key = vehicle.trackingKey
  const color = vehicle.trackingLeg === 'drop' ? '#18181b' : '#2563eb'
  const changed = !previous || previous.coords !== coords || previous.key !== key
  const source = () => map.getSource('route')
  if (!changed && previous.fix.point[0] === target[0] && previous.fix.point[1] === target[1]) {
    if (vehicle.fixTimestamp > (previous.fix.timestamp ?? -Infinity)) {
      previous.fix.timestamp = vehicle.fixTimestamp
      previous.fix.now = now
    }
    if (previous.distance != null) source()?.setData(trailFeatures(previous.route, previous.distance, color))
    return
  }
  const fix = acceptFix(changed ? null : previous.fix, target, now, vehicle.fixTimestamp)
  if (!fix) return
  const route = changed ? buildRoute(vehicle.trackingSnap ? coords || [] : []) : previous.route
  const resumedFarAway = !changed && now - previous.fix.now >= STALE_MS && haversine(previous.fix.point, target) > 200
  const reanchor = changed || document.hidden || resumedFarAway
  const projected = route.coords.length > 1 ? routeProgress(route, target, reanchor ? null : previous.goal) : null
  if (!reanchor && previous.goal != null && projected == null
    && route.project(target, previous.goal).offset <= 65) return
  if (frames.has(id)) cancelAnimationFrame(frames.get(id))
  frames.delete(id)
  const initial = reanchor ? projected : previous.distance
  const state = { coords, key, route, fix, goal: projected, distance: initial }
  marker.trackingMotion = state
  const duration = reanchor || matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 1000
  const direct = projected == null || initial == null
    ? buildRoute([marker.getLngLat().toArray(), projected == null ? target : route.pointAtDistance(projected).position]) : null
  let heading = marker.getRotation()
  let last = now
  function frame(time) {
    const t = duration && !document.hidden ? Math.max(0, Math.min(1, (time - now) / duration)) : 1
    const eased = t * t * (3 - 2 * t)
    const distance = direct ? null : initial + (projected - initial) * eased
    const sample = direct ? direct.pointAtDistance(direct.length * eased) : route.pointAtDistance(distance)
    marker.setLngLat(sample.position)
    if (!direct || direct.length > 0) {
      heading = duration ? smoothHeading(heading, sample.bearing, (time - last) / 1000) : sample.bearing
      marker.setRotation(heading)
    }
    last = time
    state.distance = distance ?? (t === 1 ? projected : null)
    if (state.distance != null) source()?.setData(trailFeatures(route, state.distance, color))
    else if (t === 1) source()?.setData(lineFeatureData(coords || []))
    if (!document.hidden && map.__followCamera && !map.__followPaused) map.jumpTo({ center: sample.position })
    if (t < 1) frames.set(id, requestAnimationFrame(frame))
    else frames.delete(id)
  }
  if (duration) frames.set(id, requestAnimationFrame(frame))
  else frame(now)
}

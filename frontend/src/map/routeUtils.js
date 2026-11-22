const radians = Math.PI / 180
const clamp = (value, min, max) => Math.max(min, Math.min(value, max))

export function haversine(a, b) {
  const h = Math.sin((b[1] - a[1]) * radians / 2) ** 2
    + Math.cos(a[1] * radians) * Math.cos(b[1] * radians)
    * Math.sin((b[0] - a[0]) * radians / 2) ** 2
  return 12_742_000 * Math.asin(Math.sqrt(clamp(h, 0, 1)))
}

export function bearing(a, b) {
  const x = (b[0] - a[0]) * radians
  const p = a[1] * radians
  const q = b[1] * radians
  return (Math.atan2(Math.sin(x) * Math.cos(q),
    Math.cos(p) * Math.sin(q) - Math.sin(p) * Math.cos(q) * Math.cos(x)) / radians + 360) % 360
}

export const shortestAngleDelta = (a, b) => ((b - a + 180) % 360 + 360) % 360 - 180
export const lerpAngle = (a, b, t) => ((a + shortestAngleDelta(a, b) * t) % 360 + 360) % 360
const interpolate = (a, b, t) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]

export async function fetchRoute(from, to, { signal } = {}) {
  if (haversine(from, to) < 0.1) return [from, to]
  try {
    const url = `https://router.project-osrm.org/route/v1/driving/${from.join(',')};${to.join(',')}?overview=full&geometries=geojson`
    const response = await fetch(url, { signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(8000)]) : AbortSignal.timeout(8000) })
    if (!response.ok) throw new Error(`OSRM: ${response.status}`)
    const coords = (await response.json()).routes?.[0]?.geometry?.coordinates
    return coords?.length > 1 ? coords : [from, to]
  } catch (error) {
    if (signal?.aborted) throw error
    return [from, to]
  }
}

export function buildRoute(input) {
  const coords = []
  const distances = []
  const headings = []
  for (const point of input) {
    const previous = coords.at(-1)
    const length = previous ? haversine(previous, point) : 0
    if (previous && length < 0.01) continue
    if (previous) headings.push(bearing(previous, point))
    coords.push(point)
    distances.push((distances.at(-1) ?? 0) + length)
  }
  const length = distances.at(-1) ?? 0
  function pointAtDistance(distance) {
    if (coords.length < 2) return { position: coords[0], bearing: 0, segmentIndex: 0 }
    const d = clamp(distance, 0, length)
    let lo = 0
    let hi = coords.length - 1
    while (hi - lo > 1) {
      const mid = (lo + hi) >> 1
      if (distances[mid] <= d) lo = mid
      else hi = mid
    }
    return { position: interpolate(coords[lo], coords[hi], (d - distances[lo]) / (distances[hi] - distances[lo])), bearing: headings[lo], segmentIndex: lo }
  }
  function project(point, near = 0) {
    let best = { distance: 0, offset: coords.length ? haversine(point, coords[0]) : Infinity }
    // Local tangent plane for projection; distances along the route stay in metres.
    const scale = Math.cos(point[1] * radians)
    for (let i = 0; i < coords.length - 1; i++) {
      const a = coords[i]
      const b = coords[i + 1]
      const x = (b[0] - a[0]) * scale
      const y = b[1] - a[1]
      const t = clamp((((point[0] - a[0]) * scale) * x + (point[1] - a[1]) * y) / (x * x + y * y), 0, 1)
      const offset = haversine(point, interpolate(a, b, t))
      const distance = distances[i] + t * (distances[i + 1] - distances[i])
      if (offset < best.offset - 0.01 || (Math.abs(offset - best.offset) <= 0.01
        && Math.abs(distance - near) < Math.abs(best.distance - near))) best = { distance, offset }
    }
    return best
  }
  return { coords, length, pointAtDistance, project }
}

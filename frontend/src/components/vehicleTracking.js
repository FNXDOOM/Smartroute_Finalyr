// Geometry is [longitude, latitude]. Never extrapolate beyond received GPS.
export function headingDelta(from, to) {
  return ((to - from + 540) % 360) - 180
}

export function vehicleKind(vehicle = {}) {
  const type = String(vehicle.vehicle_type || vehicle.type || vehicle.category || '').toLowerCase()
  if (/rickshaw|auto/.test(type)) return 'auto'
  if (/bike|motorcycle|scooter/.test(type)) return 'bike'
  if (/van|bus|minibus/.test(type)) return 'van'
  return 'car'
}

function project(point, path) {
  let best = null
  const scale = Math.cos(point[1] * Math.PI / 180)
  for (let i = 0; i < path.length - 1; i += 1) {
    const a = path[i], b = path[i + 1]
    const dx = (b[0] - a[0]) * scale, dy = b[1] - a[1]
    const t = Math.max(0, Math.min(1, (((point[0] - a[0]) * scale) * dx + (point[1] - a[1]) * dy) / (dx * dx + dy * dy || 1)))
    const position = [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]
    const distance = Math.hypot((position[0] - point[0]) * scale, position[1] - point[1]) * 111195
    if (!best || distance < best.distance) best = { position, index: i + t, distance }
  }
  return best
}

export function telemetryPath(from, to, route = []) {
  if (route.length < 2) return [from, to]
  const start = project(from, route), end = project(to, route)
  // Do not snap off-route telemetry or send vehicles backwards around a loop.
  if (start.distance > 35 || end.distance > 35 || end.index < start.index) return [from, to]
  const corners = route.slice(Math.floor(start.index) + 1, Math.ceil(end.index))
  return [from, start.position, ...corners, end.position, to]
}

export function vehicleSvg(kind) {
  const bike = kind === 'bike'
  const body = bike
    ? '<rect x="20" y="2" width="8" height="15" rx="4" fill="#24282c"/><rect x="20" y="45" width="8" height="15" rx="4" fill="#24282c"/><path d="M12 20h24M24 12v39" stroke="#343a40" stroke-width="4"/><rect x="17" y="16" width="14" height="30" rx="7" fill="#e7ecef" stroke="#454d55"/><rect x="19" y="29" width="10" height="14" rx="4" fill="#343a40"/>'
    : `<rect x="7" y="12" width="6" height="12" rx="2" fill="#20262b"/><rect x="35" y="12" width="6" height="12" rx="2" fill="#20262b"/><rect x="7" y="39" width="6" height="12" rx="2" fill="#20262b"/><rect x="35" y="39" width="6" height="12" rx="2" fill="#20262b"/><rect x="11" y="3" width="26" height="56" rx="${kind === 'van' ? 5 : 10}" fill="${kind === 'auto' ? '#efc748' : '#f5f7f8'}" stroke="#626c75" stroke-width="1.5"/><path d="M15 16Q24 12 33 16L32 26H16Z" fill="#465c6c"/><rect x="16" y="29" width="16" height="${kind === 'van' ? 20 : 12}" rx="3" fill="${kind === 'auto' ? '#303c36' : '#dce3e8'}"/><path d="M16 46h16l1 6H15Z" fill="#526573"/><path d="M14 8h5m10 0h5" stroke="#fff6cf" stroke-width="3"/><path d="M14 55h5m10 0h5" stroke="#c94f50" stroke-width="2"/>`
  return `<svg xmlns="http://www.w3.org/2000/svg" width="42" height="58" viewBox="0 0 48 64">${body}</svg>`
}

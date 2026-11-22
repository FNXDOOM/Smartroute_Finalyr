import assert from 'node:assert/strict'
import { setTimeout as delay } from 'node:timers/promises'
import { readFile, writeFile } from 'node:fs/promises'
import { animatePassengerFix, STALE_MS } from '../src/map/passengerMotion.js'
import { buildRoute, haversine, shortestAngleDelta } from '../src/map/routeUtils.js'

// Public landmarks, not rider addresses. Each of the 23 appears once per pickup role.
const places = [
  ['Majestic', 77.5728, 12.9767], ['Cubbon Park', 77.5928, 12.9764],
  ['MG Road', 77.6068, 12.9756], ['Ulsoor', 77.6198, 12.9777],
  ['Indiranagar', 77.6408, 12.9784], ['Domlur', 77.6382, 12.9597],
  ['Koramangala', 77.6245, 12.9363], ['BTM Layout', 77.6068, 12.9166],
  ['JP Nagar', 77.5855, 12.9064], ['Jayanagar', 77.5848, 12.9296],
  ['Lalbagh', 77.5859, 12.9507], ['Basavanagudi', 77.5736, 12.9417],
  ['Vijayanagar', 77.5356, 12.9710], ['Rajajinagar', 77.5569, 12.9917],
  ['Malleshwaram', 77.5708, 13.0035], ['Yeshwanthpur', 77.5488, 13.0238],
  ['Hebbal', 77.5913, 13.0382], ['RT Nagar', 77.5947, 13.0203],
  ['Frazer Town', 77.6146, 12.9975], ['Banaswadi', 77.6498, 13.0118],
  ['KR Puram', 77.6958, 13.0070], ['Tin Factory', 77.6693, 12.9972],
  ['Marathahalli', 77.6982, 12.9564],
]
const cachePath = process.env.BENGALURU_ROUTE_CACHE
let cache = {}
if (cachePath) {
  try { cache = JSON.parse(await readFile(cachePath, 'utf8')) } catch (error) {
    if (error.code !== 'ENOENT') throw error
  }
}
let lastRequest = 0

function replay(coords) {
  let now = 0
  let serial = 0
  let heading = 0
  let point = coords[0]
  let trail
  let frameCount = 0
  let furthestFrame = 0
  let largestTurn = 0
  const queue = new Map()
  const frames = new Map()
  Object.defineProperty(globalThis, 'performance', { value: { now: () => now }, configurable: true })
  globalThis.document = { hidden: false }
  globalThis.matchMedia = () => ({ matches: false })
  globalThis.requestAnimationFrame = fn => { queue.set(++serial, fn); return serial }
  globalThis.cancelAnimationFrame = id => queue.delete(id)
  const map = { __trackingRoute: coords, getSource: () => ({ setData: value => { trail = value } }) }
  const marker = {
    getLngLat: () => ({ toArray: () => point }), getRotation: () => heading,
    setLngLat(value) {
      if (queue.size === 0 && now > 0) furthestFrame = Math.max(furthestFrame, haversine(point, value))
      frameCount++
      point = value
    },
    setRotation(value) {
      if (now > 0) largestTurn = Math.max(largestTurn, Math.abs(shortestAngleDelta(heading, value)))
      heading = value
    },
  }
  const update = (fix, timestamp = now, leg = 'pickup') => animatePassengerFix(map, marker,
    { trackingKey: 'one-trip', trackingLeg: leg, trackingSnap: true, fixTimestamp: timestamp }, fix, 1, frames)
  function tick(ms) {
    now += ms
    const current = [...queue.values()]
    queue.clear()
    for (const fn of current) fn(now)
  }
  return { update, tick, marker, point: () => point, trail: () => trail, now: () => now,
    metrics: () => ({ frameCount, furthestFrame, largestTurn }) }
}

async function loadTrip(start, a, b) {
  const points = [start, a, b].map(([, lng, lat]) => `${lng},${lat}`).join(';')
  if (cache[points]) return cache[points]
  if (lastRequest) await delay(1100)
  lastRequest = Date.now()
  const response = await fetch(`https://router.project-osrm.org/route/v1/driving/${points}?overview=full&geometries=geojson`,
    { signal: AbortSignal.timeout(25_000) })
  assert.ok(response.ok, `OSRM HTTP ${response.status}`)
  const result = await response.json()
  const coords = result.routes?.[0]?.geometry?.coordinates
  assert.ok(coords?.length > 2 && result.routes[0].legs.length === 2, 'No two-leg road route returned')
  const trip = { coords, pickups: result.waypoints.slice(1).map(stop => stop.location), legs: result.routes[0].legs.map(({ distance }) => ({ distance })) }
  if (cachePath) {
    cache[points] = trip
    await writeFile(cachePath, JSON.stringify(cache))
  }
  return trip
}

let frames = 0
let worstMove = 0
let worstTurn = 0
let failures = 0
for (let i = 0; i < places.length; i++) {
  const names = [places[i], places[(i + 1) % places.length], places[(i + 4) % places.length]]
  try {
    const { coords, pickups, legs } = await loadTrip(...names)
    const route = buildRoute(coords)
    const firstPickup = route.project(pickups[0], legs[0].distance).distance
    assert.ok(firstPickup > 0 && firstPickup < route.length)
    const view = replay(coords)
    view.update(coords[0])
    const simulateLeg = (from, to) => {
      for (let d = Math.min(from + 24, to); ; d = Math.min(d + 24, to)) {
        view.update(route.pointAtDistance(d).position, view.now() + 1)
        for (let frame = 0; frame < 60; frame++) view.tick(1000 / 60 + 0.001)
        const progress = view.marker.trackingMotion.distance
        assert.ok(Math.abs(progress - d) <= 25, `lost route progress: expected ${d.toFixed(0)}m, got ${progress?.toFixed(0)}m`)
        if (d === to) break
      }
    }
    simulateLeg(0, firstPickup)
    assert.ok(haversine(view.point(), pickups[0]) <= 25, 'Missed first pickup')
    const stopped = view.point()
    view.tick(STALE_MS + 2000)
    assert.deepEqual(view.point(), stopped, 'Drove toward the next rider without GPS')
    simulateLeg(firstPickup, route.length)
    assert.ok(haversine(view.point(), pickups[1]) <= 25, 'Missed second pickup')
    assert.equal(view.trail().features.length, 1, 'Remaining trail still visible at the end')
    const { frameCount, furthestFrame, largestTurn } = view.metrics()
    assert.ok(furthestFrame <= 26, `large visible frame displacement: ${furthestFrame.toFixed(1)}m`)
    assert.ok(largestTurn <= 30, `large heading change: ${largestTurn.toFixed(1)}°`)
    frames += frameCount
    worstMove = Math.max(worstMove, furthestFrame)
    worstTurn = Math.max(worstTurn, largestTurn)
    console.log(`PASS ${i + 1}. ${names.map(place => place[0]).join(' → ')} (${(route.length / 1000).toFixed(1)} km)`)
  } catch (error) {
    failures++
    console.error(`FAIL ${i + 1}. ${names.map(place => place[0]).join(' → ')}: ${error.message}`)
  }
}
console.log(`${places.length - failures}/${places.length} road cases; ${frames} animation frames; max ${worstMove.toFixed(2)} m/frame, ${worstTurn.toFixed(1)}°/frame`)
if (failures) process.exitCode = 1

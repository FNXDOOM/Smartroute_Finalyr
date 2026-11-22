import assert from 'node:assert/strict'
import { test } from 'node:test'
import { buildRoute, haversine } from './routeUtils.js'
import { acceptFix, animatePassengerFix, routeProgress, smoothHeading, STALE_MS, trailFeatures } from './passengerMotion.js'

const coords = [[77, 13], [77.001, 13], [77.001, 13.003]]
const route = buildRoute(coords)

test('ignores old GPS and large jumps until the feed goes stale', () => {
  const fix = acceptFix(null, coords[0], 0, 100)
  assert.equal(acceptFix(fix, coords[1], 500, 99), null)
  assert.equal(acceptFix(fix, coords[2], 500, 101), null)
  assert.deepEqual(acceptFix(fix, coords[2], STALE_MS, 101).point, coords[2])
})

test('route progress rejects backtracking, large jumps and off-route fixes', () => {
  const progress = routeProgress(route, coords[1])
  assert.ok(progress > 100)
  assert.equal(routeProgress(route, coords[0], progress), null)
  assert.equal(routeProgress(route, coords[2], progress), null)
  assert.equal(routeProgress(route, [77.005, 13], progress), null)
})

test('takes the forward branch when the road after a U-turn overlaps the approach', () => {
  const loop = buildRoute([coords[0], coords[1], coords[0]])
  const expected = loop.length / 2 + 22
  const point = loop.pointAtDistance(expected).position
  assert.ok(Math.abs(routeProgress(loop, point, loop.length / 2) - expected) < 0.01)
})

test('travelled and remaining lines meet at the on-route position', () => {
  const [past, remaining] = trailFeatures(route, 40, '#2563eb').features
  assert.deepEqual(past.geometry.coordinates.at(-1), remaining.geometry.coordinates[0])
  assert.equal(remaining.properties.tint, '#2563eb')
  assert.ok(smoothHeading(359, 1, 1 / 60) > 359)
})

function harness(t) {
  let now = 0
  let serial = 0
  let point = coords[0]
  let heading = 0
  let trail
  const pending = new Map()
  const frames = new Map()
  const browser = { hidden: false }
  const reduced = { matches: false }
  t.mock.method(performance, 'now', () => now)
  const globals = { document: browser, matchMedia: () => reduced,
    requestAnimationFrame: fn => { pending.set(++serial, fn); return serial },
    cancelAnimationFrame: key => pending.delete(key) }
  for (const [key, value] of Object.entries(globals)) {
    globalThis[key] = value
    t.after(() => { delete globalThis[key] })
  }
  const marker = { getLngLat: () => ({ toArray: () => point }), getRotation: () => heading,
    setLngLat: value => { point = value }, setRotation: value => { heading = value } }
  const map = { __trackingRoute: coords, getSource: () => ({ setData: value => { trail = value } }) }
  const update = (distance, options = {}) => animatePassengerFix(map, marker,
    { trackingKey: 'ride', trackingSnap: true, fixTimestamp: now + 1, ...options },
    typeof distance === 'number' ? route.pointAtDistance(distance).position : distance, 1, frames)
  const tick = (ms) => {
    now += ms
    const work = [...pending.values()]
    pending.clear()
    work.forEach(fn => fn(now))
  }
  return { update, tick, point: () => point, trail: () => trail, map, browser, reduced }
}

test('two fixes before the first render glide from the visible marker, not the previous target', (t) => {
  const v = harness(t)
  v.update(0)
  v.update(25, { fixTimestamp: 2 })
  v.update(55, { fixTimestamp: 3 })
  v.tick(1000 / 60)
  assert.ok(haversine(coords[0], v.point()) < 1)
  v.tick(1000)
  assert.ok(haversine(route.pointAtDistance(55).position, v.point()) < 0.1)
})

test('driver no-show and older fixes do not move the marker toward pickup', (t) => {
  const v = harness(t)
  v.update(0)
  v.tick(STALE_MS * 2)
  assert.deepEqual(v.point(), coords[0])
  v.update(55, { fixTimestamp: 0 })
  v.tick(1000)
  assert.deepEqual(v.point(), coords[0])
})

test('reconnect after GPS silence reanchors; hidden tab skips drawing intermediate frames', (t) => {
  const v = harness(t)
  v.update(0)
  v.tick(STALE_MS + 1)
  v.update(300)
  assert.ok(haversine(route.pointAtDistance(300).position, v.point()) < 0.1)
  v.update(325, { fixTimestamp: STALE_MS + 3 })
  v.browser.hidden = true
  v.tick(7000)
  assert.ok(haversine(route.pointAtDistance(325).position, v.point()) < 0.1)
})

test('an off-route fix glides without falsely consuming the route, then a new route reanchors', (t) => {
  const v = harness(t)
  v.update(0)
  v.tick(1000)
  const offRoute = [77, 13.001]
  v.update(offRoute)
  v.tick(500)
  assert.ok(haversine(coords[0], v.point()) > 10 && haversine(offRoute, v.point()) > 10)
  v.tick(500)
  assert.deepEqual(v.trail().features[0].geometry.coordinates, coords)
  v.map.__trackingRoute = [offRoute, coords[2]]
  v.update(offRoute, { trackingKey: 'reroute' })
  assert.deepEqual(v.point(), offRoute)
})

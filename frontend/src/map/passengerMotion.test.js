import assert from 'node:assert/strict'
import { test } from 'node:test'
import { buildRoute } from './routeUtils.js'
import { acceptFix, routeProgress, smoothHeading, STALE_MS, trailFeatures } from './passengerMotion.js'

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

test('travelled and remaining lines meet at the on-route position', () => {
  const [past, remaining] = trailFeatures(route, 40, '#2563eb').features
  assert.deepEqual(past.geometry.coordinates.at(-1), remaining.geometry.coordinates[0])
  assert.equal(remaining.properties.tint, '#2563eb')
  assert.ok(smoothHeading(359, 1, 1 / 60) > 359)
})

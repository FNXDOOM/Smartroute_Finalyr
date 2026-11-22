import assert from 'node:assert/strict'
import { test } from 'node:test'
import VehicleAnimator from './VehicleAnimator.js'
import { buildRoute, lerpAngle, shortestAngleDelta } from './routeUtils.js'

const coords = [[77, 13], [77.001, 13], [77.001, 13.003]]

test('route removes duplicate points and uses the shorter turn across north', () => {
  const route = buildRoute([coords[0], ...coords])
  assert.equal(route.coords.length, 3)
  assert.deepEqual(route.pointAtDistance(route.length).position, coords[2])
  assert.equal(shortestAngleDelta(359, 1), 2)
  assert.equal(lerpAngle(359, 1, 0.5), 0)
})

test('real-time simulation at 30 Hz and 60 Hz advances the same distance in cruise', () => {
  const run = (fps) => {
    const car = new VehicleAnimator({ coords, sharedClock: true })
    car.start()
    car.distance = 40
    for (let i = 0; i < fps; i++) car.tick(1 / fps)
    return car.distance
  }
  assert.ok(Math.abs(run(30) - run(60)) < 1e-8)
})

test('short legs emit both stops once and finish', () => {
  const calls = []
  const car = new VehicleAnimator({
    coords: [[77, 13], [77.000001, 13]], sharedClock: true, pickupDistance: 0,
    onArrivePickup: () => calls.push('pickup'), onArriveDrop: () => calls.push('drop'),
  })
  car.start()
  for (let i = 0; i < 50; i++) car.tick(0.1)
  assert.deepEqual(calls, ['pickup', 'drop'])
  assert.equal(car.status, 'COMPLETED')
})

test('live mode glides along the route and rejects backwards and oversized fixes', () => {
  const car = new VehicleAnimator({ coords, sharedClock: true, live: true })
  car.start()
  assert.equal(car.animateTo(coords[1]), true)
  assert.equal(car.distance, 0)
  car.tick(0.5)
  assert.ok(car.distance > 0 && car.distance < 100)
  assert.equal(car.animateTo(coords[0]), false)
  assert.equal(car.animateTo(coords[2]), false)
  car.tick(0.5)
  assert.ok(Math.abs(car.distance - buildRoute(coords.slice(0, 2)).length) < 0.01)
})

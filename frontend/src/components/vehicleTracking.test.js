import { test } from 'node:test'
import assert from 'node:assert/strict'
import { headingDelta, telemetryPath, vehicleKind, vehicleSvg } from './vehicleTracking.js'

test('heading takes shortest turn across north', () => {
  assert.equal(headingDelta(350, 10), 20)
  assert.equal(headingDelta(10, 350), -20)
})

test('telemetry follows road corners and ends at actual GPS', () => {
  const route = [[77, 13], [77.001, 13], [77.001, 13.001]]
  const path = telemetryPath(route[0], route[2], route)
  assert.ok(path.some(point => point[0] === 77.001 && point[1] === 13))
  assert.deepEqual(path.at(-1), route[2])
})

test('off-route and reverse updates are not forced onto a route', () => {
  const route = [[77, 13], [77.001, 13]]
  const off = [78, 14]
  assert.deepEqual(telemetryPath(off, route[1], route), [off, route[1]])
  assert.deepEqual(telemetryPath(route[1], route[0], route), [route[1], route[0]])
})

test('vehicle variants have safe, local vector artwork', () => {
  for (const type of ['car', 'auto-rickshaw', 'motorcycle', 'minibus']) {
    assert.ok(vehicleSvg(vehicleKind({ vehicle_type: type })).startsWith('<svg'))
  }
  assert.equal(vehicleKind({ vehicle_type: 'motorcycle' }), 'bike')
  assert.equal(vehicleKind({ vehicle_type: 'auto-rickshaw' }), 'auto')
  assert.equal(vehicleKind({}), 'car')
})

import assert from 'node:assert/strict'
import { test } from 'node:test'
import { assignedDriverRoute, carpoolItinerary } from './driverCarpool.js'

test('does not select historical routes for an idle or reassigned vehicle', () => {
  const old = { vehicle_id: 1, route_id: 'old', status: 'solved' }
  const current = { vehicle_id: 1, route_id: 'current', status: 'needs_reoptimization' }
  assert.equal(assignedDriverRoute([old, current], { id: 1, assigned_route_id: null }), null)
  assert.equal(assignedDriverRoute([old], { id: 1, assigned_route_id: 'current' }), null)
  assert.equal(assignedDriverRoute([old, current], { id: 1, assigned_route_id: 'current' }), current)
  assert.equal(assignedDriverRoute([{ ...current, status: 'completed' }], { id: 1, assigned_route_id: 'current' }), null)
})

const waypoints = [
  { waypoint_type: 'depot', passenger_ids: [] },
  { waypoint_type: 'pickup', passenger_ids: [1, 2, 3] },
  { waypoint_type: 'destination', passenger_ids: [2] },
  { waypoint_type: 'destination', passenger_ids: [1, 3] },
]

test('keeps genuinely pending stops, even when the preview reaches the destination', () => {
  const view = carpoolItinerary(waypoints, [
    { id: 1, status: 'arriving' },
    { id: 2, status: 'in_progress', carpool_status: 'boarded' },
    { id: 3, status: 'completed' },
  ])
  assert.deepEqual(view.stops.map(stop => stop.riders.map(rider => rider.id)), [[1], [2], [1]])
  assert.equal(view.remainingCount, 2)
  assert.equal(view.boardedCount, 1)
  assert.equal(view.readyToClose, false)
})

test('clears terminal stops without mistaking missing ride data for completion', () => {
  const terminal = [{ id: 1, status: 'completed' }, { id: 2, status: 'cancelled' }]
  assert.equal(carpoolItinerary(waypoints, terminal).readyToClose, false)
  const view = carpoolItinerary(waypoints, [...terminal, { id: 3, status: 'completed' }])
  assert.equal(view.readyToClose, true)
  assert.deepEqual(view.stops, [])
})

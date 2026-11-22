import assert from 'node:assert/strict'
import { test } from 'node:test'
import { findActiveRide } from './passengerActiveRide.js'

test('restores the arriving ride even when newer recent rides were cancelled', () => {
  const active = { id: 10, status: 'arriving' }
  assert.equal(findActiveRide([{ id: 12, status: 'cancelled' }, { id: 11, status: 'cancelled' }, active]), active)
})

test('restores a confirmed pickup and ignores completed or cancelled rides', () => {
  const ready = { id: 9, status: 'ready_for_pickup' }
  assert.equal(findActiveRide([{ status: 'completed' }, ready]), ready)
  assert.equal(findActiveRide([{ status: 'cancelled' }, { status: 'completed' }]), null)
  assert.equal(findActiveRide([]), null)
})

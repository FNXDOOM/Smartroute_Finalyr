import { test } from 'node:test'
import assert from 'node:assert/strict'
import { runDemoStages } from './demoPipeline.js'

test('a failed backend stage blocks the rest of the demo', async () => {
  const steps = [async () => true, async () => false, () => assert.fail('unexpected dispatch')]
  assert.equal(await runDemoStages(steps, { isCurrent: () => true, wait: async () => {} }), 'failed')
})

test('reset during the last delay prevents playback', async () => {
  let current = true
  assert.equal(await runDemoStages([async () => true], {
    isCurrent: () => current,
    wait: async () => { current = false },
  }), 'superseded')
})

test('successful stages run in order before playback', async () => {
  const order = []
  const steps = ['book', 'cluster', 'dispatch'].map(name => async () => { order.push(name); return true })
  assert.equal(await runDemoStages(steps, { isCurrent: () => true, wait: async () => {} }), 'ready')
  assert.deepEqual(order, ['book', 'cluster', 'dispatch'])
})

// Only the current run may start the next stage or turn playback on.
export async function runDemoStages(steps, { isCurrent, wait }) {
  for (const step of steps) {
    if (!isCurrent()) return 'superseded'
    const ok = await step()
    if (!isCurrent()) return 'superseded'
    if (!ok) return 'failed'
    await wait()
  }
  return isCurrent() ? 'ready' : 'superseded'
}

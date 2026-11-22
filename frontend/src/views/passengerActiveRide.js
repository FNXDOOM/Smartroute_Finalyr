const ACTIVE_STATUSES = new Set([
  'pending', 'clustered', 'assigned', 'arriving', 'ready_for_pickup', 'in_progress',
])

// The ride history endpoint returns newest first.
export function findActiveRide(rides) {
  return rides.find(ride => ACTIVE_STATUSES.has(ride?.status)) ?? null
}

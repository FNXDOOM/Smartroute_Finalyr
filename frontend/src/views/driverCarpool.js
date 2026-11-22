const LIVE_PLANS = new Set(['solved', 'needs_reoptimization'])
const TERMINAL_RIDES = new Set(['completed', 'cancelled'])
const PICKUP_DONE = new Set(['boarded', 'in_transit', 'dropped_off', 'completed'])

export function assignedDriverRoute(routes, vehicle) {
  if (!vehicle?.assigned_route_id) return null
  return routes.find(route => route.vehicle_id === vehicle.id
    && route.route_id === vehicle.assigned_route_id && LIVE_PLANS.has(route.status)
    && route.route_metadata?.carpool_run_status !== 'completed') ?? null
}

export function carpoolItinerary(waypoints, rides) {
  const byId = new Map(rides.map(ride => [ride.id, ride]))
  const ids = new Set(waypoints.flatMap(stop => stop.passenger_ids ?? []))
  const known = [...ids].map(id => byId.get(id))
  const remaining = known.filter(ride => ride && !TERMINAL_RIDES.has(ride.status))
  const stops = waypoints.flatMap(stop => {
    const pickup = stop.waypoint_type === 'pickup'
    if (!pickup && !['destination', 'dropoff'].includes(stop.waypoint_type)) return []
    const riders = [...new Set(stop.passenger_ids ?? [])].flatMap(id => {
      const ride = byId.get(id)
      if (ride && (TERMINAL_RIDES.has(ride.status) || (pickup && (
        ride.status === 'in_progress' || PICKUP_DONE.has(ride.carpool_status)
      )))) return []
      return [{ id, ride }]
    })
    return riders.length ? [{ ...stop, pickup, riders }] : []
  })
  return {
    stops,
    remainingCount: remaining.length + known.filter(ride => !ride).length,
    boardedCount: remaining.filter(ride => ride.carpool_status === 'boarded').length,
    readyToClose: known.length > 0 && known.every(ride => ride && TERMINAL_RIDES.has(ride.status)),
  }
}

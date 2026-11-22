import { useEffect, useRef, useState } from 'react'
import VehicleAnimator, { SPEEDS, STOP_SECONDS } from './VehicleAnimator.js'
import { buildRoute, fetchRoute, haversine } from './routeUtils.js'

export const CITY = [77.5946, 12.9716]
const TYPES = Object.keys(SPEEDS)
const randomPoint = () => {
  const angle = Math.random() * 2 * Math.PI
  const radius = 0.042 * Math.sqrt(Math.random())
  return [CITY[0] + radius * Math.cos(angle), CITY[1] + radius * Math.sin(angle)]
}
const endpoint = (coords, point) => haversine(coords.at(-1), point) < 0.01 ? coords : [...coords, point]

export default function useRideSimulation({ count = 12, live, multiplier, draw }) {
  const [vehicles, setVehicles] = useState([])
  const [connection, setConnection] = useState('Connecting to demo feed…')
  const settings = useRef({ draw, multiplier })
  useEffect(() => { settings.current = { draw, multiplier } }, [draw, multiplier])

  useEffect(() => {
    const fleet = new Map()
    const pending = new Map()
    const controller = new AbortController()
    const queue = []
    let busy = false
    let nextRequest = 0
    let frame
    let last
    let lastSidebar = -Infinity
    let socket

    function install(id, type, coords, pickupDistance, revision) {
      fleet.get(id)?.animator?.destroy()
      const animator = new VehicleAnimator({ type, coords, pickupDistance, live, sharedClock: true })
      const car = { id, type, animator, revision, completedFor: 0 }
      fleet.set(id, car)
      animator.start()
      return car
    }

    function enqueue(id, from, type) {
      fleet.get(id)?.animator?.destroy()
      fleet.set(id, { id, type, origin: from })
      queue.push({ id, from, type })
    }

    async function loadTrip({ id, from, type }) {
      busy = true
      const pickup = randomPoint()
      const drop = randomPoint()
      const signal = controller.signal
      try {
        const first = endpoint([from, ...await fetchRoute(from, pickup, { signal })], pickup)
        await new Promise((resolve) => {
          const cancel = () => { clearTimeout(timer); resolve() }
          const timer = setTimeout(() => { signal.removeEventListener('abort', cancel); resolve() }, 1000)
          if (signal.aborted) cancel()
          else signal.addEventListener('abort', cancel, { once: true })
        })
        if (signal.aborted) return
        const second = endpoint([pickup, ...await fetchRoute(pickup, drop, { signal })], drop)
        if (!signal.aborted) install(id, type, [...first, ...second.slice(1)], buildRoute(first).length)
      } catch {
        // The routing adapter already falls back; abort means the demo was closed.
      } finally {
        busy = false
        nextRequest = performance.now() + 1000
      }
    }

    if (live) {
      socket = new WebSocket(import.meta.env.VITE_VEHICLE_WS_URL || 'ws://localhost:8000/ws/vehicles')
      socket.onopen = () => setConnection('Synthetic GPS feed connected')
      socket.onclose = () => setConnection('Feed disconnected. Start the demo server, then toggle Live mode.')
      socket.onerror = () => setConnection('Could not connect to the demo feed.')
      socket.onmessage = ({ data }) => {
        try {
          const records = JSON.parse(data)
          if (!Array.isArray(records)) return
          for (const record of records) {
            if (record.id == null || !Number.isFinite(record.lat) || !Number.isFinite(record.lng)) continue
            const older = pending.get(record.id)
            pending.set(record.id, { ...record, coords: record.coords ?? (older?.revision === record.revision ? older.coords : undefined) })
          }
        } catch { /* Ignore invalid feed messages. */ }
      }
    } else {
      for (let i = 0; i < count; i++) enqueue(i + 1, randomPoint(), TYPES[Math.floor(Math.random() * TYPES.length)])
    }

    function render(now) {
      if (document.hidden) {
        last = undefined
        return
      }
      const dt = last == null ? 0 : Math.min((now - last) / 1000, 0.1)
      last = now
      const { multiplier: speed, draw: paint } = settings.current
      if (!busy && queue.length && now >= nextRequest) void loadTrip(queue.shift())
      for (const record of pending.values()) {
        let car = fleet.get(record.id)
        if ((!car || car.revision !== record.revision) && record.coords?.length) {
          car = install(record.id, record.type, record.coords, record.pickupDistance, record.revision)
        }
        if (car && car.revision === record.revision) {
          if (car.animator.animateTo([record.lng, record.lat])) car.animator.setLiveStatus(record.status)
        }
      }
      pending.clear()
      for (const car of fleet.values()) {
        const animator = car.animator
        if (!animator) continue
        animator.tick(live ? dt : dt * speed)
        if (!live && animator.status === 'COMPLETED') {
          car.completedFor += dt
          if (car.completedFor >= 2) enqueue(car.id, animator.sample.position, car.type)
        }
      }
      paint(fleet)
      if (now - lastSidebar >= 250) {
        lastSidebar = now
        setVehicles(Array.from(fleet.values(), ({ id, type, animator }) => {
          const remaining = animator ? animator.route.length - animator.distance : null
          const status = animator?.status ?? 'IDLE'
          const wait = !animator || status === 'COMPLETED' ? 0 : animator.wait
            + (status === 'TO_PICKUP' ? STOP_SECONDS : 0) + (status === 'WAITING_DROP' ? 0 : STOP_SECONDS)
          return { id, type, status, remaining, eta: remaining == null ? null : Math.ceil((remaining / (SPEEDS[type] ?? 10) + wait) / (live ? 1 : speed)) }
        }))
      }
      frame = requestAnimationFrame(render)
    }
    const visibility = () => {
      cancelAnimationFrame(frame)
      last = undefined
      if (!document.hidden) frame = requestAnimationFrame(render)
    }
    document.addEventListener('visibilitychange', visibility)
    visibility()
    return () => {
      document.removeEventListener('visibilitychange', visibility)
      cancelAnimationFrame(frame)
      controller.abort()
      for (const car of fleet.values()) car.animator?.destroy()
      if (socket) {
        socket.onopen = socket.onmessage = socket.onclose = socket.onerror = null
        socket.close()
      }
    }
  }, [count, live])
  return { vehicles, connection }
}

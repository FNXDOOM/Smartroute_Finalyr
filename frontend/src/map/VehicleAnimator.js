import { buildRoute, haversine, lerpAngle } from './routeUtils.js'

export const SPEEDS = { bike: 8, auto: 7, car: 10, suv: 10 }
export const STOP_SECONDS = 1.5
const RAMP_METRES = 20
const GLIDE_SECONDS = 1
const MAX_JUMP = 200
const SNAP_METRES = 65
const TURN_RATE = -60 * Math.log(0.85)

export default class VehicleAnimator {
  constructor({ type = 'car', coords = [], pickupDistance, live = false, onUpdate, onArrivePickup, onArriveDrop, sharedClock = false } = {}) {
    Object.assign(this, { live, onUpdate, onArrivePickup, onArriveDrop, sharedClock })
    this.speed = SPEEDS[type] ?? SPEEDS.car
    this.setRoute(coords, pickupDistance)
  }

  setRoute(coords, pickupDistance) {
    this.route = buildRoute(coords)
    this.pickup = pickupDistance == null ? null : Math.min(this.route.length, Math.max(0, pickupDistance))
    this.distance = 0
    this.heading = this.route.pointAtDistance(0).bearing
    this.lastFix = null
    this.glide = null
    this.wait = 0
    this.status = 'IDLE'
  }

  setSpeed(mps) { if (Number.isFinite(mps) && mps > 0) this.speed = mps }

  start() {
    if (this.destroyed) return
    if (this.status === 'IDLE') this.status = this.pickup == null ? 'TO_DROP' : 'TO_PICKUP'
    this.resume()
  }

  resume() {
    if (this.running || this.destroyed) return
    this.running = true
    if (this.sharedClock) return
    let last
    const frame = (now) => {
      if (!this.running) return
      if (!document.hidden && last != null) this.tick(Math.min((now - last) / 1000, 0.1))
      last = document.hidden ? undefined : now
      if (this.running) this.frame = requestAnimationFrame(frame)
    }
    this.frame = requestAnimationFrame(frame)
  }

  pause() {
    this.running = false
    if (this.frame != null) cancelAnimationFrame(this.frame)
    this.frame = null
  }

  destroy() { this.pause(); this.destroyed = true }

  setLiveStatus(status) {
    if (!this.live || status === this.status) return
    const previous = this.status
    this.status = status
    if (status === 'WAITING_PICKUP' || (previous === 'TO_PICKUP' && status === 'TO_DROP')) this.onArrivePickup?.()
    if (status === 'WAITING_DROP' || (previous === 'TO_DROP' && status === 'COMPLETED')) this.onArriveDrop?.()
  }

  animateTo(position) {
    if (!this.live || this.destroyed || !this.route.coords.length || !position.every(Number.isFinite)) return false
    const previous = this.lastFix
    const fix = this.route.project(position, previous?.distance ?? this.distance)
    if (fix.offset > SNAP_METRES || (previous && (
      fix.distance < previous.distance || fix.distance - previous.distance > MAX_JUMP
      || haversine(previous.position, position) > MAX_JUMP))) return false
    this.lastFix = { ...fix, position }
    this.glide = { from: this.distance, to: Math.max(this.distance, fix.distance), elapsed: 0 }
    return true
  }

  tick(dt) {
    if (!this.running || !this.route.coords.length) return
    if (this.live) {
      if (this.glide) {
        const glide = this.glide
        glide.elapsed += dt
        const t = Math.min(glide.elapsed / GLIDE_SECONDS, 1)
        this.distance = glide.from + (glide.to - glide.from) * t * t * (3 - 2 * t)
        if (t === 1) this.glide = null
      }
    } else if (this.wait > 0) {
      this.wait = Math.max(0, this.wait - dt)
      if (!this.wait) this.status = this.status === 'WAITING_PICKUP' ? 'TO_DROP' : 'COMPLETED'
    } else if (this.status === 'TO_PICKUP' || this.status === 'TO_DROP') {
      const pickup = this.status === 'TO_PICKUP'
      const end = pickup ? this.pickup : this.route.length
      const start = pickup ? 0 : this.pickup ?? 0
      const ramp = Math.min(RAMP_METRES, (end - start) / 2) || 1
      const factor = 0.25 + 0.75 * Math.min(1, Math.max(0, Math.min(this.distance - start, end - this.distance) / ramp))
      this.distance = Math.min(end, this.distance + this.speed * factor * dt)
      if (this.distance >= end) {
        this.wait = STOP_SECONDS
        this.status = pickup ? 'WAITING_PICKUP' : 'WAITING_DROP'
        if (pickup) this.onArrivePickup?.()
        else this.onArriveDrop?.()
      }
    }
    const sample = this.route.pointAtDistance(this.distance)
    this.heading = lerpAngle(this.heading, sample.bearing, 1 - Math.exp(-TURN_RATE * dt))
    this.sample = { ...sample, bearing: this.heading, distanceTravelled: this.distance }
    const route = this.route
    this.onUpdate?.({ ...this.sample, get remainingCoords() { return [sample.position, ...route.coords.slice(sample.segmentIndex + 1)] } })
  }
}

const SOURCE = 'demo-trails'
const IDS = ['demo-travelled', 'demo-remaining', 'demo-pickup-pulse', 'demo-pickup', 'demo-drop']
const feature = (type, coordinates, kind, color) => ({ type: 'Feature', geometry: { type, coordinates }, properties: { kind, color } })
const filter = (kind) => ['==', ['get', 'kind'], kind]

export function installRouteTrail(map) {
  const square = new Uint8Array(12 * 12 * 4)
  for (let i = 0; i < square.length; i += 4) square.set([211, 55, 60, 255], i)
  map.addImage('demo-drop-square', { width: 12, height: 12, data: square })
  map.addSource(SOURCE, { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
  for (const [id, kind, opacity] of [[IDS[0], 'travelled', 0.48], [IDS[1], 'remaining', 0.86]]) {
    map.addLayer({ id, source: SOURCE, type: 'line', filter: filter(kind),
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: { 'line-color': ['get', 'color'], 'line-width': 3, 'line-opacity': opacity } })
  }
  for (const [id, radius, opacity] of [[IDS[2], 10, 0.2], [IDS[3], 5, 1]]) {
    map.addLayer({ id, source: SOURCE, type: 'circle', filter: filter('pickup'),
      paint: { 'circle-radius': radius, 'circle-color': '#198653', 'circle-opacity': opacity } })
  }
  map.addLayer({ id: IDS[4], source: SOURCE, type: 'symbol', filter: filter('drop'),
    layout: { 'icon-image': 'demo-drop-square', 'icon-size': 0.75, 'icon-allow-overlap': true } })

  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches
  return {
    draw(fleet, { hideTravelled, selected, all }) {
      const features = []
      const addLine = (points, kind, color) => {
        if (points.length >= 2) features.push(feature('LineString', points, kind, color))
      }
      for (const [id, { animator }] of all ? fleet : [[selected, fleet.get(selected) ?? {}]]) {
        const sample = animator?.sample
        if (!sample) continue
        const { coords } = animator.route
        const { position, segmentIndex: i } = sample
        const focused = selected === id
        if (!hideTravelled && animator.distance > 0) addLine([...coords.slice(0, i + 1), position], 'travelled', '#a8adb4')
        const pickup = animator.pickup == null ? null : animator.route.pointAtDistance(animator.pickup)
        if (pickup && animator.distance < animator.pickup) {
          addLine([position, ...coords.slice(i + 1, pickup.segmentIndex + 1), pickup.position], 'remaining', '#255cba')
          addLine([pickup.position, ...coords.slice(pickup.segmentIndex + 1)], 'remaining', '#222d3a')
        } else if (animator.distance < animator.route.length) {
          addLine([position, ...coords.slice(i + 1)], 'remaining', '#222d3a')
        }
        if (focused || !all) {
          if (pickup) features.push(feature('Point', pickup.position, 'pickup', '#198653'))
          features.push(feature('Point', coords.at(-1), 'drop', '#d3373c'))
        }
      }
      map.getSource(SOURCE).setData({ type: 'FeatureCollection', features })
      if (!reducedMotion) map.setPaintProperty(IDS[2], 'circle-radius', 8 + 3 * Math.sin(performance.now() / 260))
    },
    destroy() {
      for (const id of IDS) map.removeLayer(id)
      map.removeSource(SOURCE)
      map.removeImage('demo-drop-square')
    },
  }
}

const SOURCE = 'demo-fleet'
const SHAPES = {
  bike: '<rect x="20" y="4" width="8" height="40" rx="4" fill="#101820"/><rect x="15" y="12" width="18" height="5" rx="2" fill="#101820"/><rect x="17" y="15" width="14" height="16" rx="6" fill="#ffb954"/>',
  auto: '<rect x="13" y="14" width="22" height="29" rx="5" fill="#183d35"/><path d="M14 20 Q15 7 24 5 Q33 7 34 20 Z" fill="#ffce52"/><rect x="16" y="22" width="16" height="14" rx="3" fill="#efb743"/>',
  car: '<rect x="12" y="4" width="24" height="40" rx="8" fill="#164ca6"/><path d="M16 18 L18 12 H30 L32 18 Z M16 33 H32 L30 38 H18 Z" fill="#b7defc"/>',
  suv: '<rect x="10" y="3" width="28" height="42" rx="7" fill="#27313b"/><path d="M14 17 L17 10 H31 L34 17 Z M14 34 H34 V39 H14 Z" fill="#acc7d5"/><path d="M13 21 V31 M35 21 V31" stroke="#fff" stroke-width="2"/>',
}

export async function installVehicleLayer(map, signal) {
  const icons = await Promise.all(Object.entries(SHAPES).map(async ([type, body]) => {
    const image = new Image()
    image.src = `data:image/svg+xml,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 48 48"><circle cx="24" cy="24" r="23" fill="#fff" fill-opacity=".93"/>${body}</svg>`)}`
    await image.decode()
    return [type, image]
  }))
  if (signal.aborted) return
  for (const [type, image] of icons) map.addImage(`demo-${type}`, image, { pixelRatio: 2 })
  map.addSource(SOURCE, { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
  map.addLayer({
    id: SOURCE, type: 'symbol', source: SOURCE,
    layout: {
      'icon-image': ['concat', 'demo-', ['get', 'type']], 'icon-rotate': ['get', 'bearing'],
      'icon-rotation-alignment': 'map', 'icon-allow-overlap': true, 'icon-anchor': 'center',
    },
  })
  return {
    draw(fleet) {
      const features = []
      for (const car of fleet.values()) {
        const sample = car.animator?.sample
        const position = sample?.position ?? car.origin
        if (position) features.push({
          id: car.id, type: 'Feature', geometry: { type: 'Point', coordinates: position },
          properties: { type: Object.hasOwn(SHAPES, car.type) ? car.type : 'car', bearing: sample?.bearing ?? 0 },
        })
      }
      map.getSource(SOURCE).setData({ type: 'FeatureCollection', features })
    },
    destroy() {
      map.removeLayer(SOURCE)
      map.removeSource(SOURCE)
      for (const type of Object.keys(SHAPES)) map.removeImage(`demo-${type}`)
    },
  }
}

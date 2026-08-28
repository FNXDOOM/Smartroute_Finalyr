// Fixed data used only by the presentation and driver-navigation visualizations.
export const DEMO_PRESETS = {
  indiranagar: {
    zone: 'Indiranagar Corridor',
    depot: { lat: 12.9784, lng: 77.6408, label: 'Indiranagar Transit Hub (Depot)' },
    riders: [
      { id: 101, name: 'Ananya Sharma', plat: 12.97190, plng: 77.64124, plbl: 'Indiranagar 100 Feet Rd (Stop A)', dlat: 12.9756, dlng: 77.6066, dlbl: 'MG Road Metro Station', fare: '₹45' },
      { id: 102, name: 'Rohan Mehta',   plat: 12.97192, plng: 77.64126, plbl: 'Indiranagar 100 Feet Rd (Stop B)', dlat: 12.9749, dlng: 77.6080, dlbl: 'Church Street Boulevard', fare: '₹42' },
      { id: 103, name: 'Priya Iyer',    plat: 12.97194, plng: 77.64120, plbl: 'Indiranagar 100 Feet Rd (Stop C)', dlat: 12.9734, dlng: 77.6075, dlbl: 'Brigade Road Junction', fare: '₹48' },
    ],
    virtualStop: { lat: 12.97192, lng: 77.64124, label: 'Virtual Boarding Stop #1 · 100 Feet Rd' },
    roadPath: [
      [77.6408, 12.9784], [77.6410, 12.9765], [77.6411, 12.9740],
      [77.64124, 12.97192], [77.6380, 12.9721], [77.6320, 12.9725],
      [77.6250, 12.9730], [77.6180, 12.9738], [77.6120, 12.9745],
      [77.6080, 12.9749], [77.6075, 12.9734], [77.6066, 12.9756],
    ],
  },
}

export const DEMO_STAGES = [
  { id: 'SPAWN', title: '1. Spawn Riders', icon: '👥', subtitle: 'Seed one route and two near-route requests', desc: 'Creates Passenger 1 at the origin and two candidates near the planned route.' },
  { id: 'CLUSTER', title: '2. HDBSCAN Density', icon: '🧬', subtitle: 'Identify high-density pickup cluster', desc: 'Density-based spatial clustering groups nearby requests with leaf selection.' },
  { id: 'VIRTUAL_STOP', title: '3. Virtual Stop', icon: '🚏', subtitle: 'Selected pickup snapped to drivable OSM road', desc: 'K-Medoids computes the pooled boarding stop near the selected pickup.' },
  { id: 'VRP_SOLVE', title: '4. CVRP & Hungarian', icon: '⚡', subtitle: 'OR-Tools multi-stop routing + Vehicle', desc: 'Solves capacitated VRP and assigns nearest idle vehicle KA-01-TEST-99.' },
  { id: 'DRIVE_SIM', title: '5. Live Transit Sim', icon: '🚗', subtitle: 'Real-time traversal from pickup to destination', desc: 'Vehicle navigates along the selected road route, boards riders, and completes the trip.' },
]

export const createDemoRunId = () => (
  globalThis.crypto?.randomUUID?.() || `demo-${Date.now()}-${Math.random().toString(16).slice(2)}`
)

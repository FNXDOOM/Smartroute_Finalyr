import axios from 'axios';

let authTokenGetter = null;
const appBootstrapRequests = new Map();

export const setAuthTokenGetter = (getter) => { authTokenGetter = getter; };

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
const WS_BASE_URL = API_BASE_URL.replace(/^http/, 'ws');
// MapTiler/Stadia are recommended for production; Photon remains a keyless
// development fallback so the app still works before provider keys are added.
const GEOCODER_PROVIDER = (import.meta.env.VITE_GEOCODER_PROVIDER || 'photon').toLowerCase();
const GEOCODER_URL = import.meta.env.VITE_GEOCODER_URL || 'https://photon.komoot.io/api';
const MAPTILER_KEY = import.meta.env.VITE_MAPTILER_KEY;
const STADIA_KEY = import.meta.env.VITE_STADIA_API_KEY;
const ROUTER_URL = import.meta.env.VITE_ROUTER_URL || '';
const ROUTER_ENGINE = (import.meta.env.VITE_ROUTER_ENGINE || 'osrm').toLowerCase();
const INDIA_BBOX = '68.1,6.5,97.4,35.7';

const COMMON_LOCATION_TYPOS = {
  chruch: 'church',
  churh: 'church',
  indranagar: 'indiranagar',
  indiranagr: 'indiranagar',
  banglore: 'bengaluru',
  bangluru: 'bengaluru',
};

function normaliseLocationQuery(query) {
  return query.split(/(\s+)/).map(part => COMMON_LOCATION_TYPOS[part.toLowerCase()] || part).join('');
}

function decodePolyline(encoded, precision = 6) {
  const coordinates = [];
  let index = 0, lat = 0, lng = 0;
  const factor = 10 ** precision;
  while (index < encoded.length) {
    let shift = 0, result = 0, byte;
    do { byte = encoded.charCodeAt(index++) - 63; result |= (byte & 0x1f) << shift; shift += 5; } while (byte >= 0x20);
    lat += (result & 1) ? ~(result >> 1) : result >> 1;
    shift = 0; result = 0;
    do { byte = encoded.charCodeAt(index++) - 63; result |= (byte & 0x1f) << shift; shift += 5; } while (byte >= 0x20);
    lng += (result & 1) ? ~(result >> 1) : result >> 1;
    coordinates.push([lng / factor, lat / factor]);
  }
  return coordinates;
}

const client = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  timeout: 10000,
});

client.interceptors.request.use(async (config) => {
  const token = authTokenGetter ? await authTokenGetter() : null;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
}, (error) => Promise.reject(error));

// ─── Auth ─────────────────────────────────────────────────────────────────────
export const authApi = {
  getProfile: async () => (await client.get('/auth/me')).data,
  updateProfile: async (fields) => (await client.patch('/auth/me', fields)).data,
};

// ─── Rides ────────────────────────────────────────────────────────────────────
export const ridesApi = {
  create: async (payload) => (await client.post('/rides/request', payload)).data,
  getMyRides: async () => {
    const data = (await client.get('/rides/my-rides')).data;
    return Array.isArray(data) ? data : (data.rides || []);
  },
  getAll: async (params = {}) => {
    const data = (await client.get('/rides/', { params })).data;
    return Array.isArray(data) ? data : (data.rides || []);
  },
  getById: async (id) => (await client.get(`/rides/${id}`)).data,
  getVehicle: async (id) => (await client.get(`/rides/${id}/vehicle`)).data,
  updateStatus: async (id, status) => (await client.patch(`/rides/${id}/status`, { status })).data,
  cancel: async (id) => (await client.delete(`/rides/${id}`)).data,
};

// ─── Geocoding ───────────────────────────────────────────────────────────────
export const geocodeApi = {
  suggest: async (query, bias) => {
    const corrected = normaliseLocationQuery(query);
    const queries = [...new Set([query, corrected, `${corrected}, India`])];
    if (GEOCODER_PROVIDER === 'maptiler' && MAPTILER_KEY) {
      const response = await axios.get(`https://api.maptiler.com/geocoding/${encodeURIComponent(corrected)}.json`, {
        params: { key: MAPTILER_KEY, limit: 8, country: 'IN', ...(bias?.lat != null ? { proximity: `${bias.lng},${bias.lat}` } : {}) }, timeout: 7000,
      });
      return (response.data?.features || []).map(feature => {
        const [lng, lat] = feature.geometry.coordinates;
        return { lat, lng, label: feature.place_name || feature.text || query, raw: feature };
      });
    }
    if (GEOCODER_PROVIDER === 'stadia' && STADIA_KEY) {
      const response = await axios.get('https://api.stadiamaps.com/geocoding/v1/autocomplete', {
        params: { text: corrected, api_key: STADIA_KEY, lang: 'en', focus_point: bias?.lat != null ? `${bias.lng},${bias.lat}` : undefined, boundary_country: 'IN' }, timeout: 7000,
      });
      return (response.data?.features || []).map(feature => {
        const [lng, lat] = feature.geometry.coordinates;
        return { lat, lng, label: feature.properties?.label || feature.properties?.name || query, raw: feature };
      });
    }
    const responses = await Promise.all(queries.map(searchQuery => axios.get(GEOCODER_URL, {
      params: { q: searchQuery, limit: 8, bbox: INDIA_BBOX, ...(bias?.lat != null ? { lat: bias.lat, lon: bias.lng } : {}) },
      timeout: 7000,
      headers: { Accept: 'application/json' },
    })));
    const results = responses.flatMap(response => response.data?.features || [])
      .filter(feature => feature.geometry?.coordinates)
      .filter(feature => {
        const [lng, lat] = feature.geometry.coordinates;
        const countryCode = String(feature.properties?.countrycode || '').toUpperCase();
        return countryCode === 'IN'
          && lng >= 68.1 && lng <= 97.4 && lat >= 6.5 && lat <= 35.7;
      }).map(feature => {
      const [lng, lat] = feature.geometry.coordinates;
      const p = feature.properties || {};
      const label = [p.name, p.street, p.locality, p.city, p.country].filter(Boolean).filter((v, i, a) => a.indexOf(v) === i).join(', ');
      return { lat, lng, label: label || query, raw: feature };
    });
    // India is the product's service area. Never display a similarly named
    // result from the United States, Liberia, Bangladesh, or another country.
    return results.filter((result, index, all) => all.findIndex(item => item.lat === result.lat && item.lng === result.lng) === index);
  },
  search: async (query, bias) => {
    const results = await geocodeApi.suggest(query, bias);
    if (!results.length) throw new Error('Location not found');
    return results[0];
  },
  reverse: async (lat, lng) => {
    if (GEOCODER_PROVIDER === 'maptiler' && MAPTILER_KEY) {
      const response = await axios.get(`https://api.maptiler.com/geocoding/${lng},${lat}.json`, { params: { key: MAPTILER_KEY, limit: 1 }, timeout: 7000 });
      const feature = response.data?.features?.[0];
      if (!feature) throw new Error('Location not found');
      return { lat, lng, label: feature.place_name || feature.text || 'Current location' };
    }
    if (GEOCODER_PROVIDER === 'stadia' && STADIA_KEY) {
      const response = await axios.get('https://api.stadiamaps.com/geocoding/v1/reverse', { params: { lat, lon: lng, api_key: STADIA_KEY }, timeout: 7000 });
      const feature = response.data?.features?.[0];
      if (!feature) throw new Error('Location not found');
      return { lat, lng, label: feature.properties?.label || 'Current location' };
    }
    const response = await axios.get(`${GEOCODER_URL}/reverse`, {
      params: { lat, lon: lng }, timeout: 7000, headers: { Accept: 'application/json' },
    });
    const p = response.data?.features?.[0]?.properties || {};
    if (p.countrycode && String(p.countrycode).toUpperCase() !== 'IN') throw new Error('Current location is outside India');
    return { lat, lng, label: [p.name, p.street, p.locality, p.city, p.country].filter(Boolean).join(', ') || 'Current location' };
  },
};

// ─── Routing / route validation ─────────────────────────────────────────────
export const routingApi = {
  route: async (from, to) => {
    if (!ROUTER_URL) return null;
    if (ROUTER_ENGINE === 'valhalla') {
      const response = await axios.post(`${ROUTER_URL.replace(/\/$/, '')}/route`, {
        locations: [{ lat: from.lat, lon: from.lng }, { lat: to.lat, lon: to.lng }],
        costing: 'auto', units: 'kilometers', directions_options: { units: 'kilometers' },
      }, { timeout: 10000 });
      const summary = response.data?.trip?.summary || {};
      const shape = response.data?.trip?.legs?.flatMap(leg => leg.shape ? decodePolyline(leg.shape) : []) || [];
      return { distanceMeters: (summary.length || 0) * 1000, durationSeconds: summary.time || 0, geometry: shape };
    }
    const base = ROUTER_URL.replace(/\/$/, '');
    const response = await axios.get(`${base}/route/v1/driving/${from.lng},${from.lat};${to.lng},${to.lat}`, {
      params: { overview: 'full', geometries: 'geojson', alternatives: 'false' }, timeout: 10000,
    });
    const route = response.data?.routes?.[0];
    if (!route) throw new Error('No drivable route found');
    return { distanceMeters: route.distance, durationSeconds: route.duration, geometry: route.geometry?.coordinates || [] };
  },
};

// ─── Vehicles ─────────────────────────────────────────────────────────────────
export const vehiclesApi = {
  list: async () => (await client.get('/vehicle/')).data,
  idle: async () => (await client.get('/vehicle/idle')).data,
  create: async (payload) => (await client.post('/vehicle/', payload)).data,
  update: async (id, payload) => (await client.patch(`/vehicle/${id}`, payload)).data,
  assign: async (payload) => (await client.post('/vehicle/assign', payload)).data,
};

// ─── Notifications ────────────────────────────────────────────────────────────
export const notificationsApi = {
  list: async (params = {}) => (await client.get('/notifications/', { params })).data,
  unreadCount: async () => (await client.get('/notifications/unread-count')).data,
  markRead: async (id) => (await client.patch(`/notifications/${id}/read`)).data,
  markAllRead: async () => (await client.patch('/notifications/read-all')).data,
};

// ─── Tracking ─────────────────────────────────────────────────────────────────
export const trackingApi = {
  getFeed: async () => (await client.get('/tracking/feed')).data,
  getEvents: async () => (await client.get('/tracking/events')).data,
  updateLocation: async (vehicleId, payload) =>
    (await client.post(`/tracking/vehicles/${vehicleId}/location`, payload)).data,
};

// ─── Cluster ──────────────────────────────────────────────────────────────────
export const clusterApi = {
  run: async (payload = { resolution: 9, min_cluster_size: 2 }) =>
    (await client.post('/cluster/run', payload)).data,
  history: async (limit = 20) => (await client.get('/cluster/history', { params: { limit } })).data,
  getById: async (id) => (await client.get(`/cluster/history/${id}`)).data,
};

// ─── Route ────────────────────────────────────────────────────────────────────
export const routeApi = {
  optimize: async (payload) => (await client.post('/route/optimize', payload)).data,
  history: async (limit = 20) => (await client.get('/route/history', { params: { limit } })).data,
  getById: async (id) => (await client.get(`/route/history/${id}`)).data,
};

// ─── Analytics ────────────────────────────────────────────────────────────────
export const analyticsApi = {
  overview: async () => (await client.get('/analytics/overview')).data,
  daily: async (days = 14) => (await client.get('/analytics/daily', { params: { days } })).data,
};

// ─── Predict ──────────────────────────────────────────────────────────────────
export const predictApi = {
  heatmap: async (params) => {
    const p = params || { min_lat: 12.8, max_lat: 13.1, min_lng: 77.4, max_lng: 77.8 };
    return (await client.get('/predict/heatmap', { params: p })).data;
  },
  demand: async (lat, lng) =>
    (await client.get('/predict/demand', { params: { latitude: lat, longitude: lng } })).data,
};

// ─── Jobs ─────────────────────────────────────────────────────────────────────
export const jobsApi = {
  status: async () => (await client.get('/jobs/status')).data,
  runs: async () => (await client.get('/jobs/runs')).data,
  runClustering: async () => (await client.post('/jobs/run/clustering')).data,
  runDemand: async () => (await client.post('/jobs/run/demand')).data,
  runRebalance: async () => (await client.post('/jobs/run/rebalance')).data,
  rebalanceSuggestions: async () => (await client.get('/jobs/rebalance-suggestions')).data,
  demandSnapshots: async () => (await client.get('/jobs/demand-snapshots')).data,
};

// ─── Bootstrap ────────────────────────────────────────────────────────────────
export const loadAppBootstrap = (clerkUserId) => {
  const existing = appBootstrapRequests.get(clerkUserId);
  if (existing) return existing;
  const request = Promise.all([
    authApi.getProfile(),
    ridesApi.getMyRides(),
    notificationsApi.list(),
  ]);
  appBootstrapRequests.set(clerkUserId, request);
  request.catch(() => {
    if (appBootstrapRequests.get(clerkUserId) === request)
      appBootstrapRequests.delete(clerkUserId);
  });
  return request;
};
export const clearAppBootstrap = (clerkUserId) => appBootstrapRequests.delete(clerkUserId);

// ─── WebSocket factory ────────────────────────────────────────────────────────
export const createTrackingWS = (token, onMessage, onClose) => {
  const ws = new WebSocket(`${WS_BASE_URL}/tracking/ws?token=${encodeURIComponent(token)}`);
  ws.onmessage = (e) => { try { onMessage(JSON.parse(e.data)); } catch (error) { void error; } };
  ws.onclose = () => onClose?.();
  ws.onerror = () => ws.close();
  return ws;
};
export const createNotificationsWS = (token, onMessage, onClose) => {
  const ws = new WebSocket(`${WS_BASE_URL}/notifications/ws?token=${encodeURIComponent(token)}`);
  ws.onmessage = (e) => { try { onMessage(JSON.parse(e.data)); } catch (error) { void error; } };
  ws.onclose = () => onClose?.();
  ws.onerror = () => ws.close();
  return ws;
};

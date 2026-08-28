import axios from 'axios';

let authTokenGetter = null;
const appBootstrapRequests = new Map();

export const setAuthTokenGetter = (getter) => { authTokenGetter = getter; };

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');
const WS_BASE_URL = API_BASE_URL.replace(/^http/, 'ws');

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
  createBatch: async (requests) => (await client.post('/rides/batch', { requests })).data,
  createDemoBatch: async (zone = 'indiranagar', demoRunId, locations = {}) => (await client.post('/rides/demo-batch', null, { params: {
    zone,
    ...(demoRunId ? { demo_run_id: demoRunId } : {}),
    ...(locations.pickup?.lat != null ? { pickup_lat: locations.pickup.lat, pickup_lng: locations.pickup.lng } : {}),
    ...(locations.destination?.lat != null ? { dest_lat: locations.destination.lat, dest_lng: locations.destination.lng } : {}),
    ...(locations.pickup?.label ? { pickup_label: locations.pickup.label } : {}),
    ...(locations.destination?.label ? { destination_label: locations.destination.label } : {}),
  } })).data,
  createDemoSharedBatch: async (riders, demoRunId) => (await client.post('/rides/demo-shared-batch', { demo_run_id: demoRunId, riders })).data,
  resetDemoRun: async (demoRunId) => (await client.delete(`/rides/demo-runs/${demoRunId}`)).data,
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
    return (await client.get('/geocode/suggest', { params: { query: corrected, ...(bias?.lat != null ? { lat: bias.lat, lng: bias.lng } : {}) } })).data;
  },
  search: async (query) => {
    const corrected = normaliseLocationQuery(query);
    const results = (await client.get('/geocode/search', { params: { query: corrected } })).data;
    if (!results.length) throw new Error('Location not found');
    return results[0];
  },
  reverse: async (lat, lng) => {
    return (await client.get('/geocode/reverse', { params: { lat, lng } })).data;
  },
  nearestRoad: async (lat, lng) => {
    return (await client.get('/routing/nearest-road', { params: { lat, lng } })).data;
  },
};

// ─── Routing / route validation ─────────────────────────────────────────────
export const routingApi = {
  route: async (from, to, { traffic = false } = {}) => {
    return (await client.get('/routing/route', { params: {
      from_lat: from.lat, from_lng: from.lng, to_lat: to.lat, to_lng: to.lng,
      traffic,
    } })).data;
  },
  matrix: async (sources, targets, costing) =>
    (await client.post('/routing/matrix', { sources, targets, costing })).data,
  mapMatch: async (locations) =>
    (await client.post('/routing/map-match', locations)).data,
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
  runAutoDispatch: async ({ mode = 'live', demoRunId } = {}) => (await client.post('/jobs/run/auto-dispatch', null, { params: { mode, ...(demoRunId ? { demo_run_id: demoRunId } : {}) } })).data,
  runClustering: async ({ mode = 'live', demoRunId } = {}) => (await client.post('/jobs/run/clustering', null, { params: { mode, ...(demoRunId ? { demo_run_id: demoRunId } : {}) } })).data,
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
  const ws = new WebSocket(`${WS_BASE_URL}/tracking/ws`, ['bearer', token]);
  ws.onmessage = (e) => { try { onMessage(JSON.parse(e.data)); } catch (error) { void error; } };
  ws.onclose = () => onClose?.();
  ws.onerror = () => ws.close();
  return ws;
};
export const createNotificationsWS = (token, onMessage, onClose) => {
  const ws = new WebSocket(`${WS_BASE_URL}/notifications/ws`, ['bearer', token]);
  ws.onmessage = (e) => { try { onMessage(JSON.parse(e.data)); } catch (error) { void error; } };
  ws.onclose = () => onClose?.();
  ws.onerror = () => ws.close();
  return ws;
};

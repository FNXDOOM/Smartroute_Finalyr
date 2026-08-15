import axios from 'axios';

let authTokenGetter = null;
const appBootstrapRequests = new Map();

export const setAuthTokenGetter = (getter) => { authTokenGetter = getter; };

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
const WS_BASE_URL = API_BASE_URL.replace(/^http/, 'ws');

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
  const ws = new WebSocket(`${WS_BASE_URL}/tracking/ws?token=${token}`);
  ws.onmessage = (e) => { try { onMessage(JSON.parse(e.data)); } catch {} };
  ws.onclose = () => onClose?.();
  ws.onerror = () => ws.close();
  return ws;
};
export const createNotificationsWS = (token, onMessage, onClose) => {
  const ws = new WebSocket(`${WS_BASE_URL}/notifications/ws?token=${token}`);
  ws.onmessage = (e) => { try { onMessage(JSON.parse(e.data)); } catch {} };
  ws.onclose = () => onClose?.();
  ws.onerror = () => ws.close();
  return ws;
};

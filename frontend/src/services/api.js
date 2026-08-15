import axios from 'axios';
let authTokenGetter = null;

export const setAuthTokenGetter = (getter) => {
  authTokenGetter = getter;
};

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const client = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 8000,
});

// Interceptor to attach JWT token
client.interceptors.request.use(
  async (config) => {
    const token = authTokenGetter ? await authTokenGetter() : null;
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

export const authApi = {
  getProfile: async () => {
    const res = await client.get('/auth/me');
    return res.data;
  },
  updateProfile: async (fields) => {
    const res = await client.patch('/auth/me', fields);
    return res.data;
  },
};

export const ridesApi = {
  createRideRequest: async (ridePayload) => (await client.post('/rides/request', ridePayload)).data,
  getMyRides: async () => { const data = (await client.get('/rides/my-rides')).data; return { rides: Array.isArray(data) ? data : (data.rides || []) }; },
  getAllRides: async (params = {}) => { const data = (await client.get('/rides/', { params })).data; return { rides: Array.isArray(data) ? data : (data.rides || []) }; },
  getRideVehicle: async (rideId) => (await client.get(`/rides/${rideId}/vehicle`)).data,
  updateStatus: async (rideId, status) => (await client.patch(`/rides/${rideId}/status`, { status })).data,
};

export const vehiclesApi = {
  list: async () => (await client.get('/vehicle/')).data,
  idle: async () => (await client.get('/vehicle/idle')).data,
};

export const notificationsApi = {
  list: async (params = {}) => (await client.get('/notifications/', { params })).data,
  markRead: async (id) => (await client.patch(`/notifications/${id}/read`)).data,
  markAllRead: async () => (await client.patch('/notifications/read-all')).data,
};

export const trackingApi = {
  getLiveFeed: async () => (await client.get('/tracking/feed')).data,
  getEvents: async () => (await client.get('/tracking/events')).data,
};

export const analyticsApi = {
  getOverview: async () => (await client.get('/analytics/overview')).data,
  getDaily: async (days = 7) => (await client.get('/analytics/daily', { params: { days } })).data,
};

export const predictApi = {
  getDemandHeatmap: async (bounds) => {
    const params = bounds || { min_lat: 12.8, max_lat: 13.1, min_lng: 77.4, max_lng: 77.8 };
    return (await client.get('/predict/heatmap', { params })).data;
  },
};

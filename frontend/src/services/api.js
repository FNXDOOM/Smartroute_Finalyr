import axios from 'axios';
import {
  MOCK_VEHICLES,
  MOCK_SMART_PICKUP_POINTS,
  MOCK_RIDE_OPTIONS,
  MOCK_TRIP_HISTORY,
  MOCK_ADMIN_METRICS,
  MOCK_DEMAND_HEATMAP_CELLS,
  MOCK_DAILY_ANALYTICS,
} from './mockData';

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
  (config) => {
    const token = localStorage.getItem('smartroute_token');
    if (token && !token.startsWith('mock_jwt_token_')) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

export const authApi = {
  login: async (credentials) => {
    try {
      const res = await client.post('/auth/login', credentials);
      return res.data;
    } catch (err) {
      throw err;
    }
  },
  register: async (userData) => {
    try {
      const res = await client.post('/auth/register', userData);
      return res.data;
    } catch (err) {
      throw err;
    }
  },
  getProfile: async () => {
    try {
      const res = await client.get('/auth/me');
      return res.data;
    } catch (err) {
      return null;
    }
  },
};

export const ridesApi = {
  createRideRequest: async (ridePayload) => {
    try {
      const res = await client.post('/rides/request', ridePayload);
      return res.data;
    } catch (err) {
      console.warn('Using fallback ride request confirmation');
      return {
        id: Math.floor(Math.random() * 90000) + 10000,
        status: 'clustered',
        pickup_lat: ridePayload.pickup_lat,
        pickup_lng: ridePayload.pickup_lng,
        dest_lat: ridePayload.dest_lat,
        dest_lng: ridePayload.dest_lng,
        ride_option_name: ridePayload.ride_option_name || 'Smart AI Pool',
        ride_option_price: ridePayload.ride_option_price || 140,
        request_time: new Date().toISOString(),
      };
    }
  },
  getMyRides: async () => {
    try {
      const res = await client.get('/rides/my-rides');
      return res.data;
    } catch (err) {
      return MOCK_TRIP_HISTORY;
    }
  },
};

export const predictApi = {
  getDemandHeatmap: async (bounds) => {
    try {
      const params = bounds
        ? bounds
        : { min_lat: 12.8, max_lat: 13.1, min_lng: 77.4, max_lng: 77.8 };
      const res = await client.get('/predict/heatmap', { params });
      return res.data;
    } catch (err) {
      return { cells: MOCK_DEMAND_HEATMAP_CELLS };
    }
  },
};

export const trackingApi = {
  getLiveFeed: async () => {
    try {
      const res = await client.get('/tracking/feed');
      return res.data;
    } catch (err) {
      return { vehicles: MOCK_VEHICLES, events: [] };
    }
  },
};

export const analyticsApi = {
  getOverview: async () => {
    try {
      const res = await client.get('/analytics/overview');
      return res.data;
    } catch (err) {
      return MOCK_ADMIN_METRICS;
    }
  },
  getDaily: async (days = 7) => {
    try {
      const res = await client.get('/analytics/daily', { params: { days } });
      return res.data;
    } catch (err) {
      return MOCK_DAILY_ANALYTICS;
    }
  },
};

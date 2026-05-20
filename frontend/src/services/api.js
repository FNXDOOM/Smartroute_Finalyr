import axios from 'axios';

// Create axios instance with base URL
const api = axios.create({
  baseURL: 'http://localhost:8000', // Assuming FastAPI default port is 8000
  headers: {
    'Content-Type': 'application/json',
  },
});

// Interceptor to add auth token if present
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export const authAPI = {
  login: (credentials) => api.post('/auth/login', credentials),
  register: (userData) => api.post('/auth/register', userData),
};

export const ridesAPI = {
  requestRide: (rideData) => api.post('/rides/request', rideData),
  checkStatus: (rideId) => api.get(`/rides/status?ride_id=${rideId}`),
};

export const clusterAPI = {
  triggerCluster: () => api.post('/cluster/create'),
};

export const routeAPI = {
  optimize: () => api.post('/route/optimize'),
};

export const predictAPI = {
  getDemand: (zoneId) => api.get(`/predict/demand${zoneId ? `?zone=${zoneId}` : ''}`),
};

export default api;

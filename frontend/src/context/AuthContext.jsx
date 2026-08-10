import React, { createContext, useState, useEffect } from 'react';
import { authApi } from '../services/api';

export const AuthContext = createContext({
  user: null,
  token: null,
  isAuthenticated: false,
  role: 'passenger', // passenger | driver | admin
  login: async () => {},
  signup: async () => {},
  logout: () => {},
  updateProfile: async () => {},
  loading: true,
});

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(() => {
    const savedUser = localStorage.getItem('smartroute_user');
    return savedUser ? JSON.parse(savedUser) : null;
  });

  const [token, setToken] = useState(() => {
    return localStorage.getItem('smartroute_token') || null;
  });

  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (token) {
      localStorage.setItem('smartroute_token', token);
    } else {
      localStorage.removeItem('smartroute_token');
    }
  }, [token]);

  useEffect(() => {
    if (user) {
      localStorage.setItem('smartroute_user', JSON.stringify(user));
    } else {
      localStorage.removeItem('smartroute_user');
    }
  }, [user]);

  const login = async (email, password) => {
    setLoading(true);
    try {
      // Try backend API first
      const res = await authApi.login({ email, password });
      if (res && res.access_token) {
        setToken(res.access_token);
        setUser(res.user);
        setLoading(false);
        return { success: true, user: res.user };
      }
    } catch (err) {
      console.warn('Backend login failed, using interactive demo session:', err);
    }

    // Demo/Mock Fallback if backend is unavailable or for testing
    let simulatedRole = 'passenger';
    if (email.includes('driver')) simulatedRole = 'driver';
    if (email.includes('admin')) simulatedRole = 'admin';

    const mockUser = {
      id: Math.floor(Math.random() * 1000) + 1,
      name: email.split('@')[0].replace('.', ' ').toUpperCase() || 'Smart Rider',
      email: email,
      role: simulatedRole,
      phone: '+91 98765 43210',
      avatar: 'https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?auto=format&fit=crop&w=150&q=80',
    };
    const mockToken = 'mock_jwt_token_' + Date.now();

    setToken(mockToken);
    setUser(mockUser);
    setLoading(false);
    return { success: true, user: mockUser };
  };

  const signup = async (userData) => {
    setLoading(true);
    try {
      const res = await authApi.register({
        name: userData.name,
        email: userData.email,
        password: userData.password,
        role: userData.role || 'passenger',
      });
      if (res) {
        // Auto login after registration
        return await login(userData.email, userData.password);
      }
    } catch (err) {
      console.warn('Backend signup failed, proceeding with demo account:', err);
    }

    const mockUser = {
      id: Math.floor(Math.random() * 1000) + 1,
      name: userData.name,
      email: userData.email,
      role: userData.role || 'passenger',
      phone: userData.phone || '+91 98765 43210',
    };
    const mockToken = 'mock_jwt_token_' + Date.now();

    setToken(mockToken);
    setUser(mockUser);
    setLoading(false);
    return { success: true, user: mockUser };
  };

  const logout = () => {
    setUser(null);
    setToken(null);
    localStorage.removeItem('smartroute_user');
    localStorage.removeItem('smartroute_token');
  };

  const updateProfile = async (updatedFields) => {
    setUser((prev) => ({ ...prev, ...updatedFields }));
    return { success: true };
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isAuthenticated: !!user,
        role: user?.role || 'passenger',
        login,
        signup,
        logout,
        updateProfile,
        loading,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

import React, { useContext } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { AuthContext } from '../../context/AuthContext';

export const RoleGuard = ({ allowedRoles = [], children }) => {
  const { isAuthenticated, role, loading } = useContext(AuthContext);
  const location = useLocation();

  if (loading) {
    return null; // Or skeleton fallback
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  if (allowedRoles.length > 0 && !allowedRoles.includes(role)) {
    // Redirect to proper role dashboard
    if (role === 'driver') return <Navigate to="/driver-dashboard" replace />;
    if (role === 'admin') return <Navigate to="/admin-dashboard" replace />;
    return <Navigate to="/rider-dashboard" replace />;
  }

  return children;
};

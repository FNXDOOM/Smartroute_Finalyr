import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { ColorModeProvider } from './context/ColorModeContext';
import { AuthProvider } from './context/AuthContext';
import { RoleGuard } from './components/common/RoleGuard';

// Public Pages
import { Home } from './pages/Home';
import { About } from './pages/About';
import { Features } from './pages/Features';
import { HowItWorks } from './pages/HowItWorks';
import { Pricing } from './pages/Pricing';
import { Contact } from './pages/Contact';

// Auth Pages
import { Login } from './pages/auth/Login';
import { SignUp } from './pages/auth/SignUp';
import { OTPVerification } from './pages/auth/OTPVerification';
import { ForgotPassword } from './pages/auth/ForgotPassword';

// Rider Dashboard
import { RiderOverview } from './pages/RiderDashboard/RiderOverview';
import { TripHistory } from './pages/RiderDashboard/TripHistory';
import { PaymentMethods } from './pages/RiderDashboard/PaymentMethods';
import { Notifications } from './pages/RiderDashboard/Notifications';
import { ProfileSettings } from './pages/RiderDashboard/ProfileSettings';

// Driver Dashboard
import { DriverOverview } from './pages/DriverDashboard/DriverOverview';
import { Earnings } from './pages/DriverDashboard/Earnings';
import { Performance } from './pages/DriverDashboard/Performance';

// Admin Dashboard
import { AdminOverview } from './pages/AdminDashboard/AdminOverview';
import { FleetMap } from './pages/AdminDashboard/FleetMap';
import { Analytics } from './pages/AdminDashboard/Analytics';
import { UserManagement } from './pages/AdminDashboard/UserManagement';

import './theme/glassmorphism.css';

export default function App() {
  return (
    <ColorModeProvider>
      <AuthProvider>
        <Router>
          <Routes>
            {/* Public Routes */}
            <Route path="/" element={<Home />} />
            <Route path="/about" element={<About />} />
            <Route path="/features" element={<Features />} />
            <Route path="/how-it-works" element={<HowItWorks />} />
            <Route path="/pricing" element={<Pricing />} />
            <Route path="/contact" element={<Contact />} />

            {/* Auth Routes */}
            <Route path="/login" element={<Login />} />
            <Route path="/signup" element={<SignUp />} />
            <Route path="/otp-verify" element={<OTPVerification />} />
            <Route path="/forgot-password" element={<ForgotPassword />} />

            {/* Rider Dashboard Routes */}
            <Route path="/rider-dashboard" element={<RiderOverview />} />
            <Route path="/rider-dashboard/history" element={<TripHistory />} />
            <Route path="/rider-dashboard/payments" element={<PaymentMethods />} />
            <Route path="/rider-dashboard/notifications" element={<Notifications />} />
            <Route path="/rider-dashboard/profile" element={<ProfileSettings />} />

            {/* Driver Dashboard Routes */}
            <Route path="/driver-dashboard" element={<DriverOverview />} />
            <Route path="/driver-dashboard/earnings" element={<Earnings />} />
            <Route path="/driver-dashboard/performance" element={<Performance />} />

            {/* Admin Dashboard Routes */}
            <Route path="/admin-dashboard" element={<AdminOverview />} />
            <Route path="/admin-dashboard/fleet" element={<FleetMap />} />
            <Route path="/admin-dashboard/analytics" element={<Analytics />} />
            <Route path="/admin-dashboard/users" element={<UserManagement />} />

            {/* Fallback */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Router>
      </AuthProvider>
    </ColorModeProvider>
  );
}

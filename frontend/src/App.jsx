import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { ColorModeProvider } from './context/ColorModeContext';
import { AuthProvider } from './context/AuthContext';

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
import { RoleGuard } from './components/common/RoleGuard';

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

            {/* Rider Dashboard Routes */}
            <Route path="/rider-dashboard" element={<RoleGuard allowedRoles={['passenger']}><RiderOverview /></RoleGuard>} />
            <Route path="/rider-dashboard/history" element={<RoleGuard allowedRoles={['passenger']}><TripHistory /></RoleGuard>} />
            <Route path="/rider-dashboard/payments" element={<RoleGuard allowedRoles={['passenger']}><PaymentMethods /></RoleGuard>} />
            <Route path="/rider-dashboard/notifications" element={<RoleGuard allowedRoles={['passenger']}><Notifications /></RoleGuard>} />
            <Route path="/rider-dashboard/profile" element={<RoleGuard allowedRoles={['passenger']}><ProfileSettings /></RoleGuard>} />

            {/* Driver Dashboard Routes */}
            <Route path="/driver-dashboard" element={<RoleGuard allowedRoles={['driver']}><DriverOverview /></RoleGuard>} />
            <Route path="/driver-dashboard/earnings" element={<RoleGuard allowedRoles={['driver']}><Earnings /></RoleGuard>} />
            <Route path="/driver-dashboard/performance" element={<RoleGuard allowedRoles={['driver']}><Performance /></RoleGuard>} />

            {/* Admin Dashboard Routes */}
            <Route path="/admin-dashboard" element={<RoleGuard allowedRoles={['admin']}><AdminOverview /></RoleGuard>} />
            <Route path="/admin-dashboard/fleet" element={<RoleGuard allowedRoles={['admin']}><FleetMap /></RoleGuard>} />
            <Route path="/admin-dashboard/analytics" element={<RoleGuard allowedRoles={['admin']}><Analytics /></RoleGuard>} />
            <Route path="/admin-dashboard/users" element={<RoleGuard allowedRoles={['admin']}><UserManagement /></RoleGuard>} />

            {/* Fallback */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Router>
      </AuthProvider>
    </ColorModeProvider>
  );
}

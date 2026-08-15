import React, { useState } from 'react';
import { LogOut, LayoutDashboard, Settings } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import MapView from '../components/MapView';
import RideBooking from '../components/RideBooking';

import { useVehicleTracking } from '../hooks/useVehicleTracking';

const Dashboard = () => {
  const navigate = useNavigate();
  const [virtualStops, setVirtualStops] = useState([]);
  const [routes, setRoutes] = useState([]);
  const [userLocation, setUserLocation] = useState(null);
  const [destinationLocation, setDestinationLocation] = useState(null);
  const { vehicles } = useVehicleTracking();



  const handleLogout = () => {
    localStorage.removeItem('token');
    navigate('/');
  };

  const handleRideRequested = (payload) => {
    console.log("Ride requested", payload);
    setUserLocation([payload.pickup_lat, payload.pickup_lng]);
    setDestinationLocation([payload.dest_lat, payload.dest_lng]);
  };

  const triggerOptimization = async () => {
    try {
      if (userLocation && destinationLocation) {
        setRoutes([{
          path: [
            { lat: userLocation[0], lng: userLocation[1] },
            { lat: destinationLocation[0], lng: destinationLocation[1] }
          ]
        }]);
      } else {
        alert("Please enter a pickup and destination first.");
      }
    } catch (error) {
      console.error("Optimization failed", error);
    }
  };

  return (
    <div style={{ height: '100vh', width: '100vw', display: 'flex', overflow: 'hidden' }}>
      
      {/* Sidebar Navigation */}
      <aside className="glass-panel" style={{ width: '80px', height: '100%', borderRadius: 0, borderTop: 'none', borderBottom: 'none', borderLeft: 'none', display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '1.5rem 0', zIndex: 20 }}>
        <div style={{ width: '40px', height: '40px', borderRadius: '10px', background: 'var(--primary)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: '2rem' }}>
          <span className="font-bold">SR</span>
        </div>
        
        <nav style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', flex: 1 }}>
          <button className="btn" style={{ padding: '0.5rem', background: 'rgba(255,255,255,0.1)', color: 'var(--primary)', borderRadius: '10px' }}>
            <LayoutDashboard size={24} />
          </button>
          <button className="btn" style={{ padding: '0.5rem', background: 'transparent', color: 'var(--text-secondary)' }} onClick={triggerOptimization} title="Run Optimization Engine">
            <Settings size={24} />
          </button>
        </nav>

        <button className="btn" onClick={handleLogout} style={{ padding: '0.5rem', background: 'transparent', color: 'var(--text-secondary)' }}>
          <LogOut size={24} />
        </button>
      </aside>

      {/* Main Content Area */}
      <main style={{ flex: 1, position: 'relative' }}>
        <MapView 
          virtualStops={virtualStops} 
          routes={routes} 
          userLocation={userLocation} 
          destinationLocation={destinationLocation} 
          vehicles={vehicles} 
        />
        <RideBooking onRideRequested={handleRideRequested} onLocationFound={setUserLocation} />
      </main>

    </div>
  );
};

export default Dashboard;

import React, { useState, useEffect } from 'react';
import { LogOut, LayoutDashboard, Settings } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import MapView from '../components/MapView';
import RideBooking from '../components/RideBooking';
import { clusterAPI, routeAPI } from '../services/api';

const Dashboard = () => {
  const navigate = useNavigate();
  const [virtualStops, setVirtualStops] = useState([]);
  const [routes, setRoutes] = useState([]);

  // Mock data simulation for MVP demonstration
  useEffect(() => {
    // In a real app, this would be fetched from backend or WebSockets
    const mockStops = [
      { lat: 40.7128, lng: -74.0060, cluster_id: 1 },
      { lat: 40.7306, lng: -73.9352, cluster_id: 2 }
    ];
    setVirtualStops(mockStops);
  }, []);

  const handleLogout = () => {
    localStorage.removeItem('token');
    navigate('/');
  };

  const handleRideRequested = (payload) => {
    console.log("Ride requested", payload);
    // You could trigger clustering or refresh data here
  };

  const triggerOptimization = async () => {
    try {
      // await clusterAPI.triggerCluster();
      // await routeAPI.optimize();
      alert("Triggering backend optimization pipeline...");
      
      // Mock result
      setRoutes([
        { path: [{lat: 40.7128, lng: -74.0060}, {lat: 40.7306, lng: -73.9352}] }
      ]);
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
        <MapView virtualStops={virtualStops} routes={routes} />
        <RideBooking onRideRequested={handleRideRequested} />
      </main>

    </div>
  );
};

export default Dashboard;

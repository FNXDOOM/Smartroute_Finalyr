import React from 'react';
import { Link } from 'react-router-dom';
import { Route, MapPin, Zap, Compass } from 'lucide-react';
import '../index.css';

const Home = () => {
  return (
    <div className="home-page min-h-screen">
      {/* Navbar */}
      <nav className="glass-panel" style={{ padding: '1rem 2rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderRadius: 0, borderTop: 'none', borderLeft: 'none', borderRight: 'none', borderBottom: '1px solid var(--border-color)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Compass className="text-primary" size={32} />
          <span className="font-bold text-xl tracking-tight">Smart<span className="text-gradient">Route</span>AI</span>
        </div>
        <div style={{ display: 'flex', gap: '1rem' }}>
          <Link to="/login" className="btn btn-outline">Log In</Link>
          <Link to="/dashboard" className="btn btn-primary">Try App</Link>
        </div>
      </nav>

      {/* Hero Section */}
      <header className="container" style={{ paddingTop: '8rem', paddingBottom: '8rem', textAlign: 'center' }}>
        <h1 className="animate-fade-in" style={{ fontSize: '4rem', fontWeight: '700', lineHeight: 1.1, marginBottom: '1.5rem' }}>
          Optimize Shared Mobility <br />
          with <span className="text-gradient">Intelligent Routing</span>
        </h1>
        <p className="text-secondary animate-fade-in" style={{ fontSize: '1.25rem', maxWidth: '600px', margin: '0 auto 3rem auto', animationDelay: '0.1s' }}>
          Experience the future of urban transit. SmartRouteAI dynamically groups passengers, generates virtual stops, and optimizes multi-vehicle routes on real road networks.
        </p>
        <div className="animate-fade-in" style={{ display: 'flex', gap: '1rem', justifyContent: 'center', animationDelay: '0.2s' }}>
          <Link to="/dashboard" className="btn btn-primary" style={{ padding: '1rem 2rem', fontSize: '1.125rem' }}>
            Enter Dashboard <Route size={20} />
          </Link>
        </div>
      </header>

      {/* Features Grid */}
      <section className="container" style={{ paddingBottom: '6rem' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '2rem' }}>
          
          <div className="glass-panel" style={{ padding: '2rem' }}>
            <div style={{ width: '48px', height: '48px', borderRadius: '12px', background: 'rgba(14, 165, 233, 0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: '1rem', color: 'var(--primary)' }}>
              <Zap size={24} />
            </div>
            <h3 className="font-bold text-lg" style={{ marginBottom: '0.5rem' }}>Dynamic Clustering</h3>
            <p className="text-secondary">Uses H3 indexing and HDBSCAN to match nearby passengers in real-time.</p>
          </div>

          <div className="glass-panel" style={{ padding: '2rem' }}>
            <div style={{ width: '48px', height: '48px', borderRadius: '12px', background: 'rgba(139, 92, 246, 0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: '1rem', color: 'var(--accent)' }}>
              <MapPin size={24} />
            </div>
            <h3 className="font-bold text-lg" style={{ marginBottom: '0.5rem' }}>Virtual Stops</h3>
            <p className="text-secondary">Generates intelligent pick-up locations using K-Medoids snapped to OpenStreetMap.</p>
          </div>

          <div className="glass-panel" style={{ padding: '2rem' }}>
            <div style={{ width: '48px', height: '48px', borderRadius: '12px', background: 'rgba(16, 185, 129, 0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: '1rem', color: 'var(--success)' }}>
              <Route size={24} />
            </div>
            <h3 className="font-bold text-lg" style={{ marginBottom: '0.5rem' }}>VRP Optimization</h3>
            <p className="text-secondary">Leverages Google OR-Tools to solve complex vehicle routing problems efficiently.</p>
          </div>

        </div>
      </section>
    </div>
  );
};

export default Home;

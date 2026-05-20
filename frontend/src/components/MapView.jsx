import React, { useState } from 'react';
import { MapContainer, TileLayer, Marker, Popup, Polyline } from 'react-leaflet';

const MapView = ({ virtualStops = [], routes = [], userLocation = null }) => {
  // Center of the map (defaults to a central point if no location)
  const defaultCenter = [40.7128, -74.0060]; // e.g., NYC coordinates
  const center = userLocation || defaultCenter;

  return (
    <div style={{ height: '100%', width: '100%', position: 'absolute', top: 0, left: 0, zIndex: 0 }}>
      <MapContainer 
        center={center} 
        zoom={13} 
        style={{ height: '100%', width: '100%' }}
        zoomControl={false}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
        />
        
        {/* Render Virtual Stops */}
        {virtualStops.map((stop, idx) => (
          <Marker key={`stop-${idx}`} position={[stop.lat, stop.lng]}>
            <Popup>
              <div style={{ color: '#000' }}>
                <strong>Virtual Stop</strong><br />
                Cluster ID: {stop.cluster_id}
              </div>
            </Popup>
          </Marker>
        ))}

        {/* Render Optimized Routes */}
        {routes.map((route, idx) => (
          <Polyline 
            key={`route-${idx}`} 
            positions={route.path.map(p => [p.lat, p.lng])} 
            color="var(--primary)" 
            weight={5} 
            opacity={0.8} 
          />
        ))}

      </MapContainer>
    </div>
  );
};

export default MapView;

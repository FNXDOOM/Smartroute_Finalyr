import React, { useEffect } from 'react';
import { MapContainer, TileLayer, Marker, Popup, Polyline, useMap } from 'react-leaflet';

// Fit the map to show both pickup and destination when both exist
const MapFitter = ({ userLocation, destinationLocation }) => {
  const map = useMap();
  useEffect(() => {
    if (userLocation && destinationLocation) {
      map.fitBounds([userLocation, destinationLocation], { padding: [60, 60] });
    } else if (userLocation) {
      map.flyTo(userLocation, 14);
    }
  }, [userLocation, destinationLocation, map]);
  return null;
};

const MapView = ({ virtualStops = [], routes = [], userLocation = null, destinationLocation = null, vehicles = [] }) => {
  const defaultCenter = [20.5937, 78.9629]; // Center of India as neutral default
  const center = userLocation || defaultCenter;

  return (
    <div style={{ height: '100%', width: '100%', position: 'absolute', top: 0, left: 0, zIndex: 0 }}>
      <MapContainer
        center={center}
        zoom={userLocation ? 14 : 5}
        style={{ height: '100%', width: '100%' }}
        zoomControl={false}
      >
        <MapFitter userLocation={userLocation} destinationLocation={destinationLocation} />
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
        />

        {/* Render Pickup Location */}
        {userLocation && (
          <Marker position={userLocation}>
            <Popup>
              <div style={{ color: '#000' }}>
                <strong>📍 Pickup Location</strong>
              </div>
            </Popup>
          </Marker>
        )}

        {/* Render Destination Location */}
        {destinationLocation && (
          <Marker position={destinationLocation}>
            <Popup>
              <div style={{ color: '#000' }}>
                <strong>🏁 Destination</strong>
              </div>
            </Popup>
          </Marker>
        )}

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

        {/* Render GPS-tracked Vehicles */}
        {vehicles.map((vehicle, idx) => (
          <Marker key={`vehicle-${vehicle.id || idx}`} position={[vehicle.lat, vehicle.lng]}>
            <Popup>
              <div style={{ color: '#000' }}>
                <strong>🚐 Vehicle {vehicle.id}</strong><br />
                Active on route
              </div>
            </Popup>
          </Marker>
        ))}

        {/* Render Optimized Routes — use explicit hex color, CSS vars don't work in Leaflet SVG */}
        {routes.map((route, idx) => (
          <Polyline
            key={`route-${idx}`}
            positions={route.path.map((p) => [p.lat, p.lng])}
            color="#0ea5e9"
            weight={5}
            opacity={0.85}
          />
        ))}

      </MapContainer>
    </div>
  );
};

export default MapView;

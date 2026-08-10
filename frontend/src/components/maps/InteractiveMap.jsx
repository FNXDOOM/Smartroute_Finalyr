import React, { useState, useEffect, useRef } from 'react';
import { Box, Typography, Button, IconButton, Chip } from '@mui/material';
import { GoogleMap, useJsApiLoader, Marker, Polyline, InfoWindow } from '@react-google-maps/api';
import { Car, MapPin, Navigation, Layers, Compass, Zap } from 'lucide-react';
import { MapMarker } from '../common/MapMarker';
import { MOCK_VEHICLES, MOCK_SMART_PICKUP_POINTS, MOCK_DEMAND_HEATMAP_CELLS } from '../../services/mockData';

const DEFAULT_CENTER = { lat: 12.9716, lng: 77.5946 }; // Bengaluru CBD default

export const InteractiveMap = ({
  vehicles = MOCK_VEHICLES,
  pickupPoint = null,
  destinationPoint = null,
  smartPickupPoints = MOCK_SMART_PICKUP_POINTS,
  heatmapMode = false,
  heatmapCells = MOCK_DEMAND_HEATMAP_CELLS,
  height = '100%',
  onSelectLocation,
}) => {
  const apiKey = import.meta.env.VITE_GOOGLE_MAPS_API_KEY;
  const { isLoaded } = useJsApiLoader({
    id: 'google-map-script',
    googleMapsApiKey: apiKey || '',
  });

  const [selectedMarker, setSelectedMarker] = useState(null);
  const [animatedVehicles, setAnimatedVehicles] = useState(vehicles);

  // Simulated live vehicle drift animation for realistic feedback
  useEffect(() => {
    const interval = setInterval(() => {
      setAnimatedVehicles((prev) =>
        prev.map((v) => ({
          ...v,
          lat: v.lat + (Math.random() - 0.5) * 0.0008,
          lng: v.lng + (Math.random() - 0.5) * 0.0008,
        }))
      );
    }, 2500);
    return () => clearInterval(interval);
  }, []);

  // Polyline path sample
  const routePolyline = [
    { lat: pickupPoint?.lat || 12.9784, lng: pickupPoint?.lng || 77.6408 },
    { lat: 12.965, lng: 77.63 },
    { lat: 12.95, lng: 77.61 },
    { lat: destinationPoint?.lat || 12.9352, lng: destinationPoint?.lng || 77.6245 },
  ];

  // If Google Maps API key is loaded, render Google Maps
  if (apiKey && isLoaded) {
    return (
      <Box sx={{ width: '100%', height, minHeight: 400, borderRadius: 4, overflow: 'hidden', position: 'relative' }}>
        <GoogleMap
          mapContainerStyle={{ width: '100%', height: '100%' }}
          center={pickupPoint || DEFAULT_CENTER}
          zoom={13}
          options={{
            disableDefaultUI: false,
            zoomControl: true,
            styles: [
              { elementType: 'geometry', stylers: [{ color: '#121620' }] },
              { elementType: 'labels.text.stroke', stylers: [{ color: '#121620' }] },
              { elementType: 'labels.text.fill', stylers: [{ color: '#746855' }] },
              { featureType: 'administrative.locality', elementType: 'labels.text.fill', stylers: [{ color: '#00D4FF' }] },
              { featureType: 'poi', elementType: 'labels.text.fill', stylers: [{ color: '#1E88E5' }] },
              { featureType: 'road', elementType: 'geometry', stylers: [{ color: '#1E293B' }] },
              { featureType: 'road', elementType: 'geometry.stroke', stylers: [{ color: '#0B1F3A' }] },
              { featureType: 'water', elementType: 'geometry', stylers: [{ color: '#0B1F3A' }] },
            ],
          }}
        >
          {/* Vehicles */}
          {animatedVehicles.map((v) => (
            <Marker
              key={v.id}
              position={{ lat: v.lat, lng: v.lng }}
              onClick={() => setSelectedMarker(v)}
            />
          ))}

          {/* Polyline */}
          <Polyline
            path={routePolyline}
            options={{
              strokeColor: '#00D4FF',
              strokeOpacity: 0.9,
              strokeWeight: 4,
            }}
          />

          {selectedMarker && (
            <InfoWindow position={{ lat: selectedMarker.lat, lng: selectedMarker.lng }} onCloseClick={() => setSelectedMarker(null)}>
              <Box sx={{ color: '#0B1F3A' }}>
                <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                  {selectedMarker.vehicle_model}
                </Typography>
                <Typography variant="caption">Driver: {selectedMarker.driver_name} ({selectedMarker.driver_rating}★)</Typography>
              </Box>
            </InfoWindow>
          )}
        </GoogleMap>
      </Box>
    );
  }

  // Interactive Fallback Simulated Map Canvas
  return (
    <Box
      sx={{
        width: '100%',
        height,
        minHeight: 420,
        borderRadius: 4,
        position: 'relative',
        overflow: 'hidden',
        background: 'linear-gradient(135deg, #0B1F3A 0%, #121622 100%)',
        border: '1px solid rgba(0, 212, 255, 0.2)',
        boxShadow: '0 8px 32px rgba(0, 0, 0, 0.5)',
      }}
    >
      {/* Grid Pattern overlay */}
      <Box className="hero-grid-bg" sx={{ position: 'absolute', inset: 0, opacity: 0.6 }} />

      {/* Simulated Map Roads Canvas */}
      <svg
        style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          <linearGradient id="routeGlow" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#1E88E5" />
            <stop offset="100%" stopColor="#00D4FF" />
          </linearGradient>
          <filter id="glow">
            <feGaussianBlur stdDeviation="3" result="coloredBlur" />
            <feMerge>
              <feMergeNode in="coloredBlur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Major roads lines */}
        <path d="M 50 100 Q 200 150 400 120 T 700 300" fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="12" />
        <path d="M 120 400 Q 300 200 600 350" fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="10" />

        {/* AI Calculated Route Polyline with Glow */}
        <path
          d="M 150 180 C 250 120, 350 260, 520 280"
          fill="none"
          stroke="url(#routeGlow)"
          strokeWidth="5"
          strokeDasharray="8 4"
          filter="url(#glow)"
        />

        {/* Simulated Heatmap Zones if enabled */}
        {heatmapMode &&
          heatmapCells.map((cell, idx) => (
            <circle
              key={idx}
              cx={180 + idx * 90}
              cy={140 + (idx % 3) * 70}
              r={35 + cell.demandScore / 3}
              fill="rgba(0, 212, 255, 0.25)"
              stroke="#00D4FF"
              strokeWidth="1.5"
            />
          ))}
      </svg>

      {/* Floating Map Controls overlay */}
      <Box
        sx={{
          position: 'absolute',
          top: 16,
          left: 16,
          display: 'flex',
          gap: 1,
          alignItems: 'center',
          background: 'rgba(11, 31, 58, 0.85)',
          backdropFilter: 'blur(12px)',
          border: '1px solid rgba(0, 212, 255, 0.3)',
          borderRadius: 3,
          px: 2,
          py: 1,
          zIndex: 5,
        }}
      >
        <Zap size={18} color="#00D4FF" />
        <Typography variant="caption" sx={{ color: '#00D4FF', fontWeight: 700 }}>
          {heatmapMode ? 'AI DEMAND HEATMAP ACTIVE' : 'LIVE AI TELEMETRY SIMULATOR'}
        </Typography>
        <Chip label="ONLINE" size="small" color="success" sx={{ height: 20, fontSize: '0.65rem' }} />
      </Box>

      {/* Vehicle Markers */}
      {animatedVehicles.map((v, i) => (
        <Box
          key={v.id}
          sx={{
            position: 'absolute',
            top: `${25 + (i * 18) % 60}%`,
            left: `${20 + (i * 22) % 70}%`,
            zIndex: 6,
          }}
        >
          <MapMarker
            type="vehicle"
            title={`${v.vehicle_model} — ${v.driver_name}`}
            speed={v.speed}
            onClick={() => setSelectedMarker(v)}
          />
        </Box>
      ))}

      {/* Smart Pickup Pins */}
      {smartPickupPoints.map((sp, idx) => (
        <Box
          key={sp.id}
          sx={{
            position: 'absolute',
            top: `${30 + idx * 25}%`,
            left: `${35 + idx * 30}%`,
            zIndex: 7,
          }}
        >
          <MapMarker type="stop" title={sp.name} />
        </Box>
      ))}

      {/* Floating info banner when marker clicked */}
      {selectedMarker && (
        <Box
          sx={{
            position: 'absolute',
            bottom: 20,
            left: 20,
            right: 20,
            background: 'rgba(26, 35, 50, 0.95)',
            backdropFilter: 'blur(16px)',
            border: '1px solid #00D4FF',
            borderRadius: 3,
            p: 2,
            zIndex: 10,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <Box
              sx={{
                width: 42,
                height: 42,
                borderRadius: '50%',
                background: 'linear-gradient(135deg, #1E88E5 0%, #00D4FF 100%)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Car color="#FFFFFF" size={22} />
            </Box>
            <Box>
              <Typography variant="subtitle2" sx={{ color: '#FFFFFF', fontWeight: 700 }}>
                {selectedMarker.vehicle_model} ({selectedMarker.license_plate})
              </Typography>
              <Typography variant="caption" sx={{ color: '#00D4FF' }}>
                Driver: {selectedMarker.driver_name} • {selectedMarker.driver_rating}★ • {selectedMarker.battery}% Battery
              </Typography>
            </Box>
          </Box>
          <Button size="small" variant="outlined" onClick={() => setSelectedMarker(null)}>
            Close
          </Button>
        </Box>
      )}
    </Box>
  );
};

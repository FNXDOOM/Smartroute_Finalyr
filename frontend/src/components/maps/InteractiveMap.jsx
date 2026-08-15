import React, { useEffect } from 'react';
import { Box, Chip, Typography } from '@mui/material';
import { MapContainer, TileLayer, Marker, Popup, Polyline, Circle, useMap } from 'react-leaflet';
import { Zap } from 'lucide-react';

const DEFAULT_CENTER = [12.9716, 77.5946];

const MapViewport = ({ pickupPoint, destinationPoint, vehicles }) => {
  const map = useMap();
  useEffect(() => {
    const points = [pickupPoint, destinationPoint, ...(vehicles || []).map((v) => v.lat != null && v.lng != null ? { lat: v.lat, lng: v.lng } : null)].filter(Boolean).map((p) => [p.lat, p.lng]);
    if (points.length > 1) map.fitBounds(points, { padding: [40, 40] });
    else if (points.length === 1) map.setView(points[0], 13);
  }, [map, pickupPoint, destinationPoint, vehicles]);
  return null;
};

export const InteractiveMap = ({
  vehicles = [], pickupPoint = null, destinationPoint = null,
  smartPickupPoints = [], heatmapMode = false, heatmapCells = [], height = '100%',
}) => {
  const validVehicles = vehicles.filter((v) => v.lat != null && v.lng != null);
  const route = [pickupPoint, destinationPoint].filter(Boolean).map((p) => [p.lat, p.lng]);
  const center = pickupPoint ? [pickupPoint.lat, pickupPoint.lng] : DEFAULT_CENTER;

  return <Box sx={{ width: '100%', height, minHeight: 420, borderRadius: 4, overflow: 'hidden', position: 'relative' }}>
    <MapContainer center={center} zoom={13} style={{ width: '100%', height: '100%' }}>
      <MapViewport pickupPoint={pickupPoint} destinationPoint={destinationPoint} vehicles={validVehicles} />
      <TileLayer attribution='&copy; OpenStreetMap contributors &copy; CARTO' url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png" />
      {route.length > 1 && <Polyline positions={route} pathOptions={{ color: '#00D4FF', weight: 5 }} />}
      {pickupPoint && <Marker position={[pickupPoint.lat, pickupPoint.lng]}><Popup>Pickup location</Popup></Marker>}
      {destinationPoint && <Marker position={[destinationPoint.lat, destinationPoint.lng]}><Popup>Destination</Popup></Marker>}
      {validVehicles.map((v) => <Marker key={v.id} position={[v.lat, v.lng]}><Popup><strong>{v.license_plate || `Vehicle ${v.id}`}</strong><br />Status: {v.status}</Popup></Marker>)}
      {smartPickupPoints.filter((p) => p.lat != null && p.lng != null).map((p) => <Marker key={p.id} position={[p.lat, p.lng]}><Popup>{p.name || 'Smart pickup point'}</Popup></Marker>)}
      {heatmapMode && heatmapCells.filter((c) => c.latitude != null && c.longitude != null).map((c, i) => <Circle key={c.h3_index || i} center={[c.latitude, c.longitude]} radius={Math.max(80, (c.predicted_demand || c.demandScore || 1) * 25)} pathOptions={{ color: '#00D4FF', fillColor: '#00D4FF', fillOpacity: 0.2 }} />)}
    </MapContainer>
    <Box sx={{ position: 'absolute', top: 16, left: 16, zIndex: 1000, display: 'flex', gap: 1, alignItems: 'center', background: 'rgba(11,31,58,.88)', px: 2, py: 1, borderRadius: 3 }}><Zap size={18} color="#00D4FF" /><Typography variant="caption" sx={{ color: '#00D4FF', fontWeight: 700 }}>{heatmapMode ? 'AI DEMAND HEATMAP' : 'LIVE OPENSTREETMAP TELEMETRY'}</Typography><Chip label="ONLINE" size="small" color="success" sx={{ height: 20, fontSize: '.65rem' }} /></Box>
  </Box>;
};

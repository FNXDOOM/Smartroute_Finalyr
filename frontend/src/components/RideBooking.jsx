import React, { useState } from 'react';
import { MapPin, Navigation, Clock, User, LocateFixed } from 'lucide-react';

// Regex to detect raw "lat, lng" coordinate strings (e.g. "12.9716, 77.5946")
const COORD_REGEX = /^-?\d+(\.\d+)?\s*,\s*-?\d+(\.\d+)?$/;

const RideBooking = ({ onRideRequested, onLocationFound }) => {
  const [pickup, setPickup] = useState('');
  const [destination, setDestination] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isLocating, setIsLocating] = useState(false);
  const [statusMsg, setStatusMsg] = useState('Dynamic matching in progress...');

  const fetchLocation = () => {
    if (!navigator.geolocation) {
      alert('Geolocation is not supported by your browser');
      return;
    }
    setIsLocating(true);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const lat = position.coords.latitude.toFixed(6);
        const lng = position.coords.longitude.toFixed(6);
        setPickup(`${lat}, ${lng}`);
        if (onLocationFound) {
          onLocationFound([parseFloat(lat), parseFloat(lng)]);
        }
        setIsLocating(false);
      },
      (error) => {
        console.error('Error fetching location:', error);
        alert('Unable to retrieve your location. Please check browser permissions.');
        setIsLocating(false);
      }
    );
  };

  // Geocode a human-readable address using Nominatim
  const geocode = async (address) => {
    const res = await fetch(
      `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(address)}&limit=1`,
      { headers: { 'Accept-Language': 'en' } }
    );
    const data = await res.json();
    if (data && data.length > 0) {
      return { lat: parseFloat(data[0].lat), lon: parseFloat(data[0].lon) };
    }
    return null;
  };

  // Parse either a "lat, lng" string or geocode an address
  const resolveCoords = async (input) => {
    if (COORD_REGEX.test(input.trim())) {
      const [lat, lng] = input.split(',').map((s) => parseFloat(s.trim()));
      return { lat, lon: lng };
    }
    return geocode(input.trim());
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!pickup.trim() || !destination.trim()) {
      alert('Please fill in both pickup and destination.');
      return;
    }
    setIsSubmitting(true);
    setStatusMsg('Resolving locations...');
    try {
      const [pickupCoords, destCoords] = await Promise.all([
        resolveCoords(pickup),
        resolveCoords(destination),
      ]);

      if (!pickupCoords) {
        alert('Could not find coordinates for pickup location. Try a more specific address.');
        setIsSubmitting(false);
        setStatusMsg('Dynamic matching in progress...');
        return;
      }
      if (!destCoords) {
        alert('Could not find coordinates for destination. Try a more specific address.');
        setIsSubmitting(false);
        setStatusMsg('Dynamic matching in progress...');
        return;
      }

      const payload = {
        pickup_location: `POINT(${pickupCoords.lon} ${pickupCoords.lat})`,
        destination_location: `POINT(${destCoords.lon} ${destCoords.lat})`,
        pickupCoords: { lat: pickupCoords.lat, lng: pickupCoords.lon },
        destCoords: { lat: destCoords.lat, lng: destCoords.lon },
      };

      onRideRequested(payload);
      setStatusMsg('Ride requested! Matching passengers...');
      setPickup('');
      setDestination('');
    } catch (error) {
      console.error('Booking error', error);
      alert('Error booking ride. Please check your internet connection and try again.');
      setStatusMsg('Dynamic matching in progress...');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="glass-panel" style={{ padding: '1.5rem', width: '350px', position: 'absolute', top: '1.5rem', left: '1.5rem', zIndex: 10 }}>
      <h2 className="font-bold text-xl" style={{ marginBottom: '1.5rem' }}>Book a Ride</h2>

      <form onSubmit={handleSubmit}>
        <div className="input-group">
          <label className="input-label" style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
            <User size={14} /> Pickup Location
          </label>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <input
              type="text"
              className="input-field"
              placeholder="Address or use GPS ↗"
              value={pickup}
              onChange={(e) => setPickup(e.target.value)}
              required
              style={{ flex: 1 }}
            />
            <button
              type="button"
              onClick={fetchLocation}
              className="btn btn-outline"
              style={{ padding: '0 0.75rem', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}
              disabled={isLocating}
              title="Use my current location"
            >
              <LocateFixed size={18} style={{ animation: isLocating ? 'spin 1s linear infinite' : 'none' }} />
            </button>
          </div>
        </div>

        <div className="input-group">
          <label className="input-label" style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
            <MapPin size={14} /> Destination
          </label>
          <input
            type="text"
            className="input-field"
            placeholder="Where to?"
            value={destination}
            onChange={(e) => setDestination(e.target.value)}
            required
          />
        </div>

        <button
          type="submit"
          className="btn btn-primary"
          disabled={isSubmitting}
          style={{ width: '100%', marginTop: '0.5rem' }}
        >
          {isSubmitting ? 'Resolving...' : (<>Request Ride <Navigation size={18} /></>)}
        </button>
      </form>

      <div style={{ marginTop: '1.5rem', paddingTop: '1.5rem', borderTop: '1px solid var(--border-color)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-secondary)' }}>
          <Clock size={16} />
          <span className="text-sm">{statusMsg}</span>
        </div>
      </div>
    </div>
  );
};

export default RideBooking;

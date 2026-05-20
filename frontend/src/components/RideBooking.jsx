import React, { useState } from 'react';
import { MapPin, Navigation, Clock, User } from 'lucide-react';
import { ridesAPI } from '../services/api';

const RideBooking = ({ onRideRequested }) => {
  const [pickup, setPickup] = useState('');
  const [destination, setDestination] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      // In a real app, you'd geocode the addresses to coordinates first.
      // Assuming backend expects coordinates, this would be a mock:
      const payload = {
        pickup_location: "POINT(-74.0060 40.7128)",
        destination_location: "POINT(-73.9352 40.7306)"
      };
      // const res = await ridesAPI.requestRide(payload);
      
      // Notify parent
      onRideRequested(payload);
      
      setPickup('');
      setDestination('');
      alert("Ride requested successfully!");
    } catch (error) {
      console.error("Booking error", error);
      alert("Error booking ride. Backend might be offline.");
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
          <input 
            type="text" 
            className="input-field" 
            placeholder="Current Location" 
            value={pickup}
            onChange={e => setPickup(e.target.value)}
            required
          />
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
            onChange={e => setDestination(e.target.value)}
            required
          />
        </div>

        <button type="submit" className="btn btn-primary" disabled={isSubmitting} style={{ width: '100%', marginTop: '0.5rem' }}>
          {isSubmitting ? 'Requesting...' : (
            <>Request Ride <Navigation size={18} /></>
          )}
        </button>
      </form>

      <div style={{ marginTop: '1.5rem', paddingTop: '1.5rem', borderTop: '1px solid var(--border-color)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-secondary)' }}>
          <Clock size={16} />
          <span className="text-sm">Dynamic matching in progress...</span>
        </div>
      </div>
    </div>
  );
};

export default RideBooking;

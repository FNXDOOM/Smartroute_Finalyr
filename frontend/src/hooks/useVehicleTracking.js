import { useState, useEffect } from 'react';
import { useAuth } from '@clerk/clerk-react';

export const useVehicleTracking = () => {
  const [vehicles, setVehicles] = useState([]);
  const { isLoaded, isSignedIn, getToken } = useAuth();

  useEffect(() => {
    if (!isLoaded || !isSignedIn) return undefined;

    let ws;
    let cancelled = false;

    const connect = async () => {
      const token = await getToken();
      if (cancelled || !token) return;

      const apiUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
      const wsUrl = apiUrl.replace(/^http/, 'ws');
      ws = new WebSocket(`${wsUrl}/tracking/ws?token=${encodeURIComponent(token)}`);

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.vehicles) setVehicles(data.vehicles);
          if (data.type === 'vehicle_location_update' && data.vehicle) {
            setVehicles((current) => current.map((vehicle) => (
              vehicle.id === data.vehicle.id ? data.vehicle : vehicle
            )));
          }
        } catch (error) {
          console.error('Error parsing tracking message', error);
        }
      };

      ws.onclose = () => {
        if (!cancelled) console.warn('Tracking WebSocket closed');
      };
    };

    connect();

    return () => {
      cancelled = true;
      ws?.close();
    };
  }, [getToken, isLoaded, isSignedIn]);

  return { vehicles };
};

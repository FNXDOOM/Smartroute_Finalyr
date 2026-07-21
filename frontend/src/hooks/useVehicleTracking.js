import { useState, useEffect } from 'react';

export const useVehicleTracking = (url = 'ws://localhost:8000/ws/tracking') => {
  const [vehicles, setVehicles] = useState([]);

  useEffect(() => {
    const ws = new WebSocket(url);

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'update' && data.vehicles) {
          setVehicles(data.vehicles);
        }
      } catch (error) {
        console.error("Error parsing websocket message", error);
      }
    };

    ws.onclose = () => {
      console.log('WebSocket connection closed');
    };

    return () => {
      ws.close();
    };
  }, [url]);

  return { vehicles };
};

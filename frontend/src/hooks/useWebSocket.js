import { useEffect, useRef, useCallback } from 'react';

// Reconnecting WebSocket with fresh tokens.
export function useWebSocket(factory, getToken, onMessage, enabled = true) {
  const wsRef = useRef(null);
  const retryRef = useRef(null);
  const mountedRef = useRef(true);
  const connectRef = useRef(null);
  const generationRef = useRef(0);

  const connect = useCallback(async () => {
    const generation = generationRef.current;
    if (!enabled || !mountedRef.current) return;
    let token;
    try {
      token = await getToken();
    } catch (error) { void error; return; }
    // A teardown may have happened while the token was resolving; that socket
    // must never be created or tracked.
    if (!token || !mountedRef.current || generation !== generationRef.current) return;
    try {
      const ws = factory(token, (msg) => {
        if (mountedRef.current && generation === generationRef.current) onMessage(msg);
      }, () => {
        if (!mountedRef.current || generation !== generationRef.current) return;
        retryRef.current = setTimeout(() => connectRef.current?.(), 3000);
      });
      if (generation !== generationRef.current) { ws.close(); return; }
      wsRef.current = ws;
    } catch (error) { void error }
  }, [factory, getToken, onMessage, enabled]);

  useEffect(() => {
    mountedRef.current = true;
    generationRef.current += 1;
    connectRef.current = connect;
    connect();
    return () => {
      mountedRef.current = false;
      generationRef.current += 1;
      connectRef.current = null;
      clearTimeout(retryRef.current);
      wsRef.current?.close();
    };
  }, [connect]);
}

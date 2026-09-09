import { useEffect, useRef, useCallback } from 'react';

// Reconnecting WebSocket with fresh tokens.
export function useWebSocket(factory, getToken, onMessage, enabled = true) {
  const wsRef = useRef(null);
  const retryRef = useRef(null);
  const mountedRef = useRef(true);
  const connectRef = useRef(null);

  const connect = useCallback(async () => {
    if (!enabled || !mountedRef.current) return;
    let token;
    try {
      token = await getToken();
    } catch (error) { void error; return; }
    if (!token || !mountedRef.current) return;
    try {
      const ws = factory(token, (msg) => {
        if (mountedRef.current) onMessage(msg);
      }, () => {
        if (!mountedRef.current) return;
        retryRef.current = setTimeout(() => connectRef.current?.(), 3000);
      });
      wsRef.current = ws;
    } catch (error) { void error }
  }, [factory, getToken, onMessage, enabled]);

  useEffect(() => {
    mountedRef.current = true;
    connectRef.current = connect;
    connect();
    return () => {
      mountedRef.current = false;
      connectRef.current = null;
      clearTimeout(retryRef.current);
      wsRef.current?.close();
    };
  }, [connect]);
}

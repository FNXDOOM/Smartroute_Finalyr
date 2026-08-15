import { useEffect, useRef, useCallback } from 'react';

/**
 * Generic reconnecting WebSocket hook.
 * factory: (token) => WebSocket instance
 */
export function useWebSocket(factory, token, onMessage, enabled = true) {
  const wsRef = useRef(null);
  const retryRef = useRef(null);
  const mountedRef = useRef(true);

  const connect = useCallback(() => {
    if (!token || !enabled || !mountedRef.current) return;
    try {
      const ws = factory(token, (msg) => {
        if (mountedRef.current) onMessage(msg);
      }, () => {
        if (!mountedRef.current) return;
        retryRef.current = setTimeout(connect, 3000);
      });
      wsRef.current = ws;
    } catch {}
  }, [factory, token, onMessage, enabled]);

  useEffect(() => {
    mountedRef.current = true;
    connect();
    return () => {
      mountedRef.current = false;
      clearTimeout(retryRef.current);
      wsRef.current?.close();
    };
  }, [connect]);
}

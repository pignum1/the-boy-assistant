import { useCallback, useEffect, useRef, useState } from 'react';
import type { WSMessage } from '../types/websocket';
import { getWsUrl } from '../api/client';

interface UseWebSocketOptions {
  taskId: string;
  teamId?: string;
  onMessage?: (msg: WSMessage) => void;
  maxRetries?: number;
}

export function useWebSocket({ taskId, teamId, onMessage, maxRetries = 5 }: UseWebSocketOptions) {
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const retriesRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout>>();

  const connect = useCallback(() => {
    const url = getWsUrl(`/ws/tasks/${taskId}`, teamId ? { team_id: teamId } : undefined);
    const ws = new WebSocket(url);

    ws.onopen = () => {
      setConnected(true);
      retriesRef.current = 0;
    };

    ws.onmessage = (event) => {
      try {
        const msg: WSMessage = JSON.parse(event.data);
        onMessage?.(msg);
      } catch { /* ignore parse errors */ }
    };

    ws.onclose = () => {
      setConnected(false);
      if (retriesRef.current < maxRetries) {
        const delay = Math.min(1000 * 2 ** retriesRef.current, 30000);
        retriesRef.current += 1;
        setTimeout(connect, delay);
      }
    };

    ws.onerror = (err) => { console.error('[useWebSocket] error:', err); ws.close(); };
    wsRef.current = ws;
  }, [taskId, teamId, onMessage, maxRetries]);

  useEffect(() => {
    connect();
    return () => {
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [connect]);

  const send = useCallback((data: Record<string, unknown>) => {
    wsRef.current?.send(JSON.stringify(data));
  }, []);

  const ping = useCallback(() => wsRef.current?.send('ping'), []);

  return { connected, send, ping };
}

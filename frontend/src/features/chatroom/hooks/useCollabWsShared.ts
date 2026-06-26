/** useCollabWsShared — 共享的协作 WebSocket 连接管理

供 SwarmView 和 SupervisorView 使用，消除重复的 WS 连接代码。

职责：
1. 建立/维护 WebSocket 连接（指数退避重连）
2. 30s ping 保活
3. 将入站消息分派给调用方提供的 onMessage 回调
4. 提供出站 sendChat/sendHitlResume 函数

使用方式：
  const { connected, sendChat, sendHitlResume } = useCollabWsShared({
    sessionId,
    onMessage: handleMessage,  // 每个 view 提供自己的消息处理器
    debugName: 'SwarmView',   // 用于调试日志
  });
*/

import { useState, useEffect, useRef, useCallback } from 'react';
import { getWsUrl } from '../../../shared/api/client';

export interface WsMessage {
  type: string;
  payload?: Record<string, unknown>;
  [key: string]: unknown;
}

interface UseCollabWsSharedOptions {
  sessionId: string;
  onMessage: (msg: WsMessage) => void;
  debugName?: string;
  maxRetries?: number;
}

export function useCollabWsShared({
  sessionId,
  onMessage,
  debugName = 'Collab',
  maxRetries = 8,
}: UseCollabWsSharedOptions) {
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const retriesRef = useRef(0);
  const pingRef = useRef<ReturnType<typeof setInterval>>();
  // 保存最新回调引用，避免 useEffect 重连
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  // 建连
  useEffect(() => {
    let mounted = true;
    retriesRef.current = 0;

    function connect(): WebSocket {
      const url = getWsUrl(`/ws/sessions/${sessionId}`);
      console.log(`[${debugName}] Connecting to ${url}`);
      const ws = new WebSocket(url);

      ws.onopen = () => {
        if (!mounted) { ws.close(); return; }
        console.log(`[${debugName}] Connected`);
        setConnected(true);
        retriesRef.current = 0;
        // 30s ping 保活
        pingRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) ws.send('ping');
        }, 30_000);
      };

      ws.onmessage = (event) => {
        if (!mounted) return;
        try {
          const data = JSON.parse(event.data) as WsMessage;
          if (data?.type) onMessageRef.current(data);
        } catch {
          // 忽略解析错误
        }
      };

      ws.onclose = () => {
        if (!mounted) return;
        setConnected(false);
        if (pingRef.current) clearInterval(pingRef.current);
        // 指数退避重连：1s, 2s, 4s, ..., max 30s
        if (retriesRef.current < maxRetries) {
          const delay = Math.min(1000 * 2 ** retriesRef.current, 30_000);
          retriesRef.current += 1;
          console.log(`[${debugName}] Reconnecting in ${delay}ms (attempt ${retriesRef.current})`);
          setTimeout(() => {
            if (mounted) { wsRef.current = connect(); }
          }, delay);
        } else {
          console.log(`[${debugName}] Max retries (${maxRetries}) reached`);
        }
      };

      ws.onerror = (err) => {
        console.error(`[${debugName}] WebSocket error:`, err);
      };

      return ws;
    }

    wsRef.current = connect();

    return () => {
      mounted = false;
      if (pingRef.current) clearInterval(pingRef.current);
      wsRef.current?.close();
    };
  }, [sessionId, debugName, maxRetries]);

  // 出站：发送聊天消息
  const sendChat = useCallback((content: string, mentionedAgents?: string[]) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'chat',
        message: content,
        mentioned_agents: mentionedAgents,
      }));
    }
  }, []);

  // 出站：发送 HITL 恢复
  const sendHitlResume = useCallback((response: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'hitl_resume',
        ...response,
      }));
    }
  }, []);

  // 出站：发送中断
  const sendInterrupt = useCallback((mode: 'soft' | 'hard', message?: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'interrupt',
        mode,
        message,
      }));
    }
  }, []);

  // 出站：发送原始 JSON（用于自定义消息格式）
  const sendRaw = useCallback((data: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    }
  }, []);

  return {
    connected,
    sendChat,
    sendHitlResume,
    sendInterrupt,
    sendRaw,
  };
}

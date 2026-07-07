/** useWsEvents — WebSocket 订阅 + 入站事件 → reducer action 映射
 *
 * 职责：
 *   1. 建立/维护 WebSocket 连接（含自动重连）
 *   2. 把入站 inbound message 映射为 ChatRoomAction，dispatch 到 reducer
 *   3. 提供出站发送函数（sendMessage / sendHitlResume / sendInterrupt / sendResume / sendApproveDeltaPlan）
 *
 * 不持有 UI 状态。所有状态都在 reducer 里。
 */

import { useCallback, useEffect, useRef, useMemo } from 'react';
import type {
  InboundMessage,
  OutboundMessage,
} from '../types/events';
import { getWsUrl } from '../../../shared/api/client';
import type { ChatRoomAction } from '../store/actions';

export interface UseWsEventsOptions {
  sessionId: string;
  dispatch: React.Dispatch<ChatRoomAction>;
  maxRetries?: number;
}

export interface WsSendApi {
  /** 发起新对话（普通消息） */
  sendChat: (content: string, mentionedAgents?: string[]) => void;
  /** HITL 回复 */
  sendHitlResume: (response: string) => void;
  /** 介入（软/硬） */
  sendInterrupt: (mode: 'soft' | 'hard', message?: string) => void;
  /** 暂停后恢复 */
  sendResume: (message?: string) => void;
  /** 批准/拒绝 delta_plan */
  sendApproveDeltaPlan: (approve: boolean, reason?: string) => void;
  /** 心跳 */
  sendPing: () => void;
}

export function useWsEvents({
  sessionId,
  dispatch,
  maxRetries = 5,
}: UseWsEventsOptions): WsSendApi {
  const wsRef = useRef<WebSocket | null>(null);
  const retriesRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout>>();
  const lastSessionRef = useRef(sessionId);
  const pendingMessagesRef = useRef<OutboundMessage[]>([]);
  const connectEpochRef = useRef(0);

  // ── 出站发送（带队列，WS 断开时缓存消息，重连后发送） ──

  const drainQueue = useCallback(() => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    const queue = pendingMessagesRef.current;
    while (queue.length > 0) {
      const msg = queue.shift()!;
      try { ws.send(JSON.stringify(msg)); } catch { queue.unshift(msg); break; }
    }
  }, []);

  const safeSend = useCallback((msg: OutboundMessage) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(msg));
    } else {
      // WS 未就绪 → 缓存到队列，连接后自动发送
      pendingMessagesRef.current.push(msg);
    }
  }, []);

  const sendChat = useCallback((content: string, mentionedAgents?: string[]) => {
    safeSend({ type: 'chat', message: content, mentioned_agents: mentionedAgents });
  }, [safeSend]);

  const sendHitlResume = useCallback((response: string) => {
    safeSend({ type: 'hitl_resume', response });
  }, [safeSend]);

  const sendInterrupt = useCallback((mode: 'soft' | 'hard', message?: string) => {
    safeSend({ type: 'interrupt', mode, message });
  }, [safeSend]);

  const sendResume = useCallback((message?: string) => {
    safeSend({ type: 'resume', message });
  }, [safeSend]);

  const sendApproveDeltaPlan = useCallback((approve: boolean, reason?: string) => {
    safeSend({ type: 'approve_delta_plan', approve, reason });
  }, [safeSend]);

  const sendPing = useCallback(() => {
    // 后端 ws.py 期望裸字符串 "ping"，不走 JSON
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send('ping');
    }
  }, []);

  // ── 入站 → action 映射 ──

  const dispatchInbound = useCallback((msg: InboundMessage) => {
    const action = mapInboundToAction(msg);
    if (action) dispatch(action);
  }, [dispatch]);

  // ── 连接管理 ──

  // sessionId 变化 → 重置 + 重连
  // 注意：用 useEffect 直接管 WS 而非 useCallback+connect，避免 StrictMode 双连接
  useEffect(() => {
    if (lastSessionRef.current !== sessionId) {
      lastSessionRef.current = sessionId;
      dispatch({ type: 'CTRL/INIT_SESSION', sessionId });
    }

    // epoch 标志：每次 effect 运行递增。旧 WS 的事件处理中检查 epoch，
    // 不匹配则忽略，避免 StrictMode 双 mount 导致状态异常。
    const epoch = ++connectEpochRef.current;
    let mounted = true;

    function open(): WebSocket {
      const url = getWsUrl(`/ws/sessions/${sessionId}`);
      const ws = new WebSocket(url);

      // ── 轮询历史（重连后检查是否有新消息）──
      let pollTimer: ReturnType<typeof setInterval> | null = null;
      const stopPoll = () => {
        if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
      };
      const startPoll = () => {
        stopPoll();
        let attempts = 0;
        pollTimer = setInterval(async () => {
          if (!mounted || epoch !== connectEpochRef.current) { stopPoll(); return; }
          attempts++;
          try {
            const API = (import.meta as any).env?.VITE_API_URL || '';
            const res = await fetch(`${API}/api/v1/sessions/${sessionId}/messages?limit=200`);
            const data = await res.json();
            const msgs = data.messages || [];
            if (msgs.length > 0) {
              dispatch({ type: 'CTRL/HISTORY_REFRESH', messages: msgs });
              // 有新消息（非 user）→ 停止轮询
              const hasNew = msgs.some((m: any) => m.role !== 'user');
              if (hasNew || attempts > 10) stopPoll();
            }
          } catch { /* ignore fetch errors */ }
        }, 3000);
      };

      ws.onopen = () => {
        if (!mounted || epoch !== connectEpochRef.current) { ws.close(); return; }
        dispatch({ type: 'CTRL/WS_CONNECTED', connected: true });
        retriesRef.current = 0;
        drainQueue();
        startPoll();
      };

      ws.onmessage = (event) => {
        if (!mounted) return;
        try {
          const raw = JSON.parse(event.data) as InboundMessage;
          if (!raw || typeof raw !== 'object' || !('type' in raw)) return;
          dispatchInbound(raw);
        } catch {
          // ignore parse errors
        }
      };

      ws.onclose = () => {
        if (!mounted || epoch !== connectEpochRef.current) return;
        dispatch({ type: 'CTRL/WS_CONNECTED', connected: false });
        if (retriesRef.current < maxRetries) {
          const delay = Math.min(1000 * 2 ** retriesRef.current, 30000);
          retriesRef.current += 1;
          reconnectTimerRef.current = setTimeout(() => {
            if (mounted && epoch === connectEpochRef.current) wsRef.current = open();
          }, delay);
        }
      };

      ws.onerror = () => {
        if (!mounted || epoch !== connectEpochRef.current) return;
        ws.close();
      };
      return ws;
    }

    wsRef.current = open();

    return () => {
      mounted = false;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      wsRef.current = null;
      // 注意：StrictMode 下不主动 close WS。
      // 浏览器在页面真正卸载时会自动关闭。React double-mount 时
      // 第一次 effect 的 open() 创建的连接会自然完成，第二次 effect
      // 的 open() 会创建新连接，旧连接通过 onopen 里 mounted 检查自动关闭。
    };
  }, [sessionId, dispatch, dispatchInbound, maxRetries]);

  return useMemo(() => ({
    sendChat,
    sendHitlResume,
    sendInterrupt,
    sendResume,
    sendApproveDeltaPlan,
    sendPing,
  }), [sendChat, sendHitlResume, sendInterrupt, sendResume, sendApproveDeltaPlan, sendPing]);
}

// ── 入站消息 → action 映射器（纯函数，可独立测试） ──

export function mapInboundToAction(msg: InboundMessage): ChatRoomAction | null {
  switch (msg.type) {
    case 'routing_decision':
      return { type: 'WS/ROUTING_DECISION', payload: msg.payload };
    case 'agent_status':
      return { type: 'WS/AGENT_STATUS', payload: msg.payload };
    case 'agent_message':
      return { type: 'WS/AGENT_MESSAGE', payload: msg.payload, source: msg.source };
    case 'thinking_update':
      return { type: 'WS/THINKING_UPDATE', payload: msg.payload };
    case 'reasoning_complete':
      return { type: 'WS/REASONING_COMPLETE', payload: msg.payload };
    case 'hitl_request':
    case 'hitl_notification':  // swarm 引擎使用 hitl_notification
    case 'request_clarification':  // langgraph 引擎使用 request_clarification
      return { type: 'WS/HITL_REQUEST', payload: msg.payload };
    case 'task_output':       // swarm 引擎的任务产出（同 agent_message）
      return { type: 'WS/AGENT_MESSAGE', payload: msg.payload, source: msg.source };
    case 'phase_update':
      return { type: 'WS/PHASE_UPDATE', payload: msg.payload };
    case 'files_changed':
      return { type: 'WS/FILES_CHANGED', payload: msg.payload };
    case 'message_complete':
      return { type: 'WS/MESSAGE_COMPLETE', payload: msg.payload };
    case 'tool_call':
      return { type: 'WS/TOOL_CALL', payload: msg.payload };
    case 'stream_token':
      return { type: 'WS/STREAM_TOKEN', payload: msg.payload };
    case 'error':
      return { type: 'WS/ERROR', payload: msg.payload };
    case 'task_dag':
      return { type: 'WS/TASK_DAG', payload: msg.payload };
    case 'task_status':
      return { type: 'WS/TASK_STATUS', payload: msg.payload };
    case 'execution_state':
      return { type: 'WS/EXECUTION_STATE', payload: msg.payload };
    case 'delta_plan':
      return { type: 'WS/DELTA_PLAN', payload: msg.payload };
    case 'pong':
      return null;
    default: {
      // 未来扩展时的安全降级
      // eslint-disable-next-line no-console
      console.warn('[mapInboundToAction] unknown event type', (msg as { type: string }).type);
      return null;
    }
  }
}

import { useState, useRef, useCallback, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { api, getWsUrl } from '../../../shared/api/client';
import { WorkspacePanel } from '../WorkspacePanel';
import { MembersPanel, WorkspaceSlideover } from '../components/ChatPanels';

interface HitlOption {
  label: string;
  value: string;
  description?: string;
}

interface SwarmMessage {
  id: string;
  agentId: string;
  agentName: string;
  agentEmoji: string;
  avatar?: string;
  content: string;
  reasoning?: {
    thinking_steps?: string;
    tool_calls?: Array<{ tool: string; status: string; detail?: string }>;
    decision_summary?: string;
  };
  timestamp: number;
  isUser?: boolean;
  round?: number;
  hitlId?: string;
  hitlType?: 'select' | 'multi_select' | 'answer' | 'review';
  hitlOptions?: HitlOption[];
  hitlResolved?: boolean;
  hitlResponse?: string;
}

interface AgentStatus {
  agent_id: string;
  agent_name: string;
  status: 'thinking' | 'idle';
  summary: string;
}

interface Props {
  sessionId: string;
  teamId: string;
}

export function SwarmView({ sessionId, teamId }: Props) {
  const [messages, setMessages] = useState<SwarmMessage[]>([]);
  const [inputText, setInputText] = useState('');
  const [agents, setAgents] = useState<Array<{ id: string; name: string; emoji: string }>>([]);
  const [expandedReasoning, setExpandedReasoning] = useState<Record<string, boolean>>({});
  const [agentStatuses, setAgentStatuses] = useState<Record<string, AgentStatus>>({});
  const [isConnected, setIsConnected] = useState(false);
  const [showMembers, setShowMembers] = useState(false);
  const [showWorkspace, setShowWorkspace] = useState(false);
  const [activeHitl, setActiveHitl] = useState<{
    id: string;
    hitl_type: 'select' | 'multi_select' | 'answer' | 'review';
    message: string;
    options: HitlOption[];
  } | null>(null);
  const [hitlReviewFeedback, setHitlReviewFeedback] = useState('');
  const [hitlAnswerText, setHitlAnswerText] = useState('');
  const [multiSelectValues, setMultiSelectValues] = useState<string[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);

  // Load team members
  useEffect(() => {
    api.get<{ members: { id: string; agent_id: string; agent_name: string; role_name: string; role_icon?: string }[] }>(
      `/api/v1/teams/${teamId}`
    )
      .then(team => setAgents(
        (team.members || []).map(m => ({
          id: m.agent_id,
          name: m.agent_name,
          emoji: m.role_icon || '🤖',
        }))
      ))
      .catch(() => {});

    // Load session messages
    api.get<{ messages: Array<{ id: string; role: string; agent_name?: string; content: string; metadata?: any; timestamp: string }> }>(
      `/api/v1/sessions/${sessionId}/messages`
    )
      .then(data => {
        const seenUserContent = new Set<string>();
        const parsed: SwarmMessage[] = [];
        const msgs = data.messages || [];
        const respondedHitlIds = new Set<string>();
        for (const m of msgs) {
          const meta = m.metadata || {};
          if (meta.hitl_response && meta.hitl_id) {
            respondedHitlIds.add(meta.hitl_id);
          }
        }
        for (const m of msgs) {
          const meta = m.metadata || {};
          const isHitlNotification = !!meta.hitl_notification;
          const isHitlResponse = !!meta.hitl_response;
          const isUser = m.role === 'user';
          if (isUser && !isHitlResponse) {
            if (seenUserContent.has(m.content)) continue;
            seenUserContent.add(m.content);
          }
          let hitlOptions: HitlOption[] | undefined;
          if (meta.hitl_options) {
            hitlOptions = meta.hitl_options.map((opt: any) => {
              if (typeof opt === 'string') return { label: opt, value: opt };
              return { label: opt.label || opt.value, value: opt.value, description: opt.description };
            });
          }
          const hitlId: string = meta.hitl_id || '';
          const hitlResolved = isHitlResponse || (isHitlNotification && respondedHitlIds.has(hitlId));
          parsed.push({
            id: m.id || `msg-${parsed.length}`,
            agentId: isHitlNotification ? 'system' : (isHitlResponse ? 'user' : (isUser ? 'user' : (meta.agent || 'agent'))),
            agentName: isHitlNotification ? '系统' : (isHitlResponse ? '你' : (isUser ? '你' : (meta.agent || m.agent_name || 'Agent'))),
            agentEmoji: isHitlNotification ? '\ud83e\udd14' : (isHitlResponse ? '\u2713' : (isUser ? '\ud83d\udc64' : '\ud83e\udd16')),
            content: isHitlResponse ? `\u2705 **\u51b3\u7b56\u786e\u8ba4**\n\n${m.content}` : m.content,
            reasoning: meta.thinking_steps ? {
              thinking_steps: meta.thinking_steps,
              tool_calls: meta.tool_calls,
              decision_summary: meta.decision_summary,
            } : undefined,
            timestamp: new Date(m.timestamp).getTime(),
            isUser: isHitlResponse || (isUser && !isHitlNotification),
            hitlId: hitlId || undefined,
            hitlType: meta.hitl_type as SwarmMessage['hitlType'],
            hitlOptions,
            hitlResolved,
            hitlResponse: isHitlResponse ? m.content : undefined,
          });
        }
        setMessages(parsed);

        // 恢复未解决的 HITL 状态（刷新页面后 activeHitl 需要恢复才能交互）
        const unresolvedHitl = parsed.find(m => m.hitlOptions && !m.hitlResolved);
        if (unresolvedHitl && unresolvedHitl.hitlId) {
          setActiveHitl({
            id: unresolvedHitl.hitlId,
            hitl_type: unresolvedHitl.hitlType || 'select',
            message: unresolvedHitl.content,
            options: unresolvedHitl.hitlOptions || [],
          });
        }
      })
      .catch(() => {});
  }, [sessionId, teamId]);

  // WebSocket connection
  useEffect(() => {
    const wsUrl = getWsUrl(`/ws/sessions/${sessionId}`);
    console.log('[SwarmView] Connecting WebSocket to:', wsUrl);
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('[SwarmView] WebSocket connected');
      setIsConnected(true);
      const pingInterval = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send('ping');
        else clearInterval(pingInterval);
      }, 30000);
    };

    ws.onmessage = (event) => {
      try { const data = JSON.parse(event.data); handleMessage(data); }
      catch (e) { console.error('Failed to parse WebSocket message:', e); }
    };

    ws.onclose = () => { console.log('[SwarmView] WebSocket disconnected'); setIsConnected(false); };
    ws.onerror = (error) => { console.error('[SwarmView] WebSocket error:', error); };

    return () => { ws.close(); };
  }, [sessionId]);

  const handleMessage = useCallback((data: any) => {
    console.log('[SwarmView] Received WebSocket message:', data.type, data);
    switch (data.type) {
      case 'routing_decision':
      case 'thinking_update':
        // Don't show as messages — status is shown in header indicator
        break;

      case 'agent_status':
        setAgentStatuses(prev => ({
          ...prev,
          [data.payload.agent_id]: data.payload,
        }));
        break;

      case 'agent_message':
      case 'task_output': {
        const payload = data.payload;
        const isTaskOutput = data.type === 'task_output';
        const newMsg: SwarmMessage = {
          id: `agent-${Date.now()}-${Math.random()}`,
          agentId: payload.agent_id || 'agent',
          agentName: payload.agent || 'Agent',
          agentEmoji: payload.agent_emoji || '🤖',
          content: payload.content || '',
          reasoning: undefined,
          timestamp: Date.now(),
          round: payload.round,
        };
        setMessages(prev => {
          // Deduplicate: avoid adding the same content twice
          const lastMsg = prev[prev.length - 1];
          if (lastMsg && lastMsg.content === newMsg.content && lastMsg.agentName === newMsg.agentName) {
            return prev;
          }
          return [...prev, newMsg];
        });
        break;
      }

      case 'reasoning_complete': {
        const payload = data.payload;
        const agentName = payload.agent;
        if (agentName) {
          setMessages(prev => prev.map(msg => {
            if (msg.agentName === agentName && !msg.reasoning) {
              return {
                ...msg,
                reasoning: {
                  thinking_steps: payload.thinking_steps,
                  tool_calls: payload.tool_calls,
                  decision_summary: payload.decision_summary,
                },
              };
            }
            return msg;
          }));
        }
        break;
      }

      case 'storage_update': {
        const payload = data.payload;
        const filePath = payload.path || payload.detail || '新文件';
        const op = payload.operation === 'write' ? '已写入' : '已保存';
        const sysMsg: SwarmMessage = {
          id: `storage-${Date.now()}-${Math.random()}`,
          agentId: 'system',
          agentName: payload.agent || '系统',
          agentEmoji: '📄',
          content: `✅ **${payload.agent}** ${op} \`${filePath}\``,
          timestamp: Date.now(),
        };
        setMessages(prev => [...prev, sysMsg]);
        break;
      }

      case 'hitl_notification': {
        const payload = data.payload;
        const hitlId = payload.id || `hitl-${Date.now()}`;
        const hitlType: SwarmMessage['hitlType'] = payload.hitl_type || 'select';
        const hitlMessage = payload.message || '团队讨论中出现分歧，需要您介入裁决。';
        // Normalize options: handle old string[] and new HitlOption[]
        const rawOptions: any[] = payload.options || [{ label: '继续', value: 'continue' }, { label: '停止', value: 'stop' }];
        const options: HitlOption[] = rawOptions.map((opt: any) => {
          if (typeof opt === 'string') return { label: opt, value: opt };
          return { label: opt.label || opt.value, value: opt.value, description: opt.description };
        });
        setActiveHitl({
          id: hitlId,
          hitl_type: hitlType,
          message: hitlMessage,
          options,
        });
        setHitlAnswerText('');
        setHitlReviewFeedback('');
        setMultiSelectValues([]);
        const hitlMsg: SwarmMessage = {
          id: hitlId,
          agentId: 'system',
          agentName: '系统',
          agentEmoji: '🤔',
          content: `⚠️ **需要您的决策**\n\n${hitlMessage}`,
          timestamp: Date.now(),
          hitlId,
          hitlType,
          hitlOptions: options,
        };
        setMessages(prev => [...prev, hitlMsg]);
        break;
      }

      case 'message_complete':
        setAgentStatuses({});
        break;

      case 'error':
        console.error('Server error:', data.payload);
        break;
    }
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // ESC key dismisses HITL — user can then type a free-text response
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && activeHitl) {
        setMessages(prev => prev.map(msg => {
          if (msg.hitlId === activeHitl.id) {
            return { ...msg, hitlResolved: true, hitlOptions: undefined };
          }
          return msg;
        }));
        setActiveHitl(null);
        setHitlAnswerText('');
        setHitlReviewFeedback('');
        setMultiSelectValues([]);
      }
    };
    window.addEventListener('keydown', handleEsc);
    return () => window.removeEventListener('keydown', handleEsc);
  }, [activeHitl]);

  const toggleReasoning = useCallback((msgId: string) => {
    setExpandedReasoning(prev => ({ ...prev, [msgId]: !prev[msgId] }));
  }, []);

  const handleSend = useCallback(async () => {
    if (!inputText.trim() || !wsRef.current) return;

    const userMsg: SwarmMessage = {
      id: `user-${Date.now()}`,
      agentId: 'user',
      agentName: '你',
      agentEmoji: '👤',
      content: inputText,
      timestamp: Date.now(),
      isUser: true,
    };

    setMessages(prev => [...prev, userMsg]);
    const messageToSend = inputText;
    setInputText('');

    // Send via WebSocket
    const msgToSend = JSON.stringify({
      type: 'chat',
      message: messageToSend,
    });
    console.log('[SwarmView] Sending WebSocket message:', msgToSend);
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(msgToSend);
      console.log('[SwarmView] Message sent successfully');
    } else {
      console.error('[SwarmView] Cannot send - WebSocket not open, state:', wsRef.current?.readyState);
    }
  }, [inputText]);

  const resolveHitl = useCallback((hitlId: string, responseText: string) => {
    setMessages(prev => prev.map(msg => {
      if (msg.hitlId === hitlId) {
        return { ...msg, hitlResolved: true, hitlOptions: undefined, hitlResponse: responseText };
      }
      return msg;
    }));
    setActiveHitl(null);
    setHitlAnswerText('');
    setHitlReviewFeedback('');
    setMultiSelectValues([]);
  }, []);

  const handleHitlSelect = useCallback((value: string) => {
    if (!wsRef.current || !activeHitl) return;
    const label = activeHitl.options.find(o => o.value === value)?.label || value;
    wsRef.current.send(JSON.stringify({
      type: 'hitl_resume', hitl_id: activeHitl.id, hitl_type: 'select', values: [value],
    }));
    resolveHitl(activeHitl.id, label);
  }, [activeHitl, resolveHitl]);

  const handleHitlMultiSelectConfirm = useCallback(() => {
    if (!wsRef.current || !activeHitl || multiSelectValues.length === 0) return;
    const selectedLabels = multiSelectValues.map(v =>
      activeHitl.options.find(o => o.value === v)?.label || v
    );
    wsRef.current.send(JSON.stringify({
      type: 'hitl_resume', hitl_id: activeHitl.id, hitl_type: 'multi_select', values: multiSelectValues,
    }));
    resolveHitl(activeHitl.id, selectedLabels.join('\n'));
  }, [activeHitl, multiSelectValues, resolveHitl]);

  const handleHitlAnswer = useCallback(() => {
    if (!wsRef.current || !activeHitl || !hitlAnswerText.trim()) return;
    wsRef.current.send(JSON.stringify({
      type: 'hitl_resume', hitl_id: activeHitl.id, hitl_type: 'answer', response: hitlAnswerText.trim(),
    }));
    resolveHitl(activeHitl.id, `回答: ${hitlAnswerText.trim()}`);
  }, [activeHitl, hitlAnswerText, resolveHitl]);

  const handleHitlReview = useCallback((approved: boolean) => {
    if (!wsRef.current || !activeHitl) return;
    wsRef.current.send(JSON.stringify({
      type: 'hitl_resume', hitl_id: activeHitl.id, hitl_type: 'review',
      approved, feedback: hitlReviewFeedback.trim(),
    }));
    const verb = approved ? '已批准' : '已驳回';
    const fb = hitlReviewFeedback.trim();
    resolveHitl(activeHitl.id, `${verb}${fb ? ` (反馈: ${fb})` : ''}`);
  }, [activeHitl, hitlReviewFeedback, resolveHitl]);

  const formatTime = (timestamp: number) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  };

  // Get agent color based on name
  const getAgentColor = (agentName: string) => {
    const colors = ['#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6', '#1abc9c'];
    const hash = agentName.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0);
    return colors[hash % colors.length];
  };

  return (
    <>
      <style>{`
        @keyframes slideInRight {
          from { transform: translateX(100%); }
          to { transform: translateX(0); }
        }
        .markdown-content h1 { font-size: 18px; font-weight: 700; margin: 12px 0 8px; color: var(--chat-msg-agent-text); border-bottom: 1px solid var(--chat-msg-agent-border); padding-bottom: 6px; }
        .markdown-content h2 { font-size: 16px; font-weight: 650; margin: 10px 0 6px; color: var(--chat-msg-agent-text); }
        .markdown-content h3 { font-size: 14px; font-weight: 600; margin: 8px 0 4px; color: var(--chat-msg-agent-text); }
        .markdown-content p { margin: 4px 0 8px; }
        .markdown-content ul, .markdown-content ol { margin: 4px 0; padding-left: 20px; }
        .markdown-content li { margin: 2px 0; }
        .markdown-content code { background: var(--chat-reasoning-bg); padding: 1px 5px; border-radius: 3px; font-size: 12.5px; font-family: 'SF Mono', Menlo, Monaco, monospace; color: #c02660; }
        .markdown-content pre { background: #1e293b; padding: 12px 16px; border-radius: 8px; overflow-x: auto; margin: 8px 0; }
        .markdown-content pre code { background: none; padding: 0; color: #e2e8f0; font-size: 12px; white-space: pre; }
        .markdown-content table { border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 13px; }
        .markdown-content th, .markdown-content td { border: 1px solid var(--chat-msg-agent-border); padding: 6px 10px; text-align: left; }
        .markdown-content th { background: var(--chat-reasoning-bg); font-weight: 600; color: var(--chat-msg-agent-text); }
        .markdown-content blockquote { border-left: 3px solid #3b82f6; padding-left: 12px; margin: 8px 0; color: var(--text-secondary); background: var(--chat-reasoning-bg); padding: 8px 12px; border-radius: 0 6px 6px 0; }
        .markdown-content strong { color: var(--chat-msg-agent-text); font-weight: 650; }
        .markdown-content a { color: #2563eb; text-decoration: underline; }
        .markdown-content hr { border: none; border-top: 1px solid var(--chat-msg-agent-border); margin: 16px 0; }
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
        @keyframes scaleIn { from { opacity: 0; transform: translate(-50%, -60%) scale(0.95); } to { opacity: 1; transform: translate(-50%, -50%) scale(1); } }
        .chat-scroll::-webkit-scrollbar { width: 8px; }
        .chat-scroll::-webkit-scrollbar-track { background: transparent; }
        .chat-scroll::-webkit-scrollbar-thumb { background: rgba(148, 163, 184, 0.35); border-radius: 4px; }
        .chat-scroll::-webkit-scrollbar-thumb:hover { background: rgba(148, 163, 184, 0.55); }
      `}</style>
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: 'var(--chat-bg)' }}>
      {/* Header */}
      <div style={{
        padding: '16px 20px',
        background: 'var(--chat-header-bg)',
        borderBottom: '1px solid var(--chat-msg-agent-border)',
        boxShadow: '0 1px 2px rgba(0,0,0,0.02)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{
              display: 'inline-flex', alignItems: 'center', gap: 4,
              padding: '4px 12px', borderRadius: 20,
              fontSize: 12, fontWeight: 600,
              background: '#3b82f618', color: '#3b82f6',
              border: '1px solid #3b82f630',
            }}>
              💬 群聊模式
            </span>
            <span style={{ fontSize: 12, color: 'var(--text-dim)' }}>多 Agent 自由讨论</span>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <div style={{
              width: 8,
              height: 8,
              borderRadius: '50%',
              background: isConnected ? 'var(--green-400)' : 'var(--red-400)',
              flexShrink: 0,
            }} title={isConnected ? '已连接' : '未连接'}
            />
            <div
              style={{
                padding: '6px 12px',
                background: showMembers ? 'var(--chat-btn-active-bg)' : 'var(--bg-card-hover)',
                borderRadius: 16,
                fontSize: 12,
                color: showMembers ? 'var(--chat-btn-active-text)' : 'var(--text-dim)',
                cursor: 'pointer',
                fontWeight: showMembers ? 600 : 400,
              }}
              onClick={() => { setShowMembers(!showMembers); setShowWorkspace(false); }}
              title="查看成员列表"
            >
              👥 {agents.length} 个成员
            </div>
            <div
              style={{
                padding: '6px 12px',
                background: showWorkspace ? 'var(--chat-btn-active-bg)' : 'var(--bg-card-hover)',
                borderRadius: 16,
                fontSize: 12,
                color: showWorkspace ? 'var(--chat-btn-active-text)' : 'var(--text-dim)',
                cursor: 'pointer',
                fontWeight: showWorkspace ? 600 : 400,
              }}
              onClick={() => { setShowWorkspace(!showWorkspace); setShowMembers(false); }}
              title="查看工作空间文件"
            >
              📁 文件
            </div>
            {(() => {
              const spokenAgents = new Set(messages.filter(m => !m.isUser).map(m => m.agentName || m.agentId));
              const agentMsgs = messages.filter(m => !m.isUser);
              const rounds = agentMsgs.map(m => m.round || 0).filter(r => r > 0);
              const round = rounds.length ? Math.max(...rounds) : (agentMsgs.length > 0 ? Math.ceil(agentMsgs.length / Math.max(agents.length, 1)) : 0);
              return spokenAgents.size > 0 ? (
                <div style={{
                  padding: '6px 12px', borderRadius: 16, fontSize: 12,
                  background: 'var(--bg-card-hover)', color: 'var(--text-dim)',
                  fontWeight: 400,
                }} title={`已参与 ${spokenAgents.size}/${agents.length} 个成员 · ${agentMsgs.length} 条消息`}>
                  💬 {spokenAgents.size}/{agents.length} · {round} 轮
                </div>
              ) : null;
            })()}
          </div>
        </div>

      </div>

      {/* Members panel — shared component */}
      {showMembers && (
        <MembersPanel
          members={agents.map(a => ({ id: a.id, agent_id: a.id, agent_name: a.name, role_name: '', role_icon: a.emoji, status: 'idle' }))}
          agentStatuses={Object.fromEntries(Object.values(agentStatuses).map(s => [s.agent_name, { status: s.status, summary: s.summary }]))}
          onClose={() => setShowMembers(false)}
        />
      )}

      {/* Workspace panel — shared component */}
      {showWorkspace && (
        <WorkspaceSlideover sessionId={sessionId} onClose={() => setShowWorkspace(false)} />
      )}

      {/* Messages Area */}
      <div className="chat-scroll" style={{
        flex: 1,
        overflowY: 'auto',
        padding: '20px',
        display: 'flex',
        flexDirection: 'column',
        gap: 16,
      }}>
        {messages.length === 0 && (
          <div style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            height: '100%',
            color: 'var(--text-muted)',
          }}>
            <div style={{ fontSize: 48, marginBottom: 12 }}>💭</div>
            <div style={{ fontSize: 14, color: 'var(--text-dim)' }}>开始一段新的对话吧</div>
          </div>
        )}

        {messages.map(msg => (
          <div key={msg.id} style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: msg.isUser ? 'flex-end' : 'flex-start',
            alignSelf: msg.isUser ? 'flex-end' : 'flex-start',
            maxWidth: msg.isUser ? '70%' : '85%',
            minWidth: msg.isUser ? undefined : '60%',
          }}>
            {/* Agent Header (non-user) */}
            {!msg.isUser && (
              <div style={{ marginBottom: 6, paddingLeft: 4 }}>
                <span style={{
                  fontSize: 13,
                  fontWeight: 500,
                  color: getAgentColor(msg.agentName),
                }}>
                  {msg.agentEmoji} {msg.agentName}
                  {msg.round !== undefined && ` (第${msg.round}轮)`}
                </span>
                <span style={{ fontSize: 11, color: 'var(--text-muted)', marginLeft: 8 }}>
                  {formatTime(msg.timestamp)}
                </span>
              </div>
            )}

            {/* Reasoning Section - above the message bubble */}
            {msg.reasoning && (
              <div style={{ marginBottom: 8, width: '100%' }}>
                <button
                  onClick={() => toggleReasoning(msg.id)}
                  style={{
                    background: 'var(--chat-reasoning-btn-bg)',
                    border: '1px solid var(--chat-reasoning-btn-border)',
                    borderRadius: 8,
                    padding: '6px 12px',
                    fontSize: 12,
                    color: 'var(--chat-link-color)',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                    transition: 'all 0.2s',
                    fontWeight: 500,
                  }}
                  title="查看 Agent 的思考过程"
                >
                  🧠 思考过程
                  <span style={{
                    fontSize: 10,
                    transition: 'transform 0.2s',
                    transform: expandedReasoning[msg.id] ? 'rotate(180deg)' : 'rotate(0deg)',
                  }}>▼</span>
                </button>
                {expandedReasoning[msg.id] && (
                  <div style={{
                    marginTop: 6,
                    padding: '10px 14px',
                    background: 'var(--chat-reasoning-bg)',
                    borderRadius: 8,
                    fontSize: 12,
                    color: 'var(--text-secondary)',
                    whiteSpace: 'pre-wrap',
                    border: '1px solid var(--chat-reasoning-border)',
                    lineHeight: 1.6,
                    maxHeight: 200,
                    overflowY: 'auto',
                  }}>
                    {msg.reasoning.thinking_steps || msg.reasoning.decision_summary || '无详细推理步骤'}
                  </div>
                )}
              </div>
            )}

            {/* Message Bubble */}
            <div style={{
              background: msg.isUser ? 'var(--chat-msg-user-bg)' : 'var(--chat-msg-agent-bg)',
              color: msg.isUser ? 'var(--chat-msg-user-text)' : 'var(--chat-msg-agent-text)',
              padding: msg.isUser ? '10px 16px' : '12px 16px',
              borderRadius: 12,
              borderBottomLeftRadius: msg.isUser ? 12 : 4,
              borderBottomRightRadius: msg.isUser ? 4 : 12,
              boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
              border: !msg.isUser ? '1px solid var(--chat-msg-agent-border)' : 'none',
              maxWidth: '100%',
            }}>
              {msg.isUser ? (
                <div style={{
                  fontSize: 14,
                  lineHeight: 1.6,
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                }}>
                  {msg.content}
                </div>
              ) : (
                <div className="markdown-content" style={{
                  fontSize: 14,
                  lineHeight: 1.7,
                  color: 'var(--chat-msg-agent-text)',
                  whiteSpace: 'pre-line',
                }}>
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {msg.content}
                  </ReactMarkdown>
                </div>
              )}
            </div>

            {/* Inline HITL UI — compact */}
            {msg.hitlOptions && !msg.hitlResolved && (
              <div style={{ marginTop: 8, width: '100%', paddingLeft: 2 }}>
                {msg.hitlType === 'answer' ? (
                  /* answer: compact text input */
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    <div style={{ fontSize: 11, fontWeight: 600, color: '#f59e0b' }}>
                      ✏️ 请回答 · ESC 取消
                    </div>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <input
                        type="text"
                        value={hitlAnswerText}
                        onChange={(e) => setHitlAnswerText(e.target.value)}
                        onKeyDown={(e) => { if (e.key === 'Enter') handleHitlAnswer(); }}
                        placeholder="输入你的回答..."
                        autoFocus
                        style={{
                          flex: 1, padding: '5px 10px', borderRadius: 6,
                          border: '1.2px solid rgba(245, 158, 11, 0.25)',
                          background: 'var(--bg-card-hover)', color: 'var(--text-primary)',
                          fontSize: 12, outline: 'none',
                        }}
                      />
                      <button
                        onClick={handleHitlAnswer}
                        disabled={!hitlAnswerText.trim()}
                        style={{
                          padding: '5px 12px', borderRadius: 6, border: 'none',
                          background: hitlAnswerText.trim() ? '#f59e0b' : 'rgba(245, 158, 11, 0.12)',
                          color: hitlAnswerText.trim() ? '#fff' : 'rgba(245, 158, 11, 0.4)',
                          fontSize: 12, fontWeight: 600,
                          cursor: hitlAnswerText.trim() ? 'pointer' : 'not-allowed',
                        }}
                      >发送</button>
                    </div>
                  </div>
                ) : msg.hitlType === 'review' ? (
                  /* review: compact approve/reject */
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    <div style={{ fontSize: 11, fontWeight: 600, color: '#f59e0b' }}>
                      👀 审核 · ESC 取消
                    </div>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <button onClick={() => handleHitlReview(true)} style={{
                        flex: 1, padding: '5px', borderRadius: 6,
                        border: '1.2px solid #22c55e', background: 'rgba(34, 197, 94, 0.08)',
                        color: '#22c55e', fontSize: 12, fontWeight: 600, cursor: 'pointer',
                      }}>批准</button>
                      <button onClick={() => handleHitlReview(false)} style={{
                        flex: 1, padding: '5px', borderRadius: 6,
                        border: '1.2px solid #ef4444', background: 'rgba(239, 68, 68, 0.08)',
                        color: '#ef4444', fontSize: 12, fontWeight: 600, cursor: 'pointer',
                      }}>驳回</button>
                    </div>
                    <input
                      type="text" value={hitlReviewFeedback}
                      onChange={(e) => setHitlReviewFeedback(e.target.value)}
                      placeholder="可选：反馈意见..."
                      style={{
                        padding: '5px 10px', borderRadius: 6,
                        border: '1.2px solid var(--border-medium)',
                        background: 'var(--bg-card-hover)', color: 'var(--text-primary)',
                        fontSize: 12, outline: 'none',
                      }}
                    />
                  </div>
                ) : msg.hitlType === 'multi_select' ? (
                  /* multi_select: compact checkboxes + confirm */
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    <div style={{ fontSize: 11, fontWeight: 600, color: '#f59e0b', marginBottom: 2 }}>
                      ☑️ 可多选 · 选后点确认 · ESC 取消
                    </div>
                    {msg.hitlOptions.map((opt, idx) => {
                      const isSelected = multiSelectValues.includes(opt.value);
                      return (
                        <button
                          key={idx}
                          onClick={() => {
                            setMultiSelectValues(prev =>
                              prev.includes(opt.value)
                                ? prev.filter(v => v !== opt.value)
                                : [...prev, opt.value]
                            );
                          }}
                          style={{
                            width: '100%',
                            padding: '5px 10px',
                            borderRadius: 6,
                            border: isSelected ? '1.2px solid #f59e0b' : '1.2px solid rgba(245, 158, 11, 0.25)',
                            background: isSelected ? 'rgba(245, 158, 11, 0.12)' : 'rgba(245, 158, 11, 0.04)',
                            color: 'var(--text-primary)',
                            fontSize: 12,
                            fontWeight: isSelected ? 550 : 400,
                            cursor: 'pointer',
                            textAlign: 'left',
                            display: 'flex',
                            alignItems: 'center',
                            gap: 6,
                          }}
                        >
                          <span style={{
                            minWidth: 16, height: 16, borderRadius: 3,
                            border: `1.5px solid ${isSelected ? '#f59e0b' : 'rgba(245, 158, 11, 0.3)'}`,
                            background: isSelected ? '#f59e0b' : 'transparent',
                            color: '#fff',
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            fontSize: 10, fontWeight: 700, flexShrink: 0,
                          }}>
                            {isSelected ? '✓' : ''}
                          </span>
                          <div style={{ flex: 1 }}>
                            <div style={{ fontSize: 12, lineHeight: 1.3 }}>{opt.label}</div>
                            {opt.description && <div style={{ fontSize: 10, color: 'var(--text-dim)', marginTop: 1, lineHeight: 1.2 }}>{opt.description}</div>}
                          </div>
                        </button>
                      );
                    })}
                    <button
                      onClick={handleHitlMultiSelectConfirm}
                      disabled={multiSelectValues.length === 0}
                      style={{
                        padding: '6px 12px', borderRadius: 6, border: 'none',
                        background: multiSelectValues.length > 0 ? '#f59e0b' : 'rgba(245, 158, 11, 0.15)',
                        color: multiSelectValues.length > 0 ? '#fff' : 'rgba(245, 158, 11, 0.4)',
                        fontSize: 12, fontWeight: 600,
                        cursor: multiSelectValues.length > 0 ? 'pointer' : 'not-allowed',
                        marginTop: 2, alignSelf: 'flex-start',
                      }}
                    >
                      确认{multiSelectValues.length > 0 ? ` (${multiSelectValues.length})` : ''}
                    </button>
                  </div>
                ) : (
                  /* select (default): compact radio-style */
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    <div style={{ fontSize: 11, fontWeight: 600, color: '#f59e0b', marginBottom: 2 }}>
                      选择一个选项 · ESC 取消
                    </div>
                    {msg.hitlOptions.map((opt, idx) => (
                      <button
                        key={idx}
                        onClick={() => handleHitlSelect(opt.value)}
                        style={{
                          width: '100%',
                          padding: '5px 10px',
                          borderRadius: 6,
                          border: '1.2px solid rgba(245, 158, 11, 0.25)',
                          background: 'rgba(245, 158, 11, 0.04)',
                          color: 'var(--text-primary)',
                          fontSize: 12,
                          fontWeight: 450,
                          cursor: 'pointer',
                          transition: 'all 0.15s ease',
                          textAlign: 'left',
                          display: 'flex',
                          alignItems: 'center',
                          gap: 6,
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.borderColor = '#f59e0b';
                          e.currentTarget.style.background = 'rgba(245, 158, 11, 0.12)';
                          e.currentTarget.style.transform = 'translateX(3px)';
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.borderColor = 'rgba(245, 158, 11, 0.25)';
                          e.currentTarget.style.background = 'rgba(245, 158, 11, 0.04)';
                          e.currentTarget.style.transform = 'translateX(0)';
                        }}
                      >
                        <span style={{
                          minWidth: 16, height: 16, borderRadius: '50%',
                          background: 'rgba(245, 158, 11, 0.15)',
                          color: '#f59e0b',
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                          fontSize: 10, fontWeight: 600, flexShrink: 0,
                        }}>
                          {idx + 1}
                        </span>
                        <div style={{ flex: 1 }}>
                          <div style={{ fontSize: 12, lineHeight: 1.3 }}>{opt.label}</div>
                          {opt.description && <div style={{ fontSize: 10, color: 'var(--text-dim)', marginTop: 1, lineHeight: 1.2 }}>{opt.description}</div>}
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Resolved HITL: show what was chosen as a compact summary */}
            {msg.hitlResolved && msg.hitlResponse && (
              <div style={{
                marginTop: 8, fontSize: 12, color: '#f59e0b', fontWeight: 500,
                background: 'rgba(245, 158, 11, 0.06)',
                border: '1px solid rgba(245, 158, 11, 0.2)',
                borderRadius: 6, padding: '6px 10px',
              }}>
                <div style={{ marginBottom: 2 }}>✅ 已确认：</div>
                {msg.hitlResponse!.split('\n').map((line, i) => (
                  <div key={i} style={{ color: 'var(--text-primary)', paddingLeft: 14, lineHeight: 1.5 }}>
                    {line}
                  </div>
                ))}
              </div>
            )}

            {/* Time (user message) */}
            {msg.isUser && (
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4, paddingRight: 4 }}>
                {formatTime(msg.timestamp)}
              </div>
            )}
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div style={{
        padding: '16px 20px',
        background: 'var(--chat-header-bg)',
        borderTop: '1px solid var(--chat-msg-agent-border)',
      }}>
        <div style={{
          display: 'flex',
          gap: 12,
          alignItems: 'flex-end',
        }}>
          <div style={{ display: 'flex', gap: 4 }}>
            <button
              style={{
                width: 36,
                height: 36,
                borderRadius: 8,
                background: 'var(--bg-card-hover)',
                border: 'none',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 18,
              }}
              title="上传文件 (开发中)"
            >📎</button>
            <button
              style={{
                width: 36,
                height: 36,
                borderRadius: 8,
                background: 'var(--bg-card-hover)',
                border: 'none',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 18,
              }}
              title="表情 (开发中)"
            >😊</button>
          </div>

          <div style={{
            flex: 1,
            background: 'var(--chat-input-bg)',
            borderRadius: 12,
            border: '1px solid var(--chat-input-border)',
            padding: '10px 14px',
          }}>
            <input
              type="text"
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && handleSend()}
              placeholder={activeHitl
                ? activeHitl.hitl_type === 'answer' ? '请在上方回答区域输入...'
                : activeHitl.hitl_type === 'review' ? '请审核方案并做出决定...'
                : '选择选项或按 ESC 后自由输入...'
                : '输入消息...'}
              disabled={!isConnected || !!activeHitl}
              style={{
                width: '100%',
                background: 'transparent',
                border: 'none',
                outline: 'none',
                fontSize: 14,
                color: 'var(--text-primary)',
              }}
            />
          </div>

          <button
            onClick={handleSend}
            disabled={!inputText.trim() || !isConnected || !!activeHitl}
            style={{
              width: 40,
              height: 40,
              borderRadius: 10,
              background: (inputText.trim() && isConnected && !activeHitl) ? 'var(--chat-msg-user-bg)' : 'var(--chat-send-disabled-bg)',
              border: 'none',
              fontSize: 18,
              cursor: (inputText.trim() && isConnected && !activeHitl) ? 'pointer' : 'not-allowed',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
            title={
              activeHitl
                ? activeHitl.hitl_type === 'answer' ? '请在上方回答问题'
                : '请先处理待决策事项（按 ESC 取消）'
                : (inputText.trim() && isConnected) ? '发送消息' : '请先输入消息'
            }
          >
            {inputText.trim() && isConnected && !activeHitl ? '🚀' : '✨'}
          </button>
        </div>
      </div>
    </div>
    </>
  );
}

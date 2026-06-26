/** 讨论模式视图：自由多 Agent 对话，无 SOP Pipeline */
import { useState, useEffect, useRef, useCallback } from 'react';
import { sessionsApi } from '../../shared/api/sessions';
import type { SessionInfo } from '../../shared/types/session';
import { useSessionEvents } from './hooks/useSessionEvents';
import { useCollabEvents } from './hooks/useCollabEvents';
import { MessageBubble } from './MessageBubble';
import { OrchestrationCard } from './OrchestrationCard';
import { MemberPanel } from './MemberPanel';
import { WorkspacePanel } from './WorkspacePanel';
import { TracePanel } from './TracePanel';
import { CollaborationPhaseBar } from './CollaborationPhaseBar';
import { HITLInteractionCard } from './HITLInteractionCard';
import { CollabWorkspace } from './CollabWorkspace';
import type { ReasoningTrace } from '../../shared/types/session';
import type { HitlRequest } from '../../shared/types/collaboration';
import { api } from '../../shared/api/client';

// ── 协作模式配置 ──
const MODE_CONFIG: Record<string, { label: string; bg: string; color: string }> = {
  supervisor:  { label: '👑 Supervisor', bg: 'var(--blue-bg)',   color: 'var(--blue-400)' },
  swarm:       { label: '🐝 Swarm',      bg: 'var(--purple-bg)', color: 'var(--purple-400)' },
  round_robin: { label: '🔄 轮流发言',   bg: 'var(--green-bg)',  color: 'var(--green-400)' },
  custom_sop:  { label: '📋 自定义流程', bg: 'var(--gold-bg)',   color: 'var(--gold-400)' },
};
const getModeLabel = (mode?: string) => MODE_CONFIG[mode || '']?.label || '💬 讨论';
const modeBadgeStyle = (mode?: string): React.CSSProperties => {
  const c = MODE_CONFIG[mode || ''] || { bg: 'var(--bg-elevated)', color: 'var(--text-muted)' };
  return { padding: '2px 8px', borderRadius: 4, background: c.bg, color: c.color, border: `1px solid ${c.color}33`, fontSize: 10, fontWeight: 600 };
};

interface DiscussionViewProps {
  sessionId: string;
  teamId: string;
}

export function DiscussionView({ sessionId, teamId }: DiscussionViewProps) {
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [team, setTeam] = useState<{ collaboration_mode?: string; name?: string; members?: Array<{ agent_id: string; agent_name: string; role_name: string; role_icon?: string }> } | null>(null);
  const [input, setInput] = useState('');
  const [uploading, setUploading] = useState(false);
  const [mentionMenu, setMentionMenu] = useState<{ show: boolean; query: string; position: number } | null>(null);
  const [mentionedAgents, setMentionedAgents] = useState<string[]>([]);
  const [editingTitle, setEditingTitle] = useState(false);
  const [titleDraft, setTitleDraft] = useState('');
  const [viewMode, setViewMode] = useState<'chat' | 'workspace'>('chat');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const { messages, agentStatuses, traceEntries, connected, sendMessage, sendHitlResume, historyLoaded, addTaskToCard, orchestrationState, routingMode, routingAgentName } = useSessionEvents({
    sessionId,
  });

  // ── Collaboration state (PhaseBar + HITL cards) ──
  const collab = useCollabEvents();
  const [hitlRequest, setHitlRequest] = useState<HitlRequest | null>(null);

  // Listen for HITL events directly (more reliable than useCollabEvents)
  useEffect(() => {
    const handleHitl = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      setHitlRequest(detail as HitlRequest);
    };
    window.addEventListener('collab-hitl-request', handleHitl);
    return () => window.removeEventListener('collab-hitl-request', handleHitl);
  }, []);

  // 加载会话信息
  useEffect(() => {
    sessionsApi.get(sessionId).then(setSession).catch(() => {});
  }, [sessionId]);

  // 加载团队信息（包含成员）
  useEffect(() => {
    if (teamId) {
      api.get(`/api/v1/teams/${teamId}`)
        .then((t) => setTeam(t))
        .catch(() => {});
    }
  }, [teamId]);

  // 滚到底部
  useEffect(() => {
    if (historyLoaded) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'auto' });
    }
  }, [historyLoaded]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text) return;
    setInput('');
    setMentionedAgents([]);

    // If HITL is pending, send as hitl_resume instead of regular message
    if (hitlRequest) {
      sendHitlResume(text);
      setHitlRequest(null);
      return;
    }

    // `/task 标题` 命令：手动创建任务
    if (text.startsWith('/task ')) {
      const taskTitle = text.slice(6).trim();
      if (taskTitle) {
        try {
          const res = await api.post(`/api/v1/sessions/${sessionId}/tasks`, { title: taskTitle, priority: 'medium' });
          const newTask = res as { id: string; title: string; status: string };
          addTaskToCard({ id: newTask.id, title: newTask.title, status: newTask.status });
          sendMessage(`📋 已添加任务: **${taskTitle}**`);
        } catch {
          sendMessage(`❌ 添加任务失败: ${taskTitle}`);
        }
      }
      return;
    }

    // `/approve` and `/reject` pass through to collaboration engine
    // (handled by supervisor_node intent classifier)

    sendMessage(text, mentionedAgents);
  };

  // 处理输入框变化，检测 @ 符号
  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    setInput(value);

    // 检测 @ 符号
    const cursorPosition = e.target.selectionStart;
    const textBeforeCursor = value.substring(0, cursorPosition);
    const lastAtIndex = textBeforeCursor.lastIndexOf('@');

    if (lastAtIndex !== -1) {
      // 检查 @ 后面的文本（直到空格或结尾）
      const afterAt = textBeforeCursor.substring(lastAtIndex + 1);
      if (afterAt.length === 0 || !afterAt.includes(' ')) {
        // 显示 @ 菜单
        setMentionMenu({
          show: true,
          query: afterAt.toLowerCase(),
          position: lastAtIndex,
        });
        return;
      }
    }
    setMentionMenu(null);
  };

  // 选择 @ 的 Agent
  const handleSelectMention = (agentId: string, agentName: string) => {
    const currentInput = input;
    const position = mentionMenu?.position || 0;

    // 替换 @ 符号到光标位置的内容为 @name
    const before = currentInput.substring(0, position);
    const after = currentInput.substring(position + (mentionMenu?.query?.length || 0) + 1);
    const newText = `${before}@${agentName} ${after}`;

    setInput(newText);
    // 如果是 @all，使用特殊标识
    if (agentId === '__all__') {
      setMentionedAgents(['__all__']);
    } else {
      // 移除 __all__ 如果存在，添加新的 agent
      const filtered = mentionedAgents.filter(id => id !== '__all__');
      setMentionedAgents([...filtered, agentId]);
    }
    setMentionMenu(null);

    // 聚焦回输入框
    setTimeout(() => {
      const textarea = document.querySelector('textarea[style*="resize"]');
      if (textarea) {
        textarea.focus();
        // 设置光标位置到 @name 后面
        const newCursorPos = position + agentName.length + 2;
        (textarea as HTMLTextAreaElement).setSelectionRange(newCursorPos, newCursorPos);
      }
    }, 0);
  };

  // 过滤可 @ 的成员
  const filteredMembers = (() => {
    const members = (team?.members || []).filter(m =>
      m.agent_name.toLowerCase().includes(mentionMenu?.query || '')
    );
    // 如果查询是 "all" 或空，添加 @all 选项在顶部
    if (mentionMenu?.query === '' || mentionMenu?.query === 'all') {
      return [
        { agent_id: '__all__', agent_name: 'all', role_slot: '所有成员' },
        ...members,
      ];
    }
    return members;
  })();

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      await sessionsApi.uploadFile(sessionId, file);
      // 发送附件消息
      sendMessage(`📎 上传了文件: **${file.name}** (${(file.size / 1024).toFixed(1)}KB)`);
    } catch (err) {
      alert('上传失败: ' + String(err));
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  // 合并显示：历史消息 + 实时消息（去重：相同 id 不重复）
  const allMessages = [...messages];

  return (
    <div style={{ display: 'flex', height: '100%', position: 'relative', zIndex: 1 }}>
      {/* Main Chat Area */}
      <div style={{ display: 'flex', flexDirection: 'column', flex: 1, minWidth: 0 }}>
        {/* Header */}
        <div style={headerStyle}>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 15, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 10 }}>
              {editingTitle ? (
                <input
                  value={titleDraft}
                  onChange={e => setTitleDraft(e.target.value)}
                  onBlur={async () => {
                    setEditingTitle(false);
                    if (titleDraft.trim() && titleDraft !== session?.title) {
                      try {
                        await api.put(`/api/v1/sessions/${sessionId}`, { title: titleDraft.trim() });
                        setSession(prev => prev ? { ...prev, title: titleDraft.trim() } : prev);
                      } catch { /* ignore */ }
                    }
                  }}
                  onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}
                  autoFocus
                  style={{
                    fontSize: 15, fontWeight: 600, background: 'var(--bg-elevated)',
                    border: '1px solid var(--gold-400)', borderRadius: 4,
                    color: 'var(--text-primary)', padding: '2px 8px', outline: 'none',
                    width: Math.max(80, (titleDraft.length + 2) * 12),
                  }}
                />
              ) : (
                <span
                  onClick={() => { setTitleDraft(session?.title || '新对话'); setEditingTitle(true); }}
                  title="点击修改对话名称"
                  style={{ cursor: 'pointer', borderBottom: '1px dashed transparent', padding: '2px 4px' }}
                  onMouseEnter={e => (e.target as HTMLElement).style.borderBottomColor = 'var(--gold-400)'}
                  onMouseLeave={e => (e.target as HTMLElement).style.borderBottomColor = 'transparent'}
                >
                  {session?.title || '新对话'} ✎
                </span>
              )}
              {session?.team_name && (
                <span style={teamBadgeStyle}>{session.team_name}</span>
              )}
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 2, display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{
                width: 6, height: 6, borderRadius: '50%',
                background: connected ? 'var(--green-400)' : 'var(--red-400)',
                display: 'inline-block',
              }} />
              {connected ? '已连接' : '连接中...'} ·
              <span style={modeBadgeStyle(team?.collaboration_mode)}>
                {getModeLabel(team?.collaboration_mode)}
              </span>
              {/* ── 实时路由模式标识 ── */}
              {routingMode && (
                <span style={routingMode === 'multi_agent' ? multiAgentBadgeStyle : singleAgentBadgeStyle}>
                  {routingMode === 'multi_agent' ? `🔄 多Agent协作` : `🤖 ${routingAgentName || '单Agent'}`}
                </span>
              )}
              · {allMessages.length} 条消息
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {/* View mode toggle */}
            <div style={viewToggleContainerStyle}>
              <button
                onClick={() => setViewMode('chat')}
                style={viewToggleBtnStyle(viewMode === 'chat')}
              >💬 聊天</button>
              <button
                onClick={() => setViewMode('workspace')}
                style={viewToggleBtnStyle(viewMode === 'workspace')}
              >🌳 工作区</button>
            </div>
            {session?.workspace_path && (
              <span style={{ fontSize: 10, color: 'var(--text-dim)', fontFamily: 'var(--font-mono)', display: 'flex', alignItems: 'center', gap: 4 }}>
                📂 {session.workspace_path}
              </span>
            )}
          </div>
        </div>

        {/* Collaboration Phase Bar */}
        {collab.phases.length > 0 && (
          <CollaborationPhaseBar
            phases={collab.phases}
            currentPhase={collab.currentPhase}
          />
        )}

        {/* Content: Chat or Workspace */}
        {/* 🌳 Workspace — always mounted to receive events, CSS controls visibility */}
        <div style={{ flex: 1, overflow: 'hidden', display: viewMode === 'workspace' ? 'flex' : 'none' }}>
          <CollabWorkspace mockMode={false} sessionId={sessionId} />
        </div>
        {/* 💬 Chat Messages */}
        <div style={{ display: viewMode === 'workspace' ? 'none' : 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden' }}>
          {/* ── Sticky Orchestration Pipeline Bar (multi-agent mode) ── */}
          {orchestrationState.active && (
            <div style={orchestrationBarStyle}>
                <OrchestrationCard state={orchestrationState} />
              </div>
            )}

            <div style={{ flex: 1, overflowY: 'auto', padding: '16px 20px' }}>
              {allMessages.length === 0 && !historyLoaded && (
                <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-dim)', fontSize: 13 }}>
                  加载中...
                </div>
              )}
              {allMessages.length === 0 && historyLoaded && (
                <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-dim)', fontSize: 13 }}>
                  💬 开始对话吧
                </div>
              )}
              {allMessages.map((msg, i) => (
                <MessageBubble
                  key={msg.id}
                  msg={msg}
                  reasoning={(msg as { reasoning?: unknown }).reasoning as ReasoningTrace | undefined}
                  questions={(msg as { questions?: unknown }).questions as Array<{text: string; type: string}> | undefined}
                  defaultThinkingOpen={i === allMessages.length - 1 && !msg.id.startsWith('stream_')}
                />
              ))}

              {/* HITL Interaction Card — Claude Code style */}
              {hitlRequest && (
                <div style={{ padding: '8px 0', animation: 'slideIn 0.35s ease' }}>
                  <HITLInteractionCard
                    request={hitlRequest}
                    onRespond={(value) => {
                      if (value === 'approve') {
                        setHitlRequest(null);
                        sendHitlResume('确认');
                      } else if (value === 'reject') {
                        setHitlRequest(null);
                        sendHitlResume('不对，重新来');
                      } else if (value === 'answer') {
                        // Don't dismiss card — focus input for user to type answer
                        setInput('');
                        setTimeout(() => {
                          const inputEl = document.querySelector('textarea') as HTMLTextAreaElement;
                          if (inputEl) {
                            inputEl.placeholder = '输入你的回答... (Enter 发送)';
                            inputEl.focus();
                          }
                        }, 100);
                        return; // Keep hitlRequest active so handleSend knows to send hitl_resume
                      } else if (value === 'skip') {
                        setHitlRequest(null);
                        sendHitlResume('取消');
                      } else if (value === 'modify') {
                        // Keep card, focus input for modifications
                        setInput('');
                        setTimeout(() => {
                          const inputEl = document.querySelector('textarea') as HTMLTextAreaElement;
                          if (inputEl) {
                            inputEl.placeholder = 'Tell me what to change...';
                            inputEl.focus();
                          }
                        }, 100);
                        return; // Keep hitlRequest active
                      } else {
                        setHitlRequest(null);
                        sendHitlResume(value);
                      }
                    }}
                  />
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>

            {/* Input */}
            <div style={{ ...inputContainerStyle, position: 'relative' }}>
              <label style={attachBtnStyle} title="上传附件">
                📎
                <input
                  ref={fileInputRef}
                  type="file"
                  style={{ display: 'none' }}
                  onChange={handleFileUpload}
                  disabled={uploading}
                />
              </label>
          <textarea
            ref={textareaRef}
            style={inputStyle}
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder="输入消息... (@ 成员名指定回复，Enter 发送，Shift+Enter 换行)"
            rows={2}
          />
          <button
            style={sendBtnStyle}
            onClick={handleSend}
            disabled={!input.trim() || !connected}
          >
            发送
          </button>

          {/* @ 提及菜单 */}
          {mentionMenu?.show && (
            <>
              <div
                style={{
                  position: 'fixed', inset: 0, zIndex: 10,
                }}
                onClick={() => setMentionMenu(null)}
              />
              <div
                style={{
                  position: 'absolute',
                  bottom: '100%',
                  left: 0,
                  marginBottom: 8,
                  background: 'var(--bg-card)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: 8,
                  boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
                  padding: '6px 0',
                  minWidth: 200,
                  maxWidth: 280,
                  zIndex: 11,
                  maxHeight: 200,
                  overflowY: 'auto',
                }}
              >
                {filteredMembers.length === 0 ? (
                  <div style={{ padding: '8px 16px', fontSize: 12, color: 'var(--text-dim)' }}>
                    没有匹配的成员
                  </div>
                ) : (
                  filteredMembers.map((m) => (
                    <div
                      key={m.agent_id}
                      onClick={() => handleSelectMention(m.agent_id, m.agent_name)}
                      style={{
                        padding: '8px 16px',
                        fontSize: 12,
                        cursor: 'pointer',
                        color: 'var(--text-primary)',
                        display: 'flex',
                        alignItems: 'center',
                        gap: 8,
                      }}
                      onMouseEnter={(e) => e.currentTarget.style.background = 'var(--bg-hover)'}
                      onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
                    >
                      <span style={{ fontSize: 14 }}>🤖</span>
                      <div>
                        <div style={{ fontWeight: 500 }}>{m.agent_name}</div>
                        <div style={{ fontSize: 10, color: 'var(--text-dim)' }}>{m.role_slot}</div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </>
          )}
        </div>
        </div>
      </div>

      {/* Right Sidebar: Tabbed Members + Workspace, resizable */}
      {RightSidebar({ teamId, sessionId, session, agentStatuses, traceEntries })}
    </div>
  );
}

// ── Styles ──

const headerStyle: React.CSSProperties = {
  padding: '14px 20px', borderBottom: '1px solid var(--border-subtle)',
  display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
  background: 'var(--bg-card)',
};

const teamBadgeStyle: React.CSSProperties = {
  fontSize: 10, fontWeight: 500, padding: '2px 8px', borderRadius: 10,
  background: 'var(--gold-bg)', color: 'var(--gold-400)',
  border: '1px solid var(--gold-border)',
};

// ── Routing mode badge styles ──

const multiAgentBadgeStyle: React.CSSProperties = {
  padding: '2px 8px', borderRadius: 4,
  background: 'rgba(139,92,246,0.12)', color: '#a78bfa',
  border: '1px solid rgba(139,92,246,0.25)',
  fontSize: 10, fontWeight: 600,
  animation: 'blink 2s step-end infinite',
};

const singleAgentBadgeStyle: React.CSSProperties = {
  padding: '2px 8px', borderRadius: 4,
  background: 'rgba(16,185,129,0.1)', color: '#34d399',
  border: '1px solid rgba(16,185,129,0.2)',
  fontSize: 10, fontWeight: 600,
};

// ── Sticky orchestration bar (pinned below header during multi-agent) ──

const orchestrationBarStyle: React.CSSProperties = {
  flexShrink: 0,
  borderBottom: '1px solid var(--border-subtle)',
  background: 'var(--bg-card)',
  zIndex: 2,
};

// ── View toggle styles ──

const viewToggleContainerStyle: React.CSSProperties = {
  display: 'flex',
  background: 'var(--bg-elevated)',
  borderRadius: 6,
  border: '1px solid var(--border)',
  overflow: 'hidden',
};

const viewToggleBtnStyle = (active: boolean): React.CSSProperties => ({
  padding: '3px 10px',
  fontSize: 11,
  fontWeight: active ? 600 : 400,
  border: 'none',
  background: active ? 'var(--bg-hover)' : 'transparent',
  color: active ? 'var(--text-primary)' : 'var(--text-dim)',
  cursor: 'pointer',
  transition: 'all 0.15s',
});

// ── 右侧可拖拽 Tab 侧边栏 ──

function RightSidebar({ teamId, sessionId, session, agentStatuses, traceEntries }: {
  teamId: string; sessionId: string; session: SessionInfo | null; agentStatuses: Record<string, any>;
  traceEntries: import('../../shared/types/session').TraceEntry[];
}) {
  const [tab, setTab] = useState<'members' | 'files' | 'trace'>('members');
  const [width, setWidth] = useState(240);
  const dragging = useRef(false);

  const onMouseDown = (e: React.MouseEvent) => {
    e.preventDefault();
    dragging.current = true;
    const startX = e.clientX;
    const startW = width;
    const onMove = (ev: MouseEvent) => {
      if (!dragging.current) return;
      const newW = Math.max(180, Math.min(500, startW - (ev.clientX - startX)));
      setWidth(newW);
    };
    const onUp = () => { dragging.current = false; document.removeEventListener('mousemove', onMove); document.removeEventListener('mouseup', onUp); };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  };

  return (
    <div style={{ width, flexShrink: 0, display: 'flex', position: 'relative' }}>
      <div
        onMouseDown={onMouseDown}
        style={{
          width: 4, cursor: 'col-resize', background: 'transparent',
          transition: 'background 0.15s', flexShrink: 0,
          borderLeft: '1px solid var(--border-subtle)',
        }}
        onMouseEnter={(e) => e.currentTarget.style.background = 'var(--gold-400)'}
        onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
      />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: 'var(--bg-base)', overflow: 'hidden' }}>
        <div style={{ display: 'flex', borderBottom: '1px solid var(--border-subtle)' }}>
          <button onClick={() => setTab('members')} style={tabBtnStyle(tab === 'members')}>👥 成员</button>
          <button onClick={() => setTab('files')} style={tabBtnStyle(tab === 'files')}>📁 文件</button>
          <button onClick={() => setTab('trace')} style={tabBtnStyle(tab === 'trace')}>📋 上下文</button>
        </div>
        <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          {tab === 'members' ? (
            <MemberPanel teamId={teamId} memberCount={session?.message_count || 0} onCountChange={() => {}} agentStatuses={agentStatuses} />
          ) : tab === 'files' ? (
            <WorkspacePanel sessionId={sessionId} workspacePath={session?.workspace_path || undefined} />
          ) : (
            <TracePanel traceEntries={traceEntries} sessionId={sessionId} />
          )}
        </div>
      </div>
    </div>
  );
}

const inputContainerStyle: React.CSSProperties = {
  padding: '12px 20px', borderTop: '1px solid var(--border-subtle)',
  background: 'var(--bg-card)', display: 'flex', gap: 10, alignItems: 'flex-end',
};

const inputStyle: React.CSSProperties = {
  flex: 1, padding: '10px 14px', borderRadius: 10, resize: 'none',
  background: 'var(--bg-elevated)', border: '1px solid var(--border-medium)',
  color: 'var(--text-primary)', fontSize: 13, fontFamily: 'var(--font-body)',
  outline: 'none', lineHeight: 1.5,
};

const attachBtnStyle: React.CSSProperties = {
  padding: '10px 8px', fontSize: 18, cursor: 'pointer',
  color: 'var(--text-muted)', display: 'flex', alignItems: 'center',
  borderRadius: 8, transition: 'color 0.15s', flexShrink: 0,
};

const sendBtnStyle: React.CSSProperties = {
  padding: '10px 18px', borderRadius: 10, fontFamily: 'var(--font-body)',
  fontSize: 13, fontWeight: 500, cursor: 'pointer', border: 'none',
  background: 'linear-gradient(135deg, var(--gold-500), #d97706)',
  color: '#0a0f1e', flexShrink: 0,
};

const tabBtnStyle = (active: boolean): React.CSSProperties => ({
  flex: 1, padding: '8px 0', fontSize: 11, fontWeight: active ? 600 : 400,
  background: active ? 'var(--bg-card)' : 'transparent', border: 'none', cursor: 'pointer',
  color: active ? 'var(--gold-400)' : 'var(--text-dim)',
  borderBottom: active ? '2px solid var(--gold-400)' : '2px solid transparent',
  transition: 'all 0.15s',
});

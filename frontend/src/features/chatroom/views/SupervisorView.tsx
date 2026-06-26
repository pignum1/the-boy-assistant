import { useState, useRef, useCallback, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { api, getWsUrl } from '../../../shared/api/client';
import { MembersPanel, WorkspaceSlideover, TaskTreePanel } from '../components/ChatPanels';

interface ChatMsg {
  id: string;
  type: 'user' | 'agent' | 'task_dag' | 'hitl' | 'system' | 'hitl_answer';
  agentName?: string;
  agentEmoji?: string;
  content: string;
  reasoning?: string;
  tasks?: SupervisorTask[];
  hitlMessage?: string;
  hitlOptions?: HitlOption[];
  hitlId?: string;
  hitlType?: string;
  // Claude Code-style Q&A record of a user's HITL answer
  hitlTitle?: string;
  hitlQa?: Array<{ q: string; a: string }>;
  timestamp: number;
}

interface SupervisorTask {
  id: string;
  agentId: string;
  agentName: string;
  agentEmoji: string;
  task: string;
  status: 'pending' | 'running' | 'done' | 'failed';
  result?: string;
  reasoning?: {
    thinking_steps?: string;
    decision_summary?: string;
    tool_calls?: any;
  };
  startedAt?: number;
  endedAt?: number;
}

interface LeaderAnalysis {
  taskId: string;
  analysis: string;
  tasks: SupervisorTask[];
  reasoning?: string;
}

const ROLE_NAME_MAP: Record<string, string> = {
  pm: '产品经理', product_manager: '产品经理',
  architect: '架构师', backend_dev: '后端工程师', frontend_dev: '前端工程师',
  tester: '测试员', ui_designer: 'UI设计师', devops: '部署运维',
};

function getRoleEmoji(role: string): string {
  const r = role.toLowerCase();
  if (r.includes('架构') || r.includes('architect')) return '🏗';
  if (r.includes('后端') || r.includes('backend')) return '⚙';
  if (r.includes('前端') || r.includes('frontend')) return '💻';
  if (r.includes('测试') || r.includes('test') || r.includes('qa')) return '🧪';
  if (r.includes('ui') || r.includes('设计') || r.includes('design')) return '🎨';
  if (r.includes('运维') || r.includes('devops') || r.includes('部署')) return '🚀';
  if (r.includes('产品') || r.includes('pm') || r.includes('product')) return '📋';
  if (r.includes('supervisor') || r.includes('主管') || r.includes('leader')) return '👑';
  return '🤖';
}

function getRoleDisplayName(role: string): string {
  return ROLE_NAME_MAP[role] || role;
}

// Reverse map: Chinese display name → role id, for matching task_status
// (the LLM sometimes emits the Chinese name as role_name instead of the id).
const NAME_TO_ROLE_ID: Record<string, string> = Object.entries(ROLE_NAME_MAP)
  .reduce((acc, [id, cn]) => { acc[cn] = id; return acc; }, {});

/** Normalize any role/agent string to a canonical lowercase role id.
 *  Handles: "backend_dev", "后端工程师", "后端工程师-Agent", "Backend". */
function normalizeRoleKey(s: string): string {
  if (!s) return '';
  let v = s.replace(/-Agent$/i, '').replace(/-agent$/i, '').trim();
  // Direct id
  if (ROLE_NAME_MAP[v]) return v.toLowerCase();
  // Chinese name → id
  if (NAME_TO_ROLE_ID[v]) return NAME_TO_ROLE_ID[v].toLowerCase();
  // Fuzzy: substring match against known ids / chinese names
  for (const [id, cn] of Object.entries(ROLE_NAME_MAP)) {
    if (v.includes(cn) || v.toLowerCase().includes(id)) return id.toLowerCase();
  }
  return v.toLowerCase();
}

interface Props {
  sessionId: string;
  teamId: string;
}

export function SupervisorView({ sessionId, teamId }: Props) {
  const [userInput, setUserInput] = useState('');
  const [savedUserMsg, setSavedUserMsg] = useState('');
  const [chatMessages, setChatMessages] = useState<ChatMsg[]>([]);
  const [currentAnalysis, setCurrentAnalysis] = useState<LeaderAnalysis | null>(null);
  const [history, setHistory] = useState<Array<{
    userMessage: string;
    analysis: LeaderAnalysis;
  }>>([]);
  const [expandedReasoning, setExpandedReasoning] = useState<Record<string, boolean>>({});
  const [expandedResults, setExpandedResults] = useState<Record<string, boolean>>({});
  const [expandedTasks, setExpandedTasks] = useState<Record<string, boolean>>({});
  const [isConnected, setIsConnected] = useState(false);
  const [executionState, setExecutionState] = useState<'idle' | 'thinking' | 'executing' | 'hitl_pending'>('idle');
  const scrollRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const handleMessageRef = useRef<(data: any) => void>(() => {});

  // ── Team members ──
  const [members, setMembers] = useState<Array<{ id: string; agent_id: string; agent_name: string; role_name: string; role_icon: string; status: string }>>([]);
  const [showMembers, setShowMembers] = useState(false);
  const [showWorkspace, setShowWorkspace] = useState(false);
  const [showTaskTree, setShowTaskTree] = useState(false);
  const [workspacePath, setWorkspacePath] = useState('');
  const [agentStatuses, setAgentStatuses] = useState<Record<string, { status: string; summary: string }>>({});

  // ── Persistent task tree (phase-structured) ──
  interface TaskPhase { name: string; tasks: SupervisorTask[]; }
  const [taskPhases, setTaskPhases] = useState<TaskPhase[]>([]);

  // ── HITL state (inline card style, matching SwarmView) ──
  const [activeHitl, setActiveHitl] = useState<{
    id: string; type: string; message: string; options: Array<{ label: string; value: string; description?: string }>;
  } | null>(null);
  const [selectedHitlValue, setSelectedHitlValue] = useState<string | null>(null);

  // Load session messages on mount to restore chat history
  useEffect(() => {
    api.get<{ messages: Array<{ role: string; content: string; metadata?: any; created_at: string }> }>(
      `/api/v1/sessions/${sessionId}/messages`
    )
      .then(data => {
        const msgs: ChatMsg[] = [];
        (data.messages || []).forEach((m, i) => {
          const ts = new Date(m.created_at).getTime();
          if (m.role === 'user') {
            msgs.push({ id: `hist-u-${i}`, type: 'user', content: m.content, timestamp: ts });
          } else if (m.role === 'assistant') {
            const agent = m.metadata?.agent || 'Supervisor';
            msgs.push({
              id: `hist-a-${i}`, type: 'agent', agentName: agent,
              agentEmoji: getRoleEmoji(agent), content: m.content, timestamp: ts,
            });
          }
        });
        if (msgs.length > 0) setChatMessages(msgs);
      })
      .catch(() => {});
  }, [sessionId]);

  // Load workspace path
  useEffect(() => {
    api.get<{ workspace_path?: string }>(`/api/v1/sessions/${sessionId}`)
      .then(s => { if (s.workspace_path) setWorkspacePath(s.workspace_path); })
      .catch(() => {});
  }, [sessionId]);

  // Restore task tree from persisted SessionTask (survives page refresh —
  // the live task_dag WS event is never re-sent on reload).
  useEffect(() => {
    if (!sessionId) return;
    api.get<{ tasks: Array<{ title: string; status: string; assigned_agent_name?: string }> }>(
      `/api/v1/sessions/${sessionId}/tasks`
    )
      .then(data => {
        const tasks = data.tasks || [];
        if (!tasks.length) return;
        const PLANNER_ROLES = new Set(['pm', 'product_manager', 'architect', '产品经理', '架构师']);
        const phaseTasks: SupervisorTask[] = tasks.map((t, i) => {
          const role = t.assigned_agent_name || '';
          const isPlanner = PLANNER_ROLES.has(role) || PLANNER_ROLES.has(normalizeRoleKey(role));
          return {
            id: `restored-${i}`,
            agentId: role,
            agentName: getRoleDisplayName(role) || role,
            agentEmoji: getRoleEmoji(role),
            task: t.title,
            status: (t.status === 'done' ? 'done' : isPlanner ? 'done' : 'pending') as SupervisorTask['status'],
          };
        });
        if (phaseTasks.length) {
          setTaskPhases([{ name: '任务进度', tasks: phaseTasks }]);
        }
      })
      .catch(() => {});
  }, [sessionId]);

  // Load team members
  useEffect(() => {
    api.get<{ members: Array<{ id: string; agent_id: string; agent_name: string; role_name: string; role_icon?: string }> }>(
      `/api/v1/teams/${teamId}`
    )
      .then(team => {
        const loaded = (team.members || []).map(m => ({
          id: m.agent_id,
          agent_id: m.agent_id,
          agent_name: m.agent_name,
          role_name: m.role_name,
          role_icon: m.role_icon || '🤖',
          status: 'idle',
        }));
        setMembers(loaded);
      })
      .catch(() => {});
  }, [teamId]);

  // WebSocket connection
  useEffect(() => {
    const wsUrl = getWsUrl(`/ws/sessions/${sessionId}`);
    console.log('[SupervisorView] Connecting WebSocket to:', wsUrl);
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('[SupervisorView] WebSocket connected');
      setIsConnected(true);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        console.log('[SupervisorView] WS msg:', data.type, data.payload?.agent_name || '');
        handleMessageRef.current(data);
      } catch (e) {
        console.error('Failed to parse WebSocket message:', e);
      }
    };

    ws.onclose = () => {
      console.log('[SupervisorView] WebSocket disconnected');
      setIsConnected(false);
    };

    ws.onerror = (error) => {
      console.error('[SupervisorView] WebSocket error:', error);
    };

    return () => {
      ws.close();
    };
  }, [sessionId]);

  const addMsg = useCallback((msg: ChatMsg) => {
    setChatMessages(prev => [...prev, msg]);
  }, []);

  const handleMessage = useCallback((data: any) => {
    const p = data.payload || data;
    const ts = Date.now();
    switch (data.type) {
      case 'routing_decision':
        setExecutionState('thinking');
        break;

      case 'task_dag':
        setExecutionState('executing');
        if (selectedHitlValue) { setActiveHitl(null); setSelectedHitlValue(null); }
        if (p.phases) {
          // Planner roles (PM/architect) produce the plan itself during M1/M4,
          // which is already done by the time the task_dag is emitted. They do
          // NOT run through m6_execute_worker, so mark their tasks done here —
          // otherwise design-phase tasks stay "pending" forever.
          const PLANNER_ROLES = new Set(['pm', 'product_manager', 'architect']);
          setTaskPhases(prev => {
            const existingIds = new Set(prev.flatMap(ph => ph.tasks.map(t => t.id)));
            const newPhases: TaskPhase[] = [];
            p.phases.forEach((phase: any) => {
              const phaseTasks: SupervisorTask[] = [];
              phase.tasks?.forEach((task: any) => {
                const tid = task.id || `t-${ts}-${Math.random().toString(36).slice(2,6)}`;
                if (existingIds.has(tid)) return;
                existingIds.add(tid);
                const role = task.assigned_role || task.agent_name || '';
                const roleKey = normalizeRoleKey(role);
                const isPlanner = PLANNER_ROLES.has(roleKey);
                phaseTasks.push({
                  id: tid,
                  agentId: task.agent_id || role,
                  agentName: getRoleDisplayName(role) || role,
                  agentEmoji: task.agent_emoji || getRoleEmoji(role),
                  task: task.name || task.title || task.goal || '',
                  status: isPlanner ? 'done' : 'pending',
                });
              });
              if (phaseTasks.length > 0) {
                newPhases.push({ name: phase.name || `阶段 ${newPhases.length + 1}`, tasks: phaseTasks });
              }
            });
            return [...prev, ...newPhases];
          });
        }
        break;

      case 'task_status': {
        const agentName = p.agent_name || p.agent || '';
        const role = p.role || '';
        // Backend worker status is "completed"; the tree counts 'done'.
        const mappedStatus: SupervisorTask['status'] =
          p.status === 'completed' ? 'done'
          : p.status === 'running' ? 'running'
          : p.status === 'failed' ? 'failed'
          : p.status === 'done' ? 'done' : 'pending';
        setAgentStatuses(prev => ({ ...prev, [agentName || role]: { status: p.status, summary: p.summary || '' } }));
        setMembers(prev => prev.map(m =>
          m.agent_name === agentName ? { ...m, status: mappedStatus === 'done' ? 'idle' : mappedStatus } : m
        ));
        // Update task tree: a worker completion resolves ALL of that role's
        // pending tasks (delegation is coarser than the architect's task_dag).
        // Match robustly across role-id / Chinese-name / "-Agent" forms.
        const statusRoleKey = normalizeRoleKey(role || agentName);
        setTaskPhases(prev => prev.map(ph => ({
          ...ph,
          tasks: ph.tasks.map(t => {
            const taskRoleKey = normalizeRoleKey(t.agentId || t.agentName);
            const sameRole = statusRoleKey && taskRoleKey && taskRoleKey === statusRoleKey;
            const sameTask = t.id === p.task_id;
            if ((sameRole || sameTask) && t.status !== 'done') {
              return { ...t, status: mappedStatus };
            }
            return t;
          }),
        })));
        break;
      }

      case 'agent_message': {
        const agent = p.agent || p.agent_name || '';
        const content = p.content || '';
        // Suppress pipeline-orchestration noise. These "agents" are never real —
        // internal node names (委派验证/系统/调度器) or raw role ids (pm/architect).
        // Real worker/PM/architect output always carries a human agent name
        // (产品经理-Agent, 架构师-Agent, …) and is kept.
        const INTERNAL_AGENTS = new Set([
          'system', 'System', '系统', '调度器', '委派验证', '委派验证器', '委派器',
          'Leader', 'Supervisor', 'worker', 'Worker',
        ]);
        const RAW_ROLE_IDS = new Set([
          'pm', 'architect', 'backend_dev', 'frontend_dev', 'tester', 'devops', 'ui_designer',
          'product_manager',
        ]);
        const isInternal =
          INTERNAL_AGENTS.has(agent) ||
          RAW_ROLE_IDS.has(agent) ||
          !agent;
        if (isInternal) break;
        addMsg({
          id: `msg-${ts}-${Math.random().toString(36).slice(2,6)}`, type: 'agent', agentName: agent,
          agentEmoji: getRoleEmoji(agent),
          content, timestamp: ts,
        });
        break;
      }

      case 'reasoning_complete': {
        const agentName = p.agent || '';
        const reasoningText = p.thinking_steps || p.decision_summary || '';
        if (agentName && reasoningText) {
          addMsg({
            id: `reason-${ts}-${Math.random().toString(36).slice(2,6)}`, type: 'agent', agentName,
            agentEmoji: getRoleEmoji(agentName),
            content: '', reasoning: reasoningText, timestamp: ts,
          });
        }
        break;
      }

      case 'message_complete':
        setExecutionState('idle');
        // Dismiss selected HITL card
        if (selectedHitlValue) {
          setActiveHitl(null);
          setSelectedHitlValue(null);
        }
        break;

      case 'hitl_notification':
      case 'hitl_request': {
        const payload = data.payload || data;
        setExecutionState('hitl_pending');
        setSelectedHitlValue(null);
        setActiveHitl({
          id: payload.hitl_id || `hitl-${ts}`,
          type: payload.type || payload.hitl_type || 'confirmation',
          message: payload.message || '',
          options: payload.options || [
            { label: '✅ 确认', value: 'approve' },
            { label: '✎ 修改', value: 'modify' },
            { label: '✗ 取消', value: 'reject' },
          ],
        });
        break;
      }

      case 'agent_status': {
        const agentName = p.agent_name || p.agent || data.source || '';
        const status = p.status;
        const summary = p.summary || '';
        // Track agent status for member panel
        if (agentName) {
          setAgentStatuses(prev => ({ ...prev, [agentName]: { status, summary } }));
          setMembers(prev => prev.map(m =>
            m.agent_name === agentName || m.role_name === agentName
              ? { ...m, status: status === 'done' ? 'idle' : status }
              : m
          ));
        }
        if (status === 'thinking' || status === 'executing') {
          setExecutionState(status === 'thinking' ? 'thinking' : 'executing');
        }
        // agent_status is transient (thinking/done indicators) — tracked via
        // executionState + member panel, NOT rendered as chat bubbles. Real agent
        // content arrives via agent_message events. (Pipeline nodes spam these.)
        break;
      }

      case 'thinking_update':
        setExecutionState('thinking');
        break;

      case 'execution_state':
        if (p.state === 'idle') setExecutionState('idle');
        break;

      case 'error':
        console.error('Server error:', data.payload);
        setExecutionState('idle');
        break;
    }
  }, [addMsg]);

  // Keep handleMessageRef in sync to avoid stale closure in WebSocket onmessage
  handleMessageRef.current = handleMessage;

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages, activeHitl]);

  const toggleReasoning = useCallback((id: string) => {
    setExpandedReasoning(prev => ({ ...prev, [id]: !prev[id] }));
  }, []);

  const toggleResult = useCallback((id: string) => {
    setExpandedResults(prev => ({ ...prev, [id]: !prev[id] }));
  }, []);

  const toggleTasks = useCallback((id: string) => {
    setExpandedTasks(prev => ({ ...prev, [id]: !prev[id] }));
  }, []);

  const handleSubmit = useCallback(() => {
    if (!userInput.trim() || !wsRef.current) return;

    const input = userInput;
    setUserInput('');
    setChatMessages([]);
    setTaskPhases([]); // Clear task tree

    // Add user message to chat
    const ts = Date.now();
    addMsg({ id: `user-${ts}`, type: 'user', content: input, timestamp: ts });

    // Send via WebSocket
    wsRef.current.send(JSON.stringify({
      type: 'chat',
      message: input,
    }));
  }, [userInput, addMsg]);

  const HITL_LABELS: Record<string, string> = {
    approve: '✅ 确认方案',
    force_confirm: '✅ 确认并继续',
    reject: '✗ 拒绝',
    cancel: '✗ 取消',
    modify: '✎ 需要修改',
    answer: '💬 补充说明',
  };

  const handleHitlResponse = useCallback((value: string) => {
    if (!wsRef.current || !activeHitl || selectedHitlValue) return;

    // Highlight selection and keep card visible
    setSelectedHitlValue(value);
    setExecutionState('thinking');

    // Send response immediately
    wsRef.current.send(JSON.stringify({
      type: 'hitl_resume',
      hitl_id: activeHitl.id,
      hitl_type: activeHitl.type,
      values: [value],
      response: value,
    }));

    const selectedOpt = activeHitl.options.find(o => o.value === value);
    const answerLabel = selectedOpt?.label || HITL_LABELS[value] || value;

    // Build a Claude Code-style Q&A record of what was asked → answered.
    const isConfirm = activeHitl.type === 'confirmation';
    const questionShort = isConfirm
      ? '确认执行方案'
      : (activeHitl.message || '待确认').replace(/\s+/g, ' ').trim().slice(0, 60);
    const title = isConfirm ? '用户已确认' : '用户已回答';

    addMsg({
      id: `hitl-resp-${Date.now()}`, type: 'hitl_answer',
      content: '',
      hitlTitle: title,
      hitlQa: [{ q: questionShort, a: answerLabel }],
      timestamp: Date.now(),
    });
    // NOTE: activeHitl stays until next message_complete or new hitl
  }, [activeHitl, selectedHitlValue, addMsg]);

  // ESC key → approve HITL
  useEffect(() => {
    if (!activeHitl) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') handleHitlResponse('approve');
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [activeHitl, handleHitlResponse]);

  const formatTime = (timestamp?: number) => {
    if (!timestamp) return '';
    const date = new Date(timestamp);
    return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  };

  const getStatusColor = (status: SupervisorTask['status']) => {
    switch (status) {
      case 'pending': return '#9ca3af';
      case 'running': return '#3b82f6';
      case 'done': return '#10b981';
      case 'failed': return '#ef4444';
    }
  };

  const getStatusText = (status: SupervisorTask['status']) => {
    switch (status) {
      case 'pending': return '待执行';
      case 'running': return '进行中';
      case 'done': return '已完成';
      case 'failed': return '失败';
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: 'var(--chat-bg)' }}>
      <style>{`
        .markdown-content h1 { font-size: 16px; font-weight: 700; margin: 8px 0 4px; color: var(--chat-msg-agent-text); }
        .markdown-content h2 { font-size: 14px; font-weight: 650; margin: 6px 0 3px; color: var(--chat-msg-agent-text); }
        .markdown-content h3 { font-size: 13px; font-weight: 600; margin: 4px 0 2px; color: var(--chat-msg-agent-text); }
        .markdown-content p { margin: 2px 0 6px; }
        .markdown-content ul, .markdown-content ol { margin: 2px 0; padding-left: 18px; }
        .markdown-content li { margin: 1px 0; }
        .markdown-content code { background: var(--chat-reasoning-bg); padding: 1px 4px; border-radius: 3px; font-size: 12px; color: #c02660; }
        .markdown-content strong { color: var(--chat-msg-agent-text); font-weight: 650; }
        .markdown-content blockquote { border-left: 3px solid var(--gold-500); padding-left: 10px; margin: 6px 0; color: var(--text-secondary); }
        .markdown-content table { border-collapse: collapse; width: 100%; margin: 6px 0; font-size: 12px; }
        .markdown-content th, .markdown-content td { border: 1px solid var(--chat-msg-agent-border); padding: 4px 8px; text-align: left; }
        .markdown-content th { background: var(--chat-reasoning-bg); font-weight: 600; }
      `}</style>
      {/* Header */}
      <div style={{
        padding: '12px 20px',
        background: 'var(--chat-header-bg)',
        borderBottom: '1px solid var(--chat-msg-agent-border)',
        boxShadow: '0 1px 2px rgba(0,0,0,0.02)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{
            display: 'inline-flex', alignItems: 'center', gap: 4,
            padding: '4px 12px', borderRadius: 20,
            fontSize: 12, fontWeight: 600,
            background: '#f59e0b18', color: '#f59e0b',
            border: '1px solid #f59e0b30',
          }}>
            👑 主管模式
          </span>
          <span style={{ fontSize: 12, color: 'var(--text-dim)' }}>Leader 分析任务，委派成员执行</span>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <div style={{
            width: 8, height: 8, borderRadius: '50%',
            background: isConnected ? '#10b981' : '#ef4444',
          }} />
          <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>
            {isConnected ? '已连接' : '未连接'}
          </span>
          {executionState !== 'idle' && (
              <div style={{
                padding: '6px 12px',
                background: 'var(--chat-thinking-bg)',
                borderRadius: 16,
                fontSize: 12,
                color: 'var(--text-dim)',
              }}>
                {executionState === 'thinking' && '🧠 思考中...'}
                {executionState === 'executing' && '⚡ 执行中...'}
                {executionState === 'hitl_pending' && '🤔 等待确认'}
              </div>
            )}
          <div
            style={{
              padding: '6px 12px',
              background: showMembers ? 'var(--chat-btn-active-bg)' : 'var(--bg-card-hover)',
              borderRadius: 16, fontSize: 12, cursor: 'pointer',
              color: showMembers ? 'var(--chat-btn-active-text)' : 'var(--text-dim)',
              fontWeight: showMembers ? 600 : 400,
            }}
            onClick={() => { setShowMembers(!showMembers); setShowWorkspace(false); setShowTaskTree(false); }}
            title="查看团队成员"
          >
            👥 {members.length} 成员
          </div>
          <div
            style={{
              padding: '6px 12px',
              background: showWorkspace ? 'var(--chat-btn-active-bg)' : 'var(--bg-card-hover)',
              borderRadius: 16, fontSize: 12, cursor: 'pointer',
              color: showWorkspace ? 'var(--chat-btn-active-text)' : 'var(--text-dim)',
              fontWeight: showWorkspace ? 600 : 400,
            }}
            onClick={() => { setShowWorkspace(!showWorkspace); setShowMembers(false); setShowTaskTree(false); }}
            title={workspacePath || '查看工作空间文件'}
          >
            📁 {workspacePath ? workspacePath.split('/').pop() || '工作空间' : '文件'}
          </div>
          {taskPhases.length > 0 && (
            <div
              style={{
                padding: '6px 12px',
                background: showTaskTree ? 'var(--chat-btn-active-bg)' : 'var(--bg-card-hover)',
                borderRadius: 16, fontSize: 12, cursor: 'pointer',
                color: showTaskTree ? 'var(--chat-btn-active-text)' : 'var(--text-dim)',
                fontWeight: showTaskTree ? 600 : 400,
              }}
              onClick={() => { setShowTaskTree(!showTaskTree); setShowMembers(false); setShowWorkspace(false); }}
              title="查看任务进度树"
            >
              📋 任务 {(() => {
                const tot = taskPhases.reduce((s, ph) => s + ph.tasks.length, 0);
                const done = taskPhases.reduce((s, ph) => s + ph.tasks.filter(t => t.status === 'done').length, 0);
                return `${done}/${tot}`;
              })()}
            </div>
          )}
        </div>
      </div>

      {/* Members panel — shared component */}
      {showMembers && (
        <MembersPanel members={members} agentStatuses={agentStatuses} onClose={() => setShowMembers(false)} />
      )}

      {/* Workspace panel — shared component */}
      {showWorkspace && (
        <WorkspaceSlideover sessionId={sessionId} workspacePath={workspacePath} onClose={() => setShowWorkspace(false)} />
      )}

      {/* Task tree panel — shared component */}
      {showTaskTree && taskPhases.length > 0 && (
        <TaskTreePanel phases={taskPhases} onClose={() => setShowTaskTree(false)} />
      )}

      {/* Main Content — chat message list */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '16px 20px' }}>
        {chatMessages.map(msg => {
          if (msg.type === 'user') {
            return (
              <div key={msg.id} style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16 }}>
                <div style={{
                  background: 'var(--chat-msg-user-bg)', color: 'var(--chat-msg-user-text)',
                  padding: '10px 16px', borderRadius: 12,
                  borderBottomRightRadius: 4, maxWidth: '70%',
                  fontSize: 14, lineHeight: 1.6,
                }}>
                  {msg.content}
                </div>
              </div>
            );
          }

          // Claude Code-style record of the user's HITL answer
          if (msg.type === 'hitl_answer' && msg.hitlQa && msg.hitlQa.length > 0) {
            return (
              <div key={msg.id} style={{ marginBottom: 16, marginLeft: 4 }}>
                <div style={{
                  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
                  fontSize: 12.5, lineHeight: 1.7,
                  color: 'var(--text-secondary)',
                }}>
                  <div style={{ color: 'var(--text-primary)', fontWeight: 600 }}>
                    ⏺ {msg.hitlTitle || '用户已回答'}
                  </div>
                  <div style={{ marginTop: 2 }}>
                    {msg.hitlQa.map((qa, i) => (
                      <div key={i} style={{ display: 'flex', gap: 6 }}>
                        <span style={{ color: 'var(--text-dim)', flexShrink: 0 }}>⎿</span>
                        <span style={{ color: 'var(--text-secondary)' }}>
                          · {qa.q} <span style={{ color: '#f59e0b' }}>→</span>{' '}
                          <span style={{ color: 'var(--text-primary)', fontWeight: 500 }}>{qa.a}</span>
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            );
          }

          if (msg.type === 'agent') {
            return (
              <div key={msg.id} style={{ marginBottom: 12 }}>
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                  <span style={{ fontSize: 18, flexShrink: 0, marginTop: 2 }}>{msg.agentEmoji}</span>
                  <div style={{
                    flex: 1, minWidth: 0,
                    background: 'var(--chat-header-bg)', borderRadius: 12,
                    padding: '12px 16px', border: '1px solid var(--chat-msg-agent-border)',
                    boxShadow: '0 1px 2px rgba(0,0,0,0.03)',
                  }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 6 }}>
                      {msg.agentName}
                    </div>
                    {msg.reasoning && (
                      <details style={{ marginBottom: msg.content ? 8 : 0 }}>
                        <summary style={{ fontSize: 11, color: 'var(--text-dim)', cursor: 'pointer' }}>
                          🧠 推理过程
                        </summary>
                        <div style={{
                          marginTop: 6, padding: '8px 12px',
                          background: 'var(--chat-reasoning-bg)', borderRadius: 6,
                          fontSize: 11.5, color: 'var(--text-secondary)',
                          whiteSpace: 'pre-wrap', lineHeight: 1.5,
                          maxHeight: 160, overflowY: 'auto',
                        }}>
                          {msg.reasoning}
                        </div>
                      </details>
                    )}
                    {msg.content && (
                      <div className="markdown-content" style={{
                        fontSize: 13, color: 'var(--chat-msg-agent-text)',
                        lineHeight: 1.6, whiteSpace: 'pre-line',
                      }}>
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {msg.content}
                        </ReactMarkdown>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            );
          }

          if (msg.type === 'task_dag' && msg.tasks) {
            return (
              <div key={msg.id} style={{
                marginBottom: 12, marginLeft: 26,
                background: 'var(--chat-header-bg)', borderRadius: 12,
                padding: '14px 16px', border: '1px solid #f59e0b30',
                boxShadow: '0 1px 2px rgba(0,0,0,0.03)',
              }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 10 }}>
                  📋 任务分解 ({msg.tasks.length})
                </div>
                {msg.tasks.map(t => (
                  <div key={t.id} style={{
                    display: 'flex', alignItems: 'center', gap: 8,
                    padding: '8px 0', borderBottom: '1px solid var(--border-subtle)',
                  }}>
                    <span style={{ fontSize: 16 }}>{t.agentEmoji}</span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <span style={{ fontSize: 12, fontWeight: 500, color: 'var(--chat-msg-agent-text)' }}>{t.agentName}</span>
                      <span style={{ fontSize: 11, color: 'var(--text-dim)', marginLeft: 6 }}>{t.task}</span>
                    </div>
                    <span style={{
                      fontSize: 10, padding: '2px 8px', borderRadius: 10, flexShrink: 0,
                      background: t.status === 'done' ? '#10b98115' : t.status === 'running' ? '#3b82f615' : '#9ca3af15',
                      color: t.status === 'done' ? '#10b981' : t.status === 'running' ? '#3b82f6' : '#9ca3af',
                    }}>
                      {t.status === 'done' ? '完成' : t.status === 'running' ? '执行中' : '待执行'}
                    </span>
                  </div>
                ))}
              </div>
            );
          }

          if (msg.type === 'system') {
            // User action — show as colored indicator badge matching the option
            const isUserAction = msg.agentEmoji === '👤';
            if (isUserAction) {
              const isApprove = msg.content.includes('已确认');
              const isReject = msg.content.includes('已拒绝') || msg.content.includes('已取消');
              const color = isApprove ? 'var(--green-400)' : isReject ? 'var(--red-400)' : 'var(--gold-400)';
              const bg = isApprove ? '#10b98112' : isReject ? '#ef444412' : '#f59e0b12';
              const border = isApprove ? '#10b98140' : isReject ? '#ef444440' : '#f59e0b40';
              return (
                <div key={msg.id} style={{
                  marginBottom: 10, display: 'flex', justifyContent: 'center',
                }}>
                  <span style={{
                    display: 'inline-flex', alignItems: 'center', gap: 6,
                    padding: '5px 16px', borderRadius: 20,
                    fontSize: 12, fontWeight: 600,
                    background: bg, color, border: `1px solid ${border}`,
                  }}>
                    {msg.content}
                  </span>
                </div>
              );
            }
            return (
              <div key={msg.id} style={{
                marginBottom: 8, fontSize: 11, color: 'var(--text-muted)', fontStyle: 'italic',
                textAlign: 'center',
              }}>
                {msg.agentEmoji && <span>{msg.agentEmoji} </span>}
                {msg.content}
              </div>
            );
          }

          return null;
        })}

        {chatMessages.length === 0 && !activeHitl && (
          <div style={{
            display: 'flex', flexDirection: 'column', alignItems: 'center',
            justifyContent: 'center', height: '100%', color: 'var(--text-muted)', gap: 8,
          }}>
            <div style={{ fontSize: 40 }}>👑</div>
            <div style={{ fontSize: 14 }}>输入任务需求，Leader 将分析并委派团队执行</div>
          </div>
        )}

        {/* Inline HITL — Claude Code CLI style: part of the conversation */}
        {activeHitl && (
          <div style={{ marginBottom: 12, marginLeft: 26 }}>
            <div style={{
              background: 'var(--bg-card)', borderRadius: 12,
              padding: '12px 16px', border: '1px solid var(--gold-border, #f59e0b40)',
              borderLeft: '3px solid var(--gold-500)',
            }}>
              <div style={{ fontSize: 11, color: 'var(--text-dim)', marginBottom: 4 }}>
                请确认以上方案，或输入修改意见
              </div>
              {selectedHitlValue && (
                <div style={{ fontSize: 11, color: 'var(--green-400)', fontWeight: 600, marginBottom: 6 }}>
                  ✅ 已选择，等待执行...
                </div>
              )}
              {activeHitl.message && activeHitl.message.length < 300 && (
                <div style={{
                  fontSize: 11.5, color: 'var(--text-secondary)', marginBottom: 8,
                  whiteSpace: 'pre-wrap', lineHeight: 1.4,
                  maxHeight: 80, overflowY: 'auto',
                }}>
                  {activeHitl.message}
                </div>
              )}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {activeHitl.options.map(opt => {
                  const isPrimary = opt.value === 'approve' || opt.value === 'force_confirm';
                  const isDanger = opt.value === 'reject' || opt.value === 'cancel';
                  const isSelected = selectedHitlValue === opt.value;
                  return (
                    <button
                      key={opt.value}
                      onClick={() => handleHitlResponse(opt.value)}
                      style={{
                        padding: '5px 14px', borderRadius: 6, fontSize: 12, fontWeight: isSelected ? 700 : 500,
                        cursor: 'pointer', textAlign: 'left',
                        border: `1px solid ${isSelected
                          ? (isPrimary ? 'var(--green-400)' : isDanger ? 'var(--red-400)' : 'var(--gold-400)')
                          : (isPrimary ? 'var(--green-400)' : isDanger ? 'var(--red-400)' : 'var(--border-medium)')}`,
                        background: isSelected
                          ? (isPrimary ? '#10b98130' : isDanger ? '#ef444430' : '#f59e0b30')
                          : (isPrimary ? '#10b98112' : isDanger ? '#ef444412' : 'var(--bg-card-hover)'),
                        color: isSelected
                          ? (isPrimary ? 'var(--green-400)' : isDanger ? 'var(--red-400)' : 'var(--gold-400)')
                          : (isPrimary ? 'var(--green-400)' : isDanger ? 'var(--red-400)' : 'var(--text-secondary)'),
                        opacity: selectedHitlValue && !isSelected ? 0.35 : 1,
                        transition: 'all 0.15s',
                      }}
                    >
                      {isSelected ? '▸ ' : ''}{opt.label}
                    </button>
                  );
                })}
                <span style={{ fontSize: 10, color: 'var(--text-dim)', paddingTop: 2 }}>
                  Esc 快速确认
                </span>
              </div>
            </div>
          </div>
        )}

        <div ref={scrollRef} />
      </div>

      {/* Input */}
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
          <input
            type="text"
            value={userInput}
            onChange={(e) => setUserInput(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && handleSubmit()}
            placeholder="描述你的需求..."
            disabled={!isConnected || (executionState !== 'idle' && executionState !== 'hitl_pending')}
            style={{
              flex: 1,
              padding: '12px 16px',
              borderRadius: 12,
              border: '1px solid var(--chat-msg-agent-border)',
              background: 'var(--chat-reasoning-bg)',
              fontSize: 14,
              outline: 'none',
            }}
          />
          <button
            onClick={handleSubmit}
            disabled={!userInput.trim() || !isConnected || (executionState !== 'idle' && executionState !== 'hitl_pending')}
            style={{
              padding: '12px 24px',
              borderRadius: 10,
              background: (userInput.trim() && isConnected && (executionState === 'idle' || executionState === 'hitl_pending')) ? 'var(--chat-msg-user-bg)' : 'var(--chat-send-disabled-bg)',
              color: (userInput.trim() && isConnected && (executionState === 'idle' || executionState === 'hitl_pending')) ? 'var(--chat-msg-user-text)' : 'var(--text-muted)',
              border: 'none',
              fontSize: 14,
              fontWeight: 500,
              cursor: (userInput.trim() && isConnected && (executionState === 'idle' || executionState === 'hitl_pending')) ? 'pointer' : 'not-allowed',
            }}
          >
            发送
          </button>
        </div>
      </div>
    </div>
  );
}

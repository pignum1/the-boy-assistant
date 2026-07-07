/**
 * SidePanel — 右侧固定面板，Tab 切换任务/成员/文件/流程
 *
 * Supervisor/Swarm → 任务/成员/文件
 * LangGraph → 任务/成员/文件/流程（流程图）
 */
import React, { useState, useRef, useCallback, lazy, Suspense, useEffect } from 'react';
import type { WorkPlan, DeltaPlan, ArtifactFile, ThinkingAgent } from '../types/state';
import type { TimelineItem } from '../types/state';
import type { TeamMember } from '../hooks/useTeamMembers';

const WorkPlanDrawer = lazy(() => import('./drawers/WorkPlanDrawer').then(m => ({ default: m.WorkPlanDrawer })));
const TeamDrawer = lazy(() => import('./drawers/TeamDrawer').then(m => ({ default: m.TeamDrawer })));
const ArtifactsDrawer = lazy(() => import('./drawers/ArtifactsDrawer').then(m => ({ default: m.ArtifactsDrawer })));

type CollabMode = 'swarm' | 'supervisor' | 'langgraph';

interface FlowNode { id: string; type: string; label: string; node_key: string; position_x: number; position_y: number; agent_name: string; }
interface FlowEdge { id: string; source_id: string; target_id: string; type: string; }

function FlowChart({ teamId, workPlan }: { teamId: string; workPlan: WorkPlan | null }) {
  const [nodes, setNodes] = useState<FlowNode[]>([]);
  const [edges, setEdges] = useState<FlowEdge[]>([]);
  const [name, setName] = useState('');
  const [loading, setLoading] = useState(true);
  const [selectedNode, setSelectedNode] = useState<FlowNode | null>(null);

  useEffect(() => {
    const API = (import.meta as any).env?.VITE_API_URL || '';
    fetch(`${API}/api/v1/teams/${teamId}/langgraph-workflow`)
      .then(r => r.json())
      .then(d => { setNodes(d.nodes || []); setEdges(d.edges || []); setName(d.workflow_name || ''); })
      .finally(() => setLoading(false));
  }, [teamId]);

  if (loading) return <div style={{ padding: 24, color: 'var(--text-muted)', textAlign: 'center' }}>加载工作流…</div>;
  if (nodes.length === 0) return <div style={{ padding: 24, color: 'var(--text-muted)', textAlign: 'center' }}>暂无工作流定义</div>;

  // Build status map from workPlan tasks
  const nodeStatus: Record<string, string> = {};
  if (workPlan) {
    for (const n of nodes) {
      const task = workPlan.tasks[n.id];
      if (task) nodeStatus[n.id] = task.status as string;
    }
  }
  const runningCount = Object.values(nodeStatus).filter(s => s === 'running').length;
  const doneCount = Object.values(nodeStatus).filter(s => s === 'done').length;
  const rejectedCount = Object.values(nodeStatus).filter(s => s === 'rejected' || s === 'rollback').length;

  const nodeById = new Map(nodes.map(n => [n.id, n]));

  // Calculate SVG dimensions based on node positions
  const maxX = Math.max(...nodes.map(n => n.position_x), 0) + 160;
  const maxY = Math.max(...nodes.map(n => n.position_y), 0) + 80;
  const w = Math.max(520, maxX);
  const h = Math.max(400, maxY);

  // Node type → color scheme
  const typeColors: Record<string, { border: string; bg: string; icon: string }> = {
    start: { border: 'var(--border-strong)', bg: 'var(--bg-raised)', icon: '🚀' },
    end: { border: 'var(--green)', bg: '#f0fdf4', icon: '✅' },
    agent: { border: '#3b82f6', bg: '#eff6ff', icon: '🤖' },
    task: { border: '#6366f1', bg: '#eef2ff', icon: '📌' },
    worker: { border: '#8b5cf6', bg: '#f5f3ff', icon: '🔧' },
    hitl: { border: '#f59e0b', bg: '#fffbeb', icon: '👤' },
    condition: { border: '#a855f7', bg: '#faf5ff', icon: '🔀' },
    router: { border: '#f97316', bg: '#fff7ed', icon: '🔀' },
    validation: { border: '#10b981', bg: '#ecfdf5', icon: '✅' },
  };

  const getNodeColors = (n: FlowNode) => {
    const st = nodeStatus[n.id];
    const isDone = st === 'done';
    const isRunning = st === 'running';
    const isRejected = st === 'rejected' || st === 'rollback';
    const tc = typeColors[n.type] || typeColors.task;
    return {
      border: isRejected ? '#ef4444' : isDone ? 'var(--green)' : isRunning ? 'var(--cyan-400)' : tc.border,
      bg: isRejected ? '#fef2f2' : isDone ? '#f0fdf4' : isRunning ? '#ecfeff' : tc.bg,
      shadow: isRunning ? '0 0 0 4px rgba(6,182,212,.22)' : isRejected ? '0 0 0 2px rgba(239,68,68,.15)' : undefined,
      pulse: isRunning,
    };
  };

  // Separate forward and reject edges
  const forwardEdges = edges.filter(e => (e.type || 'forward') === 'forward');
  const rejectEdges = edges.filter(e => e.type === 'reject');

  return (
    <div style={{ padding: 4, height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <div style={{ padding: '4px 10px 8px', flexShrink: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>🔀 {name || '工作流'}</div>
        <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2, fontFamily: 'var(--font-mono)', display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          {doneCount > 0 && <span style={{ color: 'var(--green-500)' }}>{doneCount} 完成</span>}
          {runningCount > 0 && <span style={{ color: 'var(--cyan-500)' }}>{runningCount} 执行中</span>}
          {rejectedCount > 0 && <span style={{ color: '#ef4444' }}>{rejectedCount} 打回</span>}
          <span style={{ color: 'var(--text-muted)' }}>{nodes.length} 节点 · {edges.length} 边</span>
        </div>
      </div>

      {/* Scrollable SVG area */}
      <div style={{ flex: 1, overflow: 'auto', position: 'relative', background: 'var(--bg-subtle)', borderRadius: 8, margin: '0 4px' }}>
        <div style={{ position: 'relative', width: w, height: h, minHeight: '100%' }}>
          <svg width={w} height={h} style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}>
            <defs>
              <marker id="arrowForward" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
                <path d="M0,0 L6,3 L0,6 Z" fill="var(--border-strong)" />
              </marker>
              <marker id="arrowGreen" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
                <path d="M0,0 L6,3 L0,6 Z" fill="var(--green)" />
              </marker>
              <marker id="arrowRed" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
                <path d="M0,0 L6,3 L0,6 Z" fill="#ef4444" />
              </marker>
            </defs>

            {/* Forward edges */}
            {forwardEdges.map(e => {
              const s = nodeById.get(e.source_id); const t = nodeById.get(e.target_id);
              if (!s || !t) return null;
              const sDone = nodeStatus[s.id] === 'done';
              const tRunning = nodeStatus[t.id] === 'running';
              const tDone = nodeStatus[t.id] === 'done';
              const isActive = sDone && (tRunning || tDone);
              const stroke = isActive ? 'var(--green)' : 'var(--border-strong)';
              const dash = tRunning ? '5,3' : undefined;
              return <line key={e.id} x1={s.position_x} y1={s.position_y + 28} x2={t.position_x} y2={t.position_y - 2} stroke={stroke} strokeWidth={isActive ? 2 : 1.3} strokeDasharray={dash} markerEnd={isActive ? 'url(#arrowGreen)' : 'url(#arrowForward)'} opacity={isActive ? 1 : 0.5} />;
            })}

            {/* Reject edges (red dashed) */}
            {rejectEdges.map(e => {
              const s = nodeById.get(e.source_id); const t = nodeById.get(e.target_id);
              if (!s || !t) return null;
              // Draw reject edge as a curved red dashed line going from source right side to target left side
              const sx = s.position_x + 56;
              const sy = s.position_y + 14;
              const tx = t.position_x - 56;
              const ty = t.position_y + 14;
              const midX = (sx + tx) / 2 + 30;
              return (
                <path key={e.id}
                  d={`M ${sx} ${sy} C ${midX} ${sy}, ${midX} ${ty}, ${tx} ${ty}`}
                  stroke="#ef4444" strokeWidth={1.5}
                  strokeDasharray="6,4" fill="none"
                  opacity={0.55}
                  markerEnd="url(#arrowRed)"
                />
              );
            })}
          </svg>

          {/* Node cards */}
          {nodes.map(n => {
            const st = nodeStatus[n.id];
            const isRunning = st === 'running';
            const isDone = st === 'done';
            const isRejected = st === 'rejected' || st === 'rollback';
            const isPending = !isRunning && !isDone && !isRejected;
            const colors = getNodeColors(n);
            const isTerminal = n.type === 'start' || n.type === 'end';
            const tc = typeColors[n.type] || typeColors.task;

            // Status dot
            let dot = '○';
            if (isRunning) dot = '◉';
            else if (isDone) dot = '✓';
            else if (isRejected) dot = '↺';

            // Node width varies by type
            const nodeW = isTerminal ? 72 : n.type === 'condition' ? 100 : n.type === 'hitl' ? 120 : 112;

            return (
              <div key={n.id}
                onClick={() => setSelectedNode(selectedNode?.id === n.id ? null : n)}
                style={{
                  position: 'absolute', left: n.position_x - nodeW / 2, top: n.position_y,
                  width: nodeW, padding: isTerminal ? '5px 6px' : '6px 8px',
                  borderRadius: isTerminal ? 20 : n.type === 'condition' ? 4 : 8,
                  border: `2px solid ${colors.border}`,
                  background: colors.bg,
                  fontSize: 10.5, textAlign: 'center' as const,
                  fontWeight: isRunning ? 600 : 500,
                  color: isRejected ? '#991b1b' : 'var(--text)',
                  boxShadow: colors.shadow,
                  transition: 'all 0.3s ease',
                  cursor: 'pointer',
                  zIndex: isRunning ? 2 : 1,
                  opacity: isPending ? 0.7 : 1,
                }}
              >
                {/* Type badge */}
                <div style={{ fontSize: 8, color: tc.border, fontWeight: 600, marginBottom: 1, letterSpacing: '0.3px' }}>
                  {n.type === 'hitl' ? '👤 人工' : n.type === 'validation' ? '✅ 校验' : n.type === 'condition' ? '🔀 条件' : n.type === 'router' ? '🔀 路由' : n.type === 'agent' ? '🤖 Agent' : n.type === 'start' ? '开始' : n.type === 'end' ? '结束' : '📌 任务'}
                </div>
                <span style={{
                  color: isDone ? 'var(--green-600)' : isRunning ? 'var(--cyan-600)' : isRejected ? '#991b1b' : undefined,
                  fontWeight: isDone || isRunning || isRejected ? 600 : undefined,
                }}>
                  <span style={{ marginRight: 3, fontSize: 9 }}>{dot}</span>
                  {n.label.length > 12 ? n.label.slice(0, 11) + '…' : n.label}
                </span>
                {n.agent_name && (
                  <div style={{ fontSize: 8.5, color: 'var(--text-muted)', marginTop: 2, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {n.agent_name}
                  </div>
                )}
                {/* Pulse animation for running nodes */}
                {isRunning && (
                  <div style={{
                    position: 'absolute', inset: -4, borderRadius: 'inherit',
                    border: '2px solid var(--cyan-400)', opacity: 0.4,
                    animation: 'pulse-ring 1.5s ease-out infinite',
                    pointerEvents: 'none',
                  }} />
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Legend */}
      <div style={{ padding: '6px 10px', fontSize: 9.5, color: 'var(--text-muted)', display: 'flex', gap: 10, flexWrap: 'wrap', flexShrink: 0, borderTop: '1px solid var(--border-subtle)', marginTop: 4 }}>
        <span>◉ 执行中</span><span>✓ 完成</span><span>○ 待执行</span><span style={{ color: '#ef4444' }}>↺ 打回</span>
        <span style={{ color: '#ef4444' }}>- - - 打回边</span>
        <span>— 正向边</span>
      </div>

      {/* Node detail popup */}
      {selectedNode && (
        <div style={{
          position: 'absolute', bottom: 60, left: 12, right: 12,
          background: 'var(--bg-raised)', border: '1px solid var(--border)',
          borderRadius: 10, padding: 12, fontSize: 12, zIndex: 10,
          boxShadow: '0 8px 30px rgba(0,0,0,.12)',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
            <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
              {typeColors[selectedNode.type]?.icon || '📌'} {selectedNode.label}
            </span>
            <button onClick={() => setSelectedNode(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 14, color: 'var(--text-muted)' }}>✕</button>
          </div>
          <div style={{ display: 'flex', gap: 16, fontSize: 11, color: 'var(--text-secondary)' }}>
            <span>类型: <b>{selectedNode.type}</b></span>
            <span>Key: <code style={{ fontSize: 10 }}>{selectedNode.node_key}</code></span>
            {selectedNode.agent_name && <span>Agent: <b>{selectedNode.agent_name}</b></span>}
          </div>
          <div style={{ marginTop: 4, fontSize: 10, color: 'var(--text-muted)' }}>
            状态: {
              nodeStatus[selectedNode.id] === 'done' ? '✅ 完成' :
              nodeStatus[selectedNode.id] === 'running' ? '◉ 执行中' :
              nodeStatus[selectedNode.id] === 'rejected' || nodeStatus[selectedNode.id] === 'rollback' ? '↺ 已打回' :
              '○ 待执行'
            }
          </div>
        </div>
      )}

      {/* CSS animation for pulse ring */}
      <style>{`
        @keyframes pulse-ring {
          0% { transform: scale(1); opacity: 0.5; }
          100% { transform: scale(1.08); opacity: 0; }
        }
      `}</style>
    </div>
  );
}

interface Props {
  workPlan: WorkPlan | null; workPlanDelta: DeltaPlan | null;
  messages: TimelineItem[]; thinkingAgents: ThinkingAgent[]; teamMembers: TeamMember[];
  artifacts: ArtifactFile[]; sessionId: string; workspacePath?: string;
  teamId: string; collabMode: CollabMode;
}

export const SidePanel: React.FC<Props> = ({
  workPlan, workPlanDelta, messages, thinkingAgents, teamMembers,
  artifacts, sessionId, workspacePath, teamId, collabMode,
}) => {
  const [activeTab, setActiveTab] = useState<string>('task');
  const [width, setWidth] = useState(380);
  const draggingRef = useRef(false);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault(); draggingRef.current = true;
    document.body.style.cursor = 'col-resize'; document.body.style.userSelect = 'none';
    const onMove = (ev: MouseEvent) => { if (!draggingRef.current) return; setWidth(Math.max(280, Math.min(window.innerWidth * 0.55, window.innerWidth - ev.clientX))); };
    const onUp = () => { draggingRef.current = false; document.body.style.cursor = ''; document.body.style.userSelect = ''; document.removeEventListener('mousemove', onMove); document.removeEventListener('mouseup', onUp); };
    document.addEventListener('mousemove', onMove); document.addEventListener('mouseup', onUp);
  }, []);

  const tabs = [
    { key: 'task', icon: '🧩', label: '任务', badge: workPlan ? `${workPlan.doneTasks}/${workPlan.totalTasks}` : undefined },
    { key: 'team', icon: '👥', label: '成员', badge: `${teamMembers.length}` },
    { key: 'file', icon: '📁', label: '文件', badge: `${artifacts.length}` },
    ...(collabMode === 'langgraph' ? [{ key: 'flow', icon: '🔀', label: '流程' }] : []),
  ];

  return (
    <div style={{ width, minWidth: 280, maxWidth: '55vw', height: '100%', display: 'flex', flexDirection: 'column', background: 'var(--bg)', borderLeft: '1px solid var(--border)', flexShrink: 0 }}>
      <div onMouseDown={handleMouseDown} style={{ position: 'absolute', left: -3, top: 0, bottom: 0, width: 6, cursor: 'col-resize', zIndex: 1 }} />
      <div style={{ height: 42, padding: '0 10px', display: 'flex', alignItems: 'center', gap: 4, borderBottom: '1px solid var(--border-subtle)', flexShrink: 0 }}>
        {tabs.map(tab => (
          <button key={tab.key} onClick={() => setActiveTab(tab.key)} style={{ padding: '5px 12px', fontSize: 12.5, fontWeight: 500, borderRadius: 7, border: 'none', background: activeTab === tab.key ? 'var(--bg-soft)' : 'transparent', color: activeTab === tab.key ? 'var(--text-primary)' : 'var(--text-secondary)', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 5 }}>
            {tab.icon} {tab.label}
            {tab.badge && <span style={{ fontSize: 10, padding: '1px 6px', borderRadius: 8, background: 'var(--bg-raised)', color: 'var(--text-secondary)' }}>{tab.badge}</span>}
          </button>
        ))}
      </div>
      <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        <Suspense fallback={<div style={{ padding: 24, color: 'var(--text-muted)' }}>加载中…</div>}>
          {activeTab === 'task' && <div style={{ flex: 1, overflowY: 'auto', padding: '8px 6px' }}><WorkPlanDrawer workPlan={workPlan} workPlanDelta={workPlanDelta} /></div>}
          {activeTab === 'team' && <div style={{ flex: 1, overflowY: 'auto', padding: '8px 6px' }}><TeamDrawer messages={messages} thinkingAgents={thinkingAgents} teamMembers={teamMembers} /></div>}
          {activeTab === 'file' && <div style={{ flex: 1, overflowY: 'auto', padding: '8px 6px' }}><ArtifactsDrawer artifacts={artifacts} sessionId={sessionId} workspacePath={workspacePath} /></div>}
          {activeTab === 'flow' && <div style={{ flex: 1, overflowY: 'auto' }}><FlowChart teamId={teamId} workPlan={workPlan} /></div>}
        </Suspense>
      </div>
    </div>
  );
};

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
  const nodeStatus: Record<string, 'running' | 'done' | 'pending'> = {};
  if (workPlan) {
    for (const n of nodes) {
      const task = workPlan.tasks[n.id];
      if (task) nodeStatus[n.id] = task.status as any;
    }
  }
  const runningCount = Object.values(nodeStatus).filter(s => s === 'running').length;
  const doneCount = Object.values(nodeStatus).filter(s => s === 'done').length;

  const nodeById = new Map(nodes.map(n => [n.id, n]));
  const w = 300, h = Math.max(300, nodes.length * 90);
  return (
    <div style={{ padding: 8 }}>
      <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 2, padding: '0 6px' }}>🔀 {name || '工作流'}</div>
      {(doneCount > 0 || runningCount > 0) && (
        <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 6, padding: '0 6px', fontFamily: 'var(--font-mono)' }}>
          {doneCount} 完成{runningCount > 0 ? ` · ${runningCount} 执行中` : ''}
        </div>
      )}
      <div style={{ position: 'relative', width: w, height: h, margin: '0 auto' }}>
        <svg width={w} height={h} style={{ position: 'absolute', inset: 0 }}>
          {edges.map(e => {
            const s = nodeById.get(e.source_id); const t = nodeById.get(e.target_id);
            if (!s || !t) return null;
            const isActive = nodeStatus[s.id] === 'done' && (nodeStatus[t.id] === 'running' || nodeStatus[t.id] === 'done');
            const stroke = isActive ? 'var(--green)' : 'var(--border-strong)';
            const dash = nodeStatus[t.id] === 'running' ? '5,3' : undefined;
            return <line key={e.id} x1={s.position_x} y1={s.position_y + 20} x2={t.position_x} y2={t.position_y - 2} stroke={stroke} strokeWidth={isActive ? 2 : 1.5} strokeDasharray={dash} markerEnd="url(#arrow)" />;
          })}
          <defs>
            <marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6 Z" fill="var(--border-strong)" /></marker>
          </defs>
        </svg>
        {nodes.map(n => {
          const st = nodeStatus[n.id];
          const isRunning = st === 'running';
          const isDone = st === 'done';
          const isTerminal = n.type === 'start' || n.type === 'end';
          const bg = isTerminal ? 'var(--bg-bubble)' : 'var(--bg)';
          const borderColor = isDone ? 'var(--green)' : isRunning ? 'var(--cyan-400)' : isTerminal ? 'var(--border-strong)' : 'var(--border)';
          const shadow = isRunning ? '0 0 0 3px rgba(6,182,212,.18)' : isDone ? '0 0 0 2px rgba(34,197,94,.1)' : undefined;
          const statusDot = isRunning ? '● ' : isDone ? '✓ ' : '';
          return (
            <div key={n.id} style={{
              position: 'absolute', left: n.position_x - 56, top: n.position_y,
              width: 112, padding: '6px 8px', borderRadius: isTerminal ? 16 : 8,
              border: `1.5px solid ${borderColor}`, background: bg, fontSize: 11, textAlign: 'center',
              fontWeight: 500, color: 'var(--text)', boxShadow: shadow,
              transition: 'border-color 0.3s, box-shadow 0.3s',
            }}>
              <span style={{ color: isDone ? 'var(--green-400)' : isRunning ? 'var(--cyan-400)' : undefined, fontWeight: isDone || isRunning ? 600 : undefined }}>{statusDot}{n.label}</span>
              {n.agent_name && <div style={{ fontSize: 9, color: 'var(--text-muted)', marginTop: 1 }}>{n.agent_name}</div>}
            </div>
          );
        })}
      </div>
      <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 12, textAlign: 'center', display: 'flex', gap: 12, justifyContent: 'center' }}>
        <span>● 执行中</span><span>✓ 完成</span><span>○ 待执行</span>
      </div>
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

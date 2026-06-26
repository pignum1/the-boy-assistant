/** Shared side panels for all chat modes: Members + Workspace */
import { WorkspacePanel } from '../WorkspacePanel';

interface Member {
  id: string; agent_id: string; agent_name: string; role_name: string;
  role_icon: string; status: string;
}

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

const overlayStyle: React.CSSProperties = { position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.2)', zIndex: 90 };

const panelContainerStyle: React.CSSProperties = {
  position: 'fixed', top: 0, right: 0, bottom: 0, width: 320,
  background: 'var(--bg-card)', zIndex: 100,
  boxShadow: '-4px 0 20px rgba(0,0,0,0.3)',
  display: 'flex', flexDirection: 'column',
};

const panelHeaderStyle: React.CSSProperties = {
  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
  padding: '14px 16px', borderBottom: '1px solid var(--border-medium)',
};

const closeBtnStyle: React.CSSProperties = {
  width: 28, height: 28, borderRadius: 6, border: 'none',
  background: 'var(--bg-card-hover)', cursor: 'pointer',
  fontSize: 14, color: 'var(--text-dim)',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
};

interface MembersPanelProps {
  members: Member[];
  agentStatuses: Record<string, { status: string; summary: string }>;
  onClose: () => void;
}

export function MembersPanel({ members, agentStatuses, onClose }: MembersPanelProps) {
  return (
    <>
      <div onClick={onClose} style={overlayStyle} />
      <div style={panelContainerStyle}>
        <div style={panelHeaderStyle}>
          <div>
            <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>团队成员</div>
            <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 2 }}>共 {members.length} 人</div>
          </div>
          <button onClick={onClose} style={closeBtnStyle}>✕</button>
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: '10px 12px' }}>
          {members.map(member => {
            const status = agentStatuses[member.agent_name];
            const isActive = status && status.status !== 'idle';
            return (
              <div key={member.agent_id} style={{
                display: 'flex', alignItems: 'center', gap: 10,
                padding: '10px 12px', borderRadius: 8,
                background: isActive ? 'var(--gold-bg)' : 'transparent',
                marginBottom: 2,
              }}>
                <span style={{ fontSize: 18, flexShrink: 0 }}>
                  {member.role_icon || getRoleEmoji(member.role_name)}
                </span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 12.5, fontWeight: 500, color: 'var(--text-primary)' }}>
                    {member.agent_name}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-dim)' }}>{member.role_name}</div>
                </div>
                <div style={{
                  width: 7, height: 7, borderRadius: '50%', flexShrink: 0,
                  background: isActive ? '#f59e0b' : '#10b981',
                }} title={isActive ? '执行中' : '空闲'} />
              </div>
            );
          })}
        </div>
      </div>
    </>
  );
}

interface WorkspaceSlideoverProps {
  sessionId: string;
  workspacePath?: string;
  onClose: () => void;
}

export function WorkspaceSlideover({ sessionId, workspacePath, onClose }: WorkspaceSlideoverProps) {
  return (
    <>
      <div onClick={onClose} style={overlayStyle} />
      <div style={panelContainerStyle}>
        <div style={panelHeaderStyle}>
          <div>
            <span style={{ fontWeight: 600, fontSize: 13, color: 'var(--text-primary)' }}>📁 工作空间</span>
            {workspacePath && (
              <div style={{ fontSize: 10, color: 'var(--text-dim)', marginTop: 2, wordBreak: 'break-all' }}>
                {workspacePath}
              </div>
            )}
          </div>
          <button onClick={onClose} style={closeBtnStyle}>✕</button>
        </div>
        <WorkspacePanel sessionId={sessionId} />
      </div>
    </>
  );
}

// ── Task tree panel ──────────────────────────────────────────────

export interface TaskTreeNode {
  id: string;
  agentId: string;
  agentName: string;
  agentEmoji: string;
  task: string;
  status: 'pending' | 'running' | 'done' | 'failed';
}

export interface TaskTreePhase {
  name: string;
  tasks: TaskTreeNode[];
}

interface TaskTreePanelProps {
  phases: TaskTreePhase[];
  onClose: () => void;
}

export function TaskTreePanel({ phases, onClose }: TaskTreePanelProps) {
  const totalTasks = phases.reduce((s, ph) => s + ph.tasks.length, 0);
  const doneTasks = phases.reduce(
    (s, ph) => s + ph.tasks.filter(t => t.status === 'done').length, 0,
  );

  return (
    <>
      <div onClick={onClose} style={overlayStyle} />
      <div style={panelContainerStyle}>
        <div style={panelHeaderStyle}>
          <div>
            <span style={{ fontWeight: 600, fontSize: 13, color: 'var(--text-primary)' }}>📋 任务进度</span>
            <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 2 }}>
              {doneTasks}/{totalTasks} 完成 · {phases.length} 个阶段
            </div>
          </div>
          <button onClick={onClose} style={closeBtnStyle}>✕</button>
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: '12px 14px' }}>
          {phases.length === 0 && (
            <div style={{ fontSize: 12, color: 'var(--text-dim)', textAlign: 'center', marginTop: 24 }}>
              暂无任务。提交需求并确认方案后,任务树将在此展示。
            </div>
          )}
          {phases.map((phase, pi) => (
            <div key={pi} style={{ marginBottom: 12 }}>
              <div style={{
                fontSize: 11, fontWeight: 600, color: 'var(--text-dim)',
                marginBottom: 4, textTransform: 'uppercase', letterSpacing: 0.3,
              }}>
                阶段 {pi + 1} · {phase.name}
              </div>
              {phase.tasks.map(t => (
                <div key={t.id} style={{
                  display: 'flex', alignItems: 'center', gap: 6,
                  padding: '4px 6px', borderRadius: 6, fontSize: 12, marginBottom: 1,
                  background: t.status === 'done' ? 'transparent' : 'var(--bg-card-hover)',
                  color: t.status === 'done' ? 'var(--text-dim)' : 'var(--text-primary)',
                }}>
                  <span style={{ width: 14, textAlign: 'center', flexShrink: 0 }}>
                    {t.status === 'done' ? '✓' : t.status === 'running' ? '⏳' : t.status === 'failed' ? '✗' : '○'}
                  </span>
                  <span style={{ width: 18, textAlign: 'center', flexShrink: 0 }}>{t.agentEmoji}</span>
                  <span style={{ fontWeight: 500, flexShrink: 0 }}>{t.agentName}</span>
                  <span style={{ opacity: 0.75, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    → {t.task}
                  </span>
                  {t.status === 'done' && <span style={{ fontSize: 10, color: '#10b981', marginLeft: 'auto', flexShrink: 0 }}>完成</span>}
                  {t.status === 'running' && <span style={{ fontSize: 10, color: '#3b82f6', marginLeft: 'auto', flexShrink: 0 }}>执行中</span>}
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>
    </>
  );
}

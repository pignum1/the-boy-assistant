import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../../shared/api/client';
import { sessionsApi } from '../../shared/api/sessions';
import type { Team } from '../../shared/types/agent';

interface TaskItem {
  task_id: string; status: string; current_node?: string;
  result?: unknown; error?: string; created_at: string; updated_at: string;
  sop_id?: string; team_id?: string; priority?: string;
  progress?: number; strategy?: string; nodes?: string; time?: string;
}

interface AgentPoolEntry {
  agent_id: string; status: string; team_id?: string; current_task?: string;
}

const STATUS_STYLE: Record<string, { bg: string; color: string }> = {
  running: { bg: 'var(--green-bg)', color: 'var(--green-400)' },
  completed: { bg: 'var(--green-bg)', color: 'var(--green-400)' },
  failed: { bg: 'var(--red-bg)', color: 'var(--red-400)' },
  pending: { bg: 'rgba(148,163,184,0.06)', color: 'var(--text-muted)' },
  paused: { bg: 'var(--gold-bg)', color: 'var(--gold-400)' },
};

const STATUS_LABEL: Record<string, string> = {
  running: '执行中', completed: '已完成', failed: '失败',
  pending: '等待中', paused: '已暂停',
};

export function Tasks() {
  const navigate = useNavigate();
  const [teams, setTeams] = useState<Team[]>([]);
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [agents, setAgents] = useState<AgentPoolEntry[]>([]);
  const [loading, setLoading] = useState(true);

  // Detail panel
  const [panelOpen, setPanelOpen] = useState(false);
  const [activePanelTeam, setActivePanelTeam] = useState<Team | null>(null);
  const [activePanelTab, setActivePanelTab] = useState<'tasks' | 'memory' | 'agents'>('tasks');

  useEffect(() => {
    Promise.allSettled([
      api.get<Team[]>('/api/v1/teams'),
      api.get<TaskItem[]>('/api/v1/tasks'),
      api.get<{ agents: AgentPoolEntry[] }>('/api/v1/agents/pool/status'),
    ]).then(([tRes, taskRes, aRes]) => {
      if (tRes.status === 'fulfilled') setTeams(tRes.value);
      if (taskRes.status === 'fulfilled') setTasks(taskRes.value);
      if (aRes.status === 'fulfilled') {
        const data = aRes.value as { agents?: AgentPoolEntry[] };
        setAgents(data?.agents || (aRes.value as unknown as AgentPoolEntry[]) || []);
      }
      setLoading(false);
    });
  }, []);

  const openPanel = (team: Team, tab: 'tasks' | 'memory' | 'agents' = 'tasks') => {
    setActivePanelTeam(team);
    setActivePanelTab(tab);
    setPanelOpen(true);
  };
  const closePanel = () => setPanelOpen(false);

  if (loading) {
    return (
      <div style={{ padding: '40px 32px', position: 'relative', zIndex: 1 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, letterSpacing: -0.5 }}>任务中心</h1>
        <p style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 8 }}>加载中...</p>
      </div>
    );
  }

  const runningTasks = tasks.filter((t) => t.status === 'running');
  const completedTasks = tasks.filter((t) => t.status === 'completed');
  const onlineAgents = agents.filter((a) => a.status === 'idle' || a.status === 'busy');

  return (
    <div style={{ padding: '28px 32px', maxWidth: 1400, position: 'relative', zIndex: 1 }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 28 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, letterSpacing: -0.5 }}>任务中心</h1>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn-secondary" style={btnSecondaryStyle}>📊</button>
          <button className="btn-primary" style={btnPrimaryStyle} onClick={() => alert('选择团队后创建任务')}>
            + 新建任务
          </button>
        </div>
      </div>

      {/* Overview Strip */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 28 }}>
        <OverviewCard icon="👥" bg="var(--gold-bg)" value={teams.length} label="活跃团队" />
        <OverviewCard icon="▶" bg="var(--green-bg)" value={runningTasks.length} label="执行中任务" valueColor="var(--green-400)" />
        <OverviewCard icon="🧠" bg="var(--blue-bg)" value="3.8KB" label="总 Memory" />
        <OverviewCard icon="🤖" bg="var(--purple-bg)" value={onlineAgents.length} label="Agent 在线" />
      </div>

      {/* Team Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(420px, 1fr))', gap: 16 }}>
        {teams.map((team) => {
          const teamTasks = tasks.filter((t) => t.team_id === team.id);
          const runTasks = teamTasks.filter((t) => t.status === 'running');
          const doneTasks = teamTasks.filter((t) => t.status === 'completed');
          const avgProgress = teamTasks.length
            ? Math.round(teamTasks.reduce((s, t) => s + (t.progress || 0), 0) / teamTasks.length)
            : 0;
          const activeTask = runTasks[0];
          const colorClass = ['gold', 'blue', 'green'][Math.floor(Math.random() * 3)];

          return (
            <div key={team.id} style={teamCardStyle} onClick={() => openPanel(team)}>
              {/* Top: identity + status ring */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 18 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <div style={{ ...teamAvatarStyle, background: `var(--${colorClass}-bg)`, border: `1px solid var(--${colorClass}-border)` }}>
                    {colorClass === 'gold' ? '🏗' : colorClass === 'blue' ? '🔬' : '✏️'}
                  </div>
                  <div>
                    <div style={{ fontSize: 16, fontWeight: 600 }}>{team.name}</div>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
                      {team.collaboration_mode || 'Supervisor'} · {team.status === 'active' ? '活跃' : '休眠'}
                    </div>
                  </div>
                </div>
                <StatusRing progress={avgProgress} color={colorClass} />
              </div>

              {/* Metric pills */}
              <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
                <MetricPill value={runTasks.length} label="执行中" color="var(--green-400)" />
                <MetricPill value={doneTasks.length} label="已完成" />
                <MetricPill value={team.members?.length || 0} label="Agent" />
              </div>

              {/* Agent roster */}
              {team.members && team.members.length > 0 && (
                <div style={agentRosterStyle}>
                  <span style={{ fontSize: 10, color: 'var(--text-dim)', marginRight: 4 }}>成员</span>
                  {team.members.slice(0, 5).map((m, i) => (
                    <div key={i} style={{ ...rosterAvatarStyle, background: 'var(--blue-bg)', zIndex: 5 - i }}>
                      🤖
                      <div style={{ position: 'absolute', bottom: -2, right: -2, width: 8, height: 8, borderRadius: '50%', background: 'var(--green-400)', border: '2px solid var(--bg-elevated)' }} />
                    </div>
                  ))}
                </div>
              )}

              {/* Active task preview */}
              {activeTask && (
                <div style={activeTaskStyle}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                    <span style={{ fontSize: 12, fontWeight: 600 }}>{activeTask.task_id}</span>
                    <span style={{ fontSize: 9, color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>
                      {activeTask.strategy || 'Plan-Exec'}
                    </span>
                  </div>
                  <div style={{ height: 4, background: 'rgba(255,255,255,0.06)', borderRadius: 2, overflow: 'hidden', marginBottom: 4 }}>
                    <div style={{ height: '100%', borderRadius: 2, width: `${activeTask.progress || 50}%`, background: 'var(--gold-500)', transition: 'width 0.5s' }} />
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9, color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>
                    <span>{activeTask.nodes || '-'} · {activeTask.time || '-'}</span>
                    <span>{activeTask.progress || 0}%</span>
                  </div>
                </div>
              )}

              {/* Memory indicator */}
              <div style={memoryBarStyle}>
                <span style={{ fontSize: 14 }}>🧠</span>
                <div style={{ flex: 1, height: 3, background: 'rgba(255,255,255,0.06)', borderRadius: 2, overflow: 'hidden' }}>
                  <div style={{ height: '100%', borderRadius: 2, width: '24%', background: 'var(--green-400)' }} />
                </div>
                <span style={{ fontSize: 10, color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>2.4KB</span>
                <span style={{ fontSize: 9, color: 'var(--text-dim)' }}>5 条</span>
              </div>

              {/* Footer */}
              <div style={cardFooterStyle}>
                <button className="card-btn" style={cardBtnStyle} onClick={async (e) => { e.stopPropagation(); try { const s = await sessionsApi.create({ team_id: team.id }); navigate(`/chat?session=${s.id}&team=${s.team_id}`); } catch { navigate('/chat'); } }}>
                  💬 聊天室
                </button>
                <button className="card-btn" style={cardBtnStyle} onClick={(e) => { e.stopPropagation(); openPanel(team, 'memory'); }}>
                  🧠 Memory
                </button>
                <button className="card-btn" style={cardBtnStyle} onClick={(e) => { e.stopPropagation(); openPanel(team, 'tasks'); }}>
                  详情 →
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* Detail Panel */}
      {panelOpen && activePanelTeam && (
        <DetailPanel
          team={activePanelTeam}
          tasks={tasks.filter((t) => t.team_id === activePanelTeam.id)}
          activeTab={activePanelTab}
          onTabChange={setActivePanelTab}
          onClose={closePanel}
        />
      )}
    </div>
  );
}

// ── Sub-components ──

function OverviewCard({ icon, bg, value, label, valueColor }: {
  icon: string; bg: string; value: string | number; label: string; valueColor?: string;
}) {
  return (
    <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', borderRadius: 12, padding: '16px 18px', display: 'flex', alignItems: 'center', gap: 14 }}>
      <div style={{ width: 40, height: 40, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18, background: bg }}>{icon}</div>
      <div>
        <div style={{ fontSize: 22, fontWeight: 700, lineHeight: 1, color: valueColor }}>{value}</div>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 3 }}>{label}</div>
      </div>
    </div>
  );
}

function StatusRing({ progress, color }: { progress: number; color: string }) {
  const r = 20, circ = 2 * Math.PI * r;
  const offset = circ - (circ * progress / 100);
  return (
    <svg width="48" height="48" viewBox="0 0 48 48">
      <circle cx="24" cy="24" r={r} fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth="4" />
      <circle cx="24" cy="24" r={r} fill="none" stroke={`var(--${color}-400)`} strokeWidth="4" strokeLinecap="round" strokeDasharray={circ} strokeDashoffset={offset} transform="rotate(-90 24 24)" style={{ transition: 'stroke-dashoffset 0.6s ease' }} />
      <text x="24" y="26" textAnchor="middle" fill="var(--text-primary)" fontSize="10" fontWeight="700" fontFamily="var(--font-mono)">{progress}%</text>
    </svg>
  );
}

function MetricPill({ value, label, color }: { value: number; label: string; color?: string }) {
  return (
    <div style={{ flex: 1, background: 'var(--bg-elevated)', borderRadius: 8, padding: '10px 12px', textAlign: 'center' }}>
      <div style={{ fontSize: 16, fontWeight: 700, lineHeight: 1, color }}>{value}</div>
      <div style={{ fontSize: 9, color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: 0.4, marginTop: 3 }}>{label}</div>
    </div>
  );
}

// ── Detail Panel ──

function DetailPanel({ team, tasks, activeTab, onTabChange, onClose }: {
  team: Team; tasks: TaskItem[]; activeTab: string;
  onTabChange: (t: 'tasks' | 'memory' | 'agents') => void; onClose: () => void;
}) {
  const runTasks = tasks.filter((t) => t.status === 'running');
  const doneTasks = tasks.filter((t) => t.status === 'completed');

  return (
    <>
      <div onClick={onClose} style={overlayStyle} />
      <div style={panelStyle}>
        <div style={panelHeaderStyle}>
          <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
            <div style={{ width: 42, height: 42, borderRadius: 11, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20, background: 'var(--gold-bg)', border: '1px solid var(--gold-border)' }}>
              🏗
            </div>
            <div>
              <div style={{ fontSize: 18, fontWeight: 700 }}>{team.name}</div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
                {team.collaboration_mode || 'Supervisor'} · {team.members?.length || 0} Agents
              </div>
            </div>
          </div>
          <button onClick={onClose} style={closeBtnStyle}>✕</button>
        </div>

        {/* Panel tabs */}
        <div style={{ display: 'flex', gap: 0, padding: '0 24px', borderBottom: '1px solid var(--border-subtle)' }}>
          {(['tasks', 'memory', 'agents'] as const).map((tab) => (
            <div
              key={tab}
              onClick={() => onTabChange(tab)}
              style={{
                padding: '12px 14px', fontSize: 12.5, fontWeight: 500, cursor: 'pointer',
                color: activeTab === tab ? 'var(--gold-400)' : 'var(--text-muted)',
                borderBottom: `2px solid ${activeTab === tab ? 'var(--gold-400)' : 'transparent'}`,
                transition: 'all 0.15s', whiteSpace: 'nowrap',
              }}
            >
              {tab === 'tasks' ? '任务' : tab === 'memory' ? 'Memory' : 'Agent'}
            </div>
          ))}
        </div>

        {/* Panel body */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px' }}>
          {activeTab === 'tasks' && (
            <>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8, marginBottom: 20 }}>
                <StatCard value={tasks.length} label="总任务" />
                <StatCard value={runTasks.length} label="执行中" color="var(--green-400)" />
                <StatCard value={doneTasks.length} label="已完成" />
                <StatCard value="97%" label="成功率" color="var(--blue-400)" />
              </div>
              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 10 }}>
                任务列表
              </div>
              {tasks.length === 0 ? (
                <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-dim)', fontSize: 13 }}>暂无任务</div>
              ) : (
                tasks.map((t) => {
                  const s = STATUS_STYLE[t.status] || STATUS_STYLE.pending;
                  return (
                    <div key={t.task_id} style={panelTaskCardStyle}>
                      <div style={{
                        width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
                        background: t.status === 'running' ? 'var(--green-400)' : 'var(--text-dim)',
                        boxShadow: t.status === 'running' ? '0 0 8px rgba(52,211,153,0.4)' : undefined,
                      }} />
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 13, fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                          {t.task_id}
                        </div>
                        <div style={{ fontSize: 10, color: 'var(--text-dim)', marginTop: 2, fontFamily: 'var(--font-mono)' }}>
                          {t.strategy || '-'} · {t.time || t.created_at || '-'}
                        </div>
                      </div>
                      <div style={{ width: 100, flexShrink: 0 }}>
                        <div style={{ height: 4, background: 'rgba(255,255,255,0.06)', borderRadius: 2, overflow: 'hidden', marginBottom: 3 }}>
                          <div style={{ height: '100%', borderRadius: 2, width: `${t.progress || 0}%`, background: t.status === 'completed' ? 'var(--green-400)' : 'var(--gold-500)' }} />
                        </div>
                        <div style={{ fontSize: 9, color: 'var(--text-dim)', fontFamily: 'var(--font-mono)', textAlign: 'right' }}>
                          {t.progress || 0}% · {t.nodes || '-'}
                        </div>
                      </div>
                      <span style={{
                        fontSize: 10, padding: '2px 8px', borderRadius: 10,
                        background: s.bg, color: s.color, fontWeight: 500,
                      }}>
                        {STATUS_LABEL[t.status] || t.status}
                      </span>
                    </div>
                  );
                })
              )}
            </>
          )}

          {activeTab === 'memory' && (
            <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-dim)', fontSize: 13 }}>
              🧠 Memory 功能开发中...
            </div>
          )}

          {activeTab === 'agents' && (
            <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-dim)', fontSize: 13 }}>
              🤖 Agent Memory 功能开发中...
            </div>
          )}
        </div>

        {/* Panel footer */}
        <div style={panelFooterStyle}>
          <button className="btn-primary" style={btnPrimaryStyle} onClick={() => navigate('/sop-designer')}>
            编辑工作流 →
          </button>
          <button className="btn-secondary" style={btnSecondaryStyle} onClick={() => alert('+ 新建 SOP')}>
            + 新建 SOP
          </button>
        </div>
      </div>
    </>
  );
}

function StatCard({ value, label, color }: { value: string | number; label: string; color?: string }) {
  return (
    <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', borderRadius: 10, padding: 14, textAlign: 'center' }}>
      <div style={{ fontSize: 22, fontWeight: 700, lineHeight: 1, color }}>{value}</div>
      <div style={{ fontSize: 10, color: 'var(--text-dim)', marginTop: 4 }}>{label}</div>
    </div>
  );
}

// ── Styles ──

const btnPrimaryStyle: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 6, padding: '8px 16px',
  borderRadius: 8, fontFamily: 'var(--font-body)', fontSize: 13, fontWeight: 500,
  border: 'none', cursor: 'pointer', transition: 'all 0.15s',
  background: 'linear-gradient(135deg, var(--gold-500), #d97706)',
  color: '#0a0f1e', boxShadow: '0 0 16px rgba(245,158,11,0.12)',
};

const btnSecondaryStyle: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 6, padding: '8px 16px',
  borderRadius: 8, fontFamily: 'var(--font-body)', fontSize: 13, fontWeight: 500,
  cursor: 'pointer', transition: 'all 0.15s',
  background: 'var(--bg-card)', color: 'var(--text-secondary)',
  border: '1px solid var(--border-medium)',
};

const teamCardStyle: React.CSSProperties = {
  background: 'var(--bg-card)', border: '1px solid var(--border-subtle)',
  borderRadius: 16, padding: 22, transition: 'all 0.25s', cursor: 'pointer', position: 'relative',
};

const teamAvatarStyle: React.CSSProperties = {
  width: 46, height: 46, borderRadius: 13, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22,
};

const agentRosterStyle: React.CSSProperties = {
  display: 'flex', alignItems: 'center', gap: 6, marginBottom: 16, padding: '10px 12px',
  background: 'var(--bg-elevated)', borderRadius: 10,
};

const rosterAvatarStyle: React.CSSProperties = {
  width: 30, height: 30, borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center',
  fontSize: 14, border: '2px solid var(--bg-elevated)', position: 'relative', marginRight: -6,
};

const activeTaskStyle: React.CSSProperties = {
  background: 'var(--bg-elevated)', borderRadius: 10, padding: '12px 14px', marginBottom: 14,
  borderLeft: '3px solid var(--gold-500)',
};

const memoryBarStyle: React.CSSProperties = {
  display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px',
  background: 'rgba(255,255,255,0.02)', borderRadius: 8, marginBottom: 14,
};

const cardFooterStyle: React.CSSProperties = {
  display: 'flex', gap: 6, paddingTop: 14, borderTop: '1px solid var(--border-subtle)',
};

const cardBtnStyle: React.CSSProperties = {
  flex: 1, padding: 8, borderRadius: 8, textAlign: 'center', fontSize: 11, fontWeight: 500,
  cursor: 'pointer', transition: 'all 0.15s', fontFamily: 'var(--font-body)',
  border: '1px solid var(--border-subtle)', background: 'transparent', color: 'var(--text-muted)',
};

const overlayStyle: React.CSSProperties = {
  position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 99,
};

const panelStyle: React.CSSProperties = {
  position: 'fixed', top: 0, right: 0, width: 640, height: '100vh',
  background: 'var(--bg-base)', borderLeft: '1px solid var(--border-subtle)',
  zIndex: 100, display: 'flex', flexDirection: 'column',
  boxShadow: '0 24px 48px rgba(0,0,0,0.4)',
};

const panelHeaderStyle: React.CSSProperties = {
  padding: '18px 24px 14px', borderBottom: '1px solid var(--border-subtle)',
  display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
};

const closeBtnStyle: React.CSSProperties = {
  background: 'none', border: 'none', color: 'var(--text-muted)', fontSize: 18,
  cursor: 'pointer', padding: '4px 8px', borderRadius: 6,
};

const panelTaskCardStyle: React.CSSProperties = {
  display: 'flex', alignItems: 'center', gap: 12, padding: '12px 14px',
  background: 'var(--bg-card)', border: '1px solid var(--border-subtle)',
  borderRadius: 10, marginBottom: 8, cursor: 'pointer', transition: 'all 0.15s',
};

const panelFooterStyle: React.CSSProperties = {
  padding: '16px 24px', borderTop: '1px solid var(--border-subtle)',
  display: 'flex', gap: 10, background: 'var(--bg-base)',
};

export default Tasks;

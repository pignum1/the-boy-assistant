/** 团队管理 v2（PR-C）
 *
 * 关键变化：
 *   - 创建向导 4 步：1) 选模式 → 2) 基本信息+成员 → 3) 模式特定配置 → 4) 确认
 *   - 三种模式（群聊式 / 主管式 / 图编排）各自的配置面板
 *   - Detail Panel 加「协作架构」tab 展示树形委派 / 群聊规则 / 图绑定
 */
import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../../shared/api/client';
import { sessionsApi } from '../../shared/api/sessions';
import type { Team } from '../../shared/types/agent';
import type { SessionInfo } from '../../shared/types/session';
import { getRoleInfo } from '../../shared/types/sop';
import { WorkflowSelector } from './WorkflowSelector';
import { AgentBindingPanel } from './AgentBindingPanel';
import type { WorkflowAgentBinding } from '../../shared/types/sop';

type CollabMode = 'swarm' | 'supervisor' | 'langgraph';

interface AgentItem {
  id: string; name: string; persona_id?: string; persona_name?: string;
  default_model_id?: string; model_name?: string; status?: string;
  tools?: string[];
}

interface AgentPoolStatus {
  agent_id: string; status: string; team_id?: string; current_task?: string;
}

interface SopSummary {
  id: string; name: string; description?: string; team_id: string;
}

interface WorkflowSummary {
  id: string; name: string; description?: string;
}

// ── 模式定义 ──

const MODES: Array<{ value: CollabMode; icon: string; title: string; subtitle: string; desc: string; example: string }> = [
  {
    value: 'swarm',
    icon: '💬',
    title: '群聊式',
    subtitle: 'AutoGen / OpenAI Swarm',
    desc: 'Agent 在群聊里自由对话，按策略轮流发言或互相协商。无主从关系，适合探索性任务、头脑风暴。',
    example: '研究讨论、方案评审、创意脑暴',
  },
  {
    value: 'supervisor',
    icon: '👑',
    title: '主管式',
    subtitle: 'CrewAI 风格',
    desc: '一个 Leader 拆解任务并委派给下属。多级层级（PM→架构师→开发），结构化执行。',
    example: '软件开发、产品交付、有明确分工的任务',
  },
  {
    value: 'langgraph',
    icon: '🔀',
    title: '图编排',
    subtitle: 'LangGraph / Dify',
    desc: '预定义有向图：节点 = Agent 任务，边 = 流转条件。流水线式执行，结果可预期。',
    example: '部署 SOP、审批流程、标准化业务',
  },
];

function getModeMeta(value?: string) {
  return MODES.find(m => m.value === value) || MODES[1]; // default supervisor
}

// ── 主页面 ──

export function Teams() {
  const navigate = useNavigate();
  const [teams, setTeams] = useState<Team[]>([]);
  const [allAgents, setAllAgents] = useState<AgentItem[]>([]);
  const [poolStatus, setPoolStatus] = useState<AgentPoolStatus[]>([]);
  const [sopMap, setSopMap] = useState<Record<string, SopSummary[]>>({});
  const [loading, setLoading] = useState(true);

  const [panelOpen, setPanelOpen] = useState(false);
  const [activeTeam, setActiveTeam] = useState<Team | null>(null);
  const [activeTab, setActiveTab] = useState<'overview' | 'members' | 'collab' | 'history'>('overview');

  const [wizardOpen, setWizardOpen] = useState(false);

  const fetchData = useCallback(async () => {
    const [tRes, aRes, pRes, sRes] = await Promise.allSettled([
      api.get<Team[]>('/api/v1/teams'),
      api.get<AgentItem[]>('/api/v1/agents'),
      api.get<{ agents: AgentPoolStatus[] }>('/api/v1/agents/pool/status'),
      api.get<SopSummary[]>('/api/v1/sops'),
    ]);
    if (tRes.status === 'fulfilled') setTeams(tRes.value);
    if (aRes.status === 'fulfilled') {
      const data = aRes.value as any;
      setAllAgents(Array.isArray(data) ? data : (data.items || []));
    }
    if (pRes.status === 'fulfilled') {
      const data = pRes.value as { agents?: AgentPoolStatus[] };
      setPoolStatus(data?.agents || []);
    }
    if (sRes.status === 'fulfilled') {
      const map: Record<string, SopSummary[]> = {};
      for (const s of sRes.value) { (map[s.team_id] ||= []).push(s); }
      setSopMap(map);
    }
    setLoading(false);
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  // 从SOP设计器返回时，恢复Team创建状态
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get('create_from_sop') === 'true') {
      const newWorkflowId = sessionStorage.getItem('team_create_new_workflow_id');
      const savedState = sessionStorage.getItem('team_create_wizard_state');

      if (savedState) {
        try {
          const state = JSON.parse(savedState);
          // 恢复状态
          setMode(state.mode || 'supervisor');
          setTeamName(state.team_name || '');
          setTeamDesc(state.team_desc || '');
          setSelectedAgents(new Set(state.selected_agents || []));
          if (state.swarm_config) {
            setSwarmMaxRounds(state.swarm_config.maxRounds || 10);
            setSwarmStrategy(state.swarm_config.strategy || 'auto');
            setSwarmTermination(state.swarm_config.termination || '');
          }
          if (state.supervisor_config) {
            setSupLeaderAgentId(state.supervisor_config.leaderId || '');
            setSupRelations(state.supervisor_config.relations || []);
          }
          // 设置新创建的Workflow ID
          if (newWorkflowId) {
            setLgWorkflowId(newWorkflowId);
          }
          // 打开向导并跳到Step 3
          setWizardOpen(true);
          setStep(3);
          // 清理sessionStorage
          sessionStorage.removeItem('team_create_new_workflow_id');
          sessionStorage.removeItem('team_create_wizard_state');
        } catch (e) {
          console.error('Failed to restore wizard state:', e);
        }
      }
      // 清理URL参数
      window.history.replaceState({}, '', '/teams');
    }
  }, []);

  const openPanel = (team: Team) => {
    setActiveTeam(team);
    setActiveTab('overview');
    setPanelOpen(true);
  };

  if (loading) {
    return (
      <div style={{ padding: '40px 32px', position: 'relative', zIndex: 1 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, letterSpacing: -0.5 }}>团队管理</h1>
        <p style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 8 }}>加载中...</p>
      </div>
    );
  }

  return (
    <div style={{ padding: '28px 32px', maxWidth: 1400, position: 'relative', zIndex: 1 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 700, letterSpacing: -0.5 }}>团队管理</h1>
          <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 6 }}>
            三种协作模式：💬 群聊式 · 👑 主管式 · 🔀 图编排
          </p>
        </div>
        <button className="btn-primary" style={btnPrimaryStyle} onClick={() => setWizardOpen(true)}>
          + 创建团队
        </button>
      </div>

      {/* 团队卡片 */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(380px, 1fr))', gap: 16 }}>
        {teams.map((team) => {
          const teamSops = sopMap[team.id] || [];
          const isActive = team.status === 'active';
          return (
            <TeamCard
              key={team.id}
              team={team}
              allAgents={allAgents}
              poolStatus={poolStatus}
              sopCount={teamSops.length}
              isActive={isActive}
              onClick={() => openPanel(team)}
            />
          );
        })}
      </div>

      {panelOpen && activeTeam && (
        <DetailPanel
          team={activeTeam}
          allAgents={allAgents}
          poolStatus={poolStatus}
          sopList={sopMap[activeTeam.id] || []}
          activeTab={activeTab}
          onTabChange={setActiveTab}
          onClose={() => setPanelOpen(false)}
          navigate={navigate}
        />
      )}

      {wizardOpen && (
        <CreateWizard
          allAgents={allAgents}
          onClose={() => setWizardOpen(false)}
          onCreated={() => { setWizardOpen(false); fetchData(); }}
        />
      )}

      <style>{`@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.4}}`}</style>
    </div>
  );
}

// ── 团队卡片 ──

function TeamCard({ team, allAgents, poolStatus, sopCount, isActive, onClick }: {
  team: Team; allAgents: AgentItem[]; poolStatus: AgentPoolStatus[];
  sopCount: number; isActive: boolean; onClick: () => void;
}) {
  const mode = (team.collaboration_mode || 'supervisor') as CollabMode;
  const modeMeta = getModeMeta(mode);
  const accent = mode === 'swarm' ? 'cyan' : mode === 'supervisor' ? 'gold' : 'purple';

  const teamAgents = (team.members || []).map((m) => {
    const agent = allAgents.find((a) => a.id === m.agent_id);
    const pool = poolStatus.find((p) => p.agent_id === m.agent_id);
    const role = getRoleInfo((m.role_name || (m as { role_slot?: string }).role_slot));
    return { ...m, agent, pool, role };
  });

  return (
    <div style={{ ...teamCardStyle, borderTop: `3px solid var(--${accent}-400)` }} onClick={onClick}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 14 }}>
        <div style={{
          width: 44, height: 44, borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 22, background: `var(--${accent}-bg)`, border: `1px solid var(--${accent}-border)`,
        }}>
          {modeMeta.icon}
        </div>
        <span style={{
          fontSize: 11, fontWeight: 500, padding: '4px 10px', borderRadius: 10,
          background: isActive ? 'var(--green-bg)' : 'rgba(148,163,184,0.06)',
          color: isActive ? 'var(--green-400)' : 'var(--text-muted)',
        }}>
          {isActive ? '运行中' : '休眠中'}
        </span>
      </div>

      <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 4 }}>{team.name}</div>
      <div style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.5, marginBottom: 14, minHeight: 36 }}>
        {team.description || '—'}
      </div>

      <div style={{ display: 'flex', gap: 20, marginBottom: 14 }}>
        <MetaItem label="模式" value={`${modeMeta.icon} ${modeMeta.title}`} />
        <MetaItem label="成员" value={`${team.members?.length || 0} Agent`} />
        <MetaItem label="SOP" value={`${sopCount} 个`} />
      </div>

      <div style={{ display: 'flex', marginBottom: 14 }}>
        {teamAgents.slice(0, 7).map((m, i) => (
          <div key={i} title={`${m.role.icon} ${m.role.label}: ${m.agent?.name || m.agent_id}`}
            style={{ ...rosterStyle, zIndex: 7 - i, background: `var(--${ACCENT_COLORS[i % ACCENT_COLORS.length]}-bg)` }}>
            {m.role.icon}
          </div>
        ))}
        {teamAgents.length > 7 && (
          <div style={{ ...rosterStyle, background: 'var(--bg-elevated)', fontSize: 10, color: 'var(--text-dim)' }}>
            +{teamAgents.length - 7}
          </div>
        )}
      </div>

      <div style={cardFooterStyle}>
        <span style={{
          fontSize: 10, padding: '3px 8px', borderRadius: 4, fontWeight: 500,
          background: `var(--${accent}-bg)`, color: `var(--${accent}-400)`,
          border: `1px solid var(--${accent}-border)`,
        }}>
          {modeMeta.icon} {modeMeta.title}
        </span>
        <span style={{ fontSize: 11, color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 4 }}>
          {isActive && <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--green-400)', animation: 'pulse 2s infinite' }} />}
          {isActive ? '活跃' : '空闲'}
        </span>
        <button style={settingsBtnStyle} onClick={(e) => { e.stopPropagation(); onClick(); }}>⚙</button>
      </div>
    </div>
  );
}

// ── Detail Panel ──

function DetailPanel({ team, allAgents, sopList, activeTab, onTabChange, onClose, navigate }: {
  team: Team; allAgents: AgentItem[]; poolStatus: AgentPoolStatus[];
  sopList: SopSummary[];
  activeTab: string; onTabChange: (t: 'overview' | 'members' | 'collab' | 'history') => void;
  onClose: () => void;
  navigate: (path: string) => void;
}) {
  const mode = (team.collaboration_mode || 'supervisor') as CollabMode;
  const modeMeta = getModeMeta(mode);

  const teamAgents = (team.members || []).map((m) => {
    const agent = allAgents.find((a) => a.id === m.agent_id);
    const role = getRoleInfo((m.role_name || (m as { role_slot?: string }).role_slot));
    return { ...m, agent, role };
  });

  return (
    <>
      <div onClick={onClose} style={overlayStyle} />
      <div style={panelStyle}>
        <div style={panelHeaderStyle}>
          <div style={{ display: 'flex', gap: 14, alignItems: 'flex-start' }}>
            <div style={{
              width: 44, height: 44, borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 22, background: 'var(--gold-bg)', border: '1px solid var(--gold-border)',
            }}>
              {modeMeta.icon}
            </div>
            <div>
              <div style={{ fontSize: 18, fontWeight: 700 }}>{team.name}</div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
                {modeMeta.title} · {team.members?.length || 0} Agents · {sopList.length} SOP
              </div>
            </div>
          </div>
          <button onClick={onClose} style={closeBtnStyle}>✕</button>
        </div>

        <div style={{ display: 'flex', gap: 0, padding: '0 24px', borderBottom: '1px solid var(--border-subtle)' }}>
          {(['overview', 'members', 'collab', 'history'] as const).map((tab) => (
            <div key={tab} onClick={() => onTabChange(tab)} style={{
              padding: '12px 14px', fontSize: 12.5, fontWeight: 500, cursor: 'pointer',
              color: activeTab === tab ? 'var(--gold-400)' : 'var(--text-muted)',
              borderBottom: `2px solid ${activeTab === tab ? 'var(--gold-400)' : 'transparent'}`,
              transition: 'all 0.15s', whiteSpace: 'nowrap',
            }}>
              {{ overview: '基本信息', members: '成员列表', collab: '协作架构', history: '历史' }[tab]}
            </div>
          ))}
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px' }}>
          {activeTab === 'overview' && (
            <>
              <FormSection title="基本信息">
                <FormField label="团队名称" value={team.name} />
                <FormField label="描述" value={team.description || ''} isTextarea />
                <div style={{ padding: '12px 14px', background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', borderRadius: 10, marginTop: 8 }}>
                  <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 6 }}>协作模式</div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <span style={{ fontSize: 24 }}>{modeMeta.icon}</span>
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 600 }}>{modeMeta.title}</div>
                      <div style={{ fontSize: 11, color: 'var(--text-dim)' }}>{modeMeta.subtitle}</div>
                    </div>
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 8, lineHeight: 1.6 }}>
                    {modeMeta.desc}
                  </div>
                </div>
              </FormSection>
            </>
          )}

          {activeTab === 'members' && (
            <>
              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 10 }}>
                团队成员 <span style={{ fontWeight: 400, color: 'var(--text-dim)' }}>({teamAgents.length} Agents)</span>
              </div>
              {teamAgents.map((m, i) => (
                <div key={i} style={memberCardStyle}>
                  <div style={{ width: 36, height: 36, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16, background: `var(--${ACCENT_COLORS[i % ACCENT_COLORS.length]}-bg)` }}>
                    {m.role.icon}
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 13, fontWeight: 600 }}>{m.agent?.name || m.agent_id}</div>
                    <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 2 }}>{m.role.label}</div>
                  </div>
                </div>
              ))}
            </>
          )}

          {activeTab === 'collab' && (
            <CollabConfigPanel team={team} allAgents={allAgents} navigate={navigate} />
          )}

          {activeTab === 'history' && (
            <TeamHistory teamId={team.id} navigate={navigate} />
          )}
        </div>
      </div>
    </>
  );
}

// ── 协作架构 Tab：根据 mode 显示不同内容 ──

function CollabConfigPanel({ team, allAgents, navigate }: { team: Team; allAgents: AgentItem[]; navigate: (path: string) => void }) {
  const mode = (team.collaboration_mode || 'supervisor') as CollabMode;
  const [config, setConfig] = useState<{
    mode: string;
    swarm?: { max_rounds: number; speak_strategy: string; termination_condition?: string };
    supervisor?: { leader_member_id?: string; relations: { member_id: string; supervisor_member_id: string }[] };
    langgraph?: { workflow_id?: string; workflow_name?: string; bindings: { node_key: string; agent_id: string }[] };
  } | null>(null);

  useEffect(() => {
    api.get<typeof config>(`/api/v1/teams/${team.id}/mode-config`).then(setConfig).catch(() => setConfig(null));
  }, [team.id]);

  if (!config) {
    return <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-dim)', fontSize: 13 }}>加载中...</div>;
  }

  if (mode === 'swarm') {
    return (
      <div>
        <FormSection title="💬 群聊配置">
          <div style={{ padding: '12px 14px', background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', borderRadius: 10 }}>
            <Row label="最大轮次" value={`${config.swarm?.max_rounds || 10} 轮`} />
            <Row label="发言策略" value={config.swarm?.speak_strategy || 'auto'} />
            <Row label="终止条件" value={config.swarm?.termination_condition || '默认（达成共识）'} />
          </div>
        </FormSection>
      </div>
    );
  }

  if (mode === 'supervisor') {
    const members = team.members || [];
    const leaderId = config.supervisor?.leader_member_id;
    const leader = members.find(m => m.id === leaderId);
    const relations = config.supervisor?.relations || [];

    // 构建树
    const childrenMap: Record<string, string[]> = {};
    for (const r of relations) {
      (childrenMap[r.supervisor_member_id] ||= []).push(r.member_id);
    }

    const renderNode = (memberId: string, depth: number): React.ReactNode => {
      const m = members.find(x => x.id === memberId);
      if (!m) return null;
      const agent = allAgents.find(a => a.id === m.agent_id);
      const role = getRoleInfo((m.role_name || (m as { role_slot?: string }).role_slot));
      const kids = childrenMap[memberId] || [];
      return (
        <div key={memberId} style={{ marginLeft: depth * 18 }}>
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8, padding: '6px 10px',
            background: depth === 0 ? 'var(--gold-bg)' : 'var(--bg-card)',
            border: depth === 0 ? '1px solid var(--gold-border)' : '1px solid var(--border-subtle)',
            borderRadius: 6, marginBottom: 6,
          }}>
            <span style={{ fontSize: 14 }}>{role.icon}</span>
            <span style={{ fontSize: 12, fontWeight: 500 }}>{agent?.name || '?'}</span>
            <span style={{ fontSize: 10, color: 'var(--text-dim)' }}>{role.label}</span>
            {depth === 0 && <span style={{ fontSize: 10, padding: '1px 6px', background: 'var(--gold-400)', color: '#0a0f1e', borderRadius: 3, fontWeight: 600 }}>LEADER</span>}
          </div>
          {kids.map(kid => renderNode(kid, depth + 1))}
        </div>
      );
    };

    return (
      <div>
        <FormSection title="👑 主管式委派树">
          {leader ? renderNode(leader.id!, 0) : (
            <div style={{ padding: 20, textAlign: 'center', color: 'var(--text-dim)', fontSize: 12 }}>
              未设置 Leader
            </div>
          )}
          <button
            onClick={(e) => {
              e.preventDefault();
              navigate(`/sop-designer?team_id=${team.id}`);
            }}
            style={{
              marginTop: 12,
              padding: '6px 12px',
              background: 'var(--bg-card)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 6,
              fontSize: 11,
              fontWeight: 500,
              color: 'var(--text-secondary)',
              cursor: 'pointer',
              width: '100%',
            }}
            title="编辑团队的工作流流程"
          >
            🔧 编辑工作流
          </button>
        </FormSection>
      </div>
    );
  }

  if (mode === 'langgraph') {
    const bindings = config.langgraph?.bindings || [];
    const workflowId = config.langgraph?.workflow_id;
    const workflowName = config.langgraph?.workflow_name || '未命名工作流';

    return (
      <div>
        <FormSection title="🔀 图编排配置">
          <div style={{ padding: '12px 14px', background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', borderRadius: 10, marginBottom: 12 }}>
            <Row label="Workflow ID" value={workflowId || '未绑定'} />
            <Row label="Workflow 名称" value={workflowName} />
            <button
              onClick={(e) => {
                e.preventDefault();
                // Navigate to team's SOP (filter by team_id)
                navigate(`/sop-designer?team_id=${team.id}`);
              }}
              style={{
                marginTop: 8,
                padding: '6px 12px',
                background: 'var(--purple-bg)',
                border: '1px solid var(--purple-border)',
                borderRadius: 6,
                fontSize: 11,
                fontWeight: 500,
                color: 'var(--purple-400)',
                cursor: 'pointer',
                width: '100%',
              }}
            >
              🔧 在 SOP 设计器中编辑
            </button>
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 12, marginBottom: 6 }}>
            节点绑定（{bindings.length}）
          </div>
          {bindings.length > 0 ? bindings.map((b, i) => {
            const a = allAgents.find(x => x.id === b.agent_id);
            return (
              <div key={i} style={{
                display: 'flex', alignItems: 'center', gap: 8, padding: '6px 10px',
                background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', borderRadius: 6, marginBottom: 6,
              }}>
                <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--purple-400)', flex: 1 }}>{b.node_key}</span>
                <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>→ {a?.name || b.agent_id}</span>
              </div>
            );
          }) : (
            <div style={{ padding: 16, textAlign: 'center', color: 'var(--text-dim)', fontSize: 11 }}>暂无节点绑定</div>
          )}
        </FormSection>
      </div>
    );
  }

  return null;
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', fontSize: 12 }}>
      <span style={{ color: 'var(--text-muted)' }}>{label}</span>
      <span style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>{value}</span>
    </div>
  );
}

// ── Create Wizard（4 步） ──

const ROLE_PRESETS = [
  { slot: 'pm', label: '产品经理', icon: '📋' },
  { slot: 'architect', label: '架构师', icon: '🏗️' },
  { slot: 'frontend_dev', label: '前端工程师', icon: '🖥️' },
  { slot: 'backend_dev', label: '后端工程师', icon: '💻' },
  { slot: 'tester', label: '测试工程师', icon: '🧪' },
  { slot: 'ui_designer', label: 'UI设计师', icon: '🎨' },
  { slot: 'devops', label: '部署运维', icon: '🚀' },
  { slot: 'custom', label: '自定义', icon: '🤖' },
];

function CreateWizard({ allAgents, onClose, onCreated }: {
  allAgents: AgentItem[]; onClose: () => void; onCreated: () => void;
}) {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [mode, setMode] = useState<CollabMode>('supervisor');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [icon, setIcon] = useState('👥');
  const [selectedAgents, setSelectedAgents] = useState<Set<string>>(new Set());
  const [agentRoles, setAgentRoles] = useState<Record<string, { role: string; customName: string }>>({});

  // 模式特定配置
  const [swarmMaxRounds, setSwarmMaxRounds] = useState(10);
  const [swarmStrategy, setSwarmStrategy] = useState<'auto' | 'round_robin' | 'priority'>('auto');
  const [swarmTermination, setSwarmTermination] = useState('达成共识或得出最终答案');

  const [supLeaderAgentId, setSupLeaderAgentId] = useState<string>('');
  // relations: 临时存 agent_id 对，提交时映射成 member_id
  const [supRelations, setSupRelations] = useState<Array<{ subordinateAgentId: string; supervisorAgentId: string }>>([]);

  const [lgWorkflowId, setLgWorkflowId] = useState<string>('');
  const [workflows, setWorkflows] = useState<WorkflowSummary[]>([]);
  const [lgBindings, setLgBindings] = useState<Array<{ node_key: string; agent_id: string }>>([]);

  const [workflowNodes, setWorkflowNodes] = useState<Array<{ id: string; label: string; type: string }>>([]);

  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (mode === 'langgraph') {
      api.get<WorkflowSummary[]>('/api/v1/workflows').then(setWorkflows).catch(() => {});
    }
  }, [mode]);

  // 当选择Workflow时，加载其节点信息
  useEffect(() => {
    if (!lgWorkflowId) {
      setWorkflowNodes([]);
      return;
    }
    api.get<{ nodes: Array<{ id: string; label: string; type: string }> }>(`/api/v1/workflows/${lgWorkflowId}`)
      .then((res) => setWorkflowNodes(res.nodes || []))
      .catch(() => setWorkflowNodes([]));
  }, [lgWorkflowId]);

  const toggleAgent = (id: string) => {
    const next = new Set(selectedAgents);
    if (next.has(id)) {
      next.delete(id);
      const r = { ...agentRoles }; delete r[id]; setAgentRoles(r);
    } else {
      next.add(id);
      setAgentRoles({ ...agentRoles, [id]: { role: 'backend_dev', customName: '' } });
    }
    setSelectedAgents(next);
  };

  const handleCreate = async () => {
    setSaving(true);
    try {
      const members = Array.from(selectedAgents).map((agentId) => {
        const cfg = agentRoles[agentId] || { role: 'backend_dev', customName: '' };
        const preset = ROLE_PRESETS.find(r => r.slot === cfg.role);
        const roleName = cfg.role === 'custom' ? (cfg.customName || '成员') : (preset?.label || cfg.role);
        return { agent_id: agentId, role_name: roleName, role_icon: preset?.icon || '🤖' };
      });

      // 1) 创建团队（带 collaboration_mode）
      const team = await api.post<Team>('/api/v1/teams', {
        name: name || '未命名团队',
        description,
        icon,
        collaboration_mode: mode,
        members,
      });

      // 2) 模式特定配置
      if (mode === 'swarm') {
        await api.put(`/api/v1/teams/${team.id}/swarm-config`, {
          max_rounds: swarmMaxRounds,
          speak_strategy: swarmStrategy,
          termination_condition: swarmTermination || null,
        });
      } else if (mode === 'supervisor') {
        // 重新查 team 拿到 member.id（创建时只返了 agent_id）
        const detailed = await api.get<Team>(`/api/v1/teams/${team.id}`);
        const memberIdByAgent: Record<string, string> = {};
        for (const m of (detailed.members || [])) {
          if (m.agent_id && m.id) memberIdByAgent[m.agent_id] = m.id;
        }
        if (supLeaderAgentId && memberIdByAgent[supLeaderAgentId]) {
          await api.put(`/api/v1/teams/${team.id}/supervisor-leader`, {
            leader_member_id: memberIdByAgent[supLeaderAgentId],
          });
        }
        const relations = supRelations.map(r => ({
          member_id: memberIdByAgent[r.subordinateAgentId],
          supervisor_member_id: memberIdByAgent[r.supervisorAgentId],
        })).filter(r => r.member_id && r.supervisor_member_id);
        if (relations.length > 0) {
          await api.put(`/api/v1/teams/${team.id}/supervisor-relations`, { relations });
        }
      } else if (mode === 'langgraph') {
        if (lgWorkflowId) {
          await api.put(`/api/v1/teams/${team.id}/langgraph-workflow`, {
            workflow_id: lgWorkflowId,
          });
        }
        if (lgBindings.length > 0) {
          await api.put(`/api/v1/teams/${team.id}/langgraph-bindings`, {
            bindings: lgBindings,
          });
        }
      }

      onCreated();
    } catch (e) {
      alert('创建失败: ' + String(e));
    } finally {
      setSaving(false);
    }
  };

  const stepLabels = ['协作模式', '基本信息+成员', '模式配置', '确认创建'];

  return (
    <>
      <div onClick={onClose} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 200 }} />
      <div style={{
        position: 'fixed', top: '4%', left: '50%', transform: 'translateX(-50%)',
        width: 900, maxHeight: '92vh', background: 'var(--bg-base)', border: '1px solid var(--border-subtle)',
        borderRadius: 16, zIndex: 201, display: 'flex', flexDirection: 'column', overflow: 'hidden',
        boxShadow: '0 24px 80px rgba(0,0,0,0.5)',
      }}>
        <div style={{ padding: '20px 24px 14px', borderBottom: '1px solid var(--border-subtle)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ fontSize: 17, fontWeight: 700 }}>创建新团队</div>
          <button onClick={onClose} style={closeBtnStyle}>✕</button>
        </div>

        {/* Steps */}
        <div style={{ display: 'flex', gap: 0, padding: '14px 24px', borderBottom: '1px solid var(--border-subtle)' }}>
          {stepLabels.map((label, i) => (
            <div key={i} style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 8 }}>
              <div style={{
                width: 26, height: 26, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 11, fontWeight: 600, flexShrink: 0,
                border: `2px solid ${step === i + 1 ? 'var(--gold-500)' : step > i + 1 ? 'var(--green-400)' : 'var(--border-medium)'}`,
                color: step >= i + 1 ? (step > i + 1 ? 'var(--green-400)' : 'var(--gold-400)') : 'var(--text-dim)',
                background: step >= i + 1 ? (step > i + 1 ? 'var(--green-bg)' : 'var(--gold-bg)') : 'var(--bg-card)',
              }}>
                {step > i + 1 ? '✓' : i + 1}
              </div>
              <span style={{ fontSize: 11, fontWeight: 500, color: step === i + 1 ? 'var(--gold-400)' : step > i + 1 ? 'var(--green-400)' : 'var(--text-dim)', whiteSpace: 'nowrap' }}>{label}</span>
              {i < stepLabels.length - 1 && <div style={{ flex: 1, height: 2, background: step > i + 1 ? 'var(--green-400)' : 'var(--border-subtle)', margin: '0 8px' }} />}
            </div>
          ))}
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px' }}>
          {/* Step 1: 选模式 */}
          {step === 1 && (
            <>
              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 14 }}>
                选择协作模式
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {MODES.map(m => (
                  <div key={m.value} onClick={() => setMode(m.value)} style={{
                    padding: '16px 18px', borderRadius: 10, cursor: 'pointer',
                    background: mode === m.value ? 'var(--gold-bg)' : 'var(--bg-card)',
                    border: mode === m.value ? '2px solid var(--gold-500)' : '1px solid var(--border-subtle)',
                    transition: 'all 0.15s',
                  }}>
                    <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
                      <div style={{ fontSize: 32 }}>{m.icon}</div>
                      <div style={{ flex: 1 }}>
                        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                          <div style={{ fontSize: 15, fontWeight: 700 }}>{m.title}</div>
                          <div style={{ fontSize: 10, color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>{m.subtitle}</div>
                        </div>
                        <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 6, lineHeight: 1.6 }}>{m.desc}</div>
                        <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 6 }}>📌 适用：{m.example}</div>
                      </div>
                      <div style={{
                        width: 20, height: 20, borderRadius: '50%',
                        border: `2px solid ${mode === m.value ? 'var(--gold-500)' : 'var(--text-dim)'}`,
                        background: mode === m.value ? 'var(--gold-500)' : 'transparent',
                        flexShrink: 0,
                      }} />
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}

          {/* Step 2: 基本信息 + 成员 */}
          {step === 2 && (
            <>
              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 10 }}>基本信息</div>
              <div style={{ display: 'flex', gap: 12, marginBottom: 12 }}>
                <div style={{ flex: 1 }}><FormField label="团队名称" value={name} onChange={setName} placeholder="例如：产品开发团队" /></div>
                <div style={{ width: 80 }}><FormField label="图标" value={icon} onChange={setIcon} placeholder="👥" /></div>
              </div>
              <FormField label="描述" value={description} onChange={setDescription} placeholder="团队职责和目标" isTextarea />

              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 10, marginTop: 20 }}>
                选择成员 ({selectedAgents.size} 已选)
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 280, overflowY: 'auto' }}>
                {allAgents.map((a) => {
                  const isSel = selectedAgents.has(a.id);
                  const cfg = agentRoles[a.id] || { role: 'backend_dev', customName: '' };
                  return (
                    <div key={a.id} style={{
                      display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px',
                      background: isSel ? 'var(--gold-bg)' : 'var(--bg-card)',
                      border: isSel ? '1px solid var(--gold-border)' : '1px solid var(--border-subtle)',
                      borderRadius: 8,
                    }}>
                      <input type="checkbox" checked={isSel} onChange={() => toggleAgent(a.id)} style={{ cursor: 'pointer' }} />
                      <span style={{ fontSize: 16 }}>{isSel ? '✅' : '🤖'}</span>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 12.5, fontWeight: 500, color: 'var(--text-primary)' }}>{a.name}</div>
                        {a.persona_name && <div style={{ fontSize: 10, color: 'var(--text-dim)' }}>{a.persona_name}</div>}
                      </div>
                      {isSel && (
                        <>
                          <select value={cfg.role} onChange={(e) => setAgentRoles({ ...agentRoles, [a.id]: { ...cfg, role: e.target.value } })} style={miniSelectStyle}>
                            {ROLE_PRESETS.map(r => <option key={r.slot} value={r.slot}>{r.icon} {r.label}</option>)}
                          </select>
                          {cfg.role === 'custom' && (
                            <input value={cfg.customName} onChange={(e) => setAgentRoles({ ...agentRoles, [a.id]: { ...cfg, customName: e.target.value } })} placeholder="角色名" style={{ ...miniInputStyle, width: 80 }} />
                          )}
                        </>
                      )}
                    </div>
                  );
                })}
              </div>
            </>
          )}

          {/* Step 3: 模式配置 */}
          {step === 3 && mode === 'swarm' && (
            <>
              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 10 }}>💬 群聊配置</div>
              <FormField label="最大轮次" value={String(swarmMaxRounds)} onChange={(v) => setSwarmMaxRounds(parseInt(v) || 10)} />
              <div style={{ marginBottom: 12 }}>
                <label style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4, display: 'block', fontWeight: 500 }}>发言策略</label>
                <select value={swarmStrategy} onChange={(e) => setSwarmStrategy(e.target.value as 'auto' | 'round_robin' | 'priority')} style={selectStyle}>
                  <option value="auto">auto（LLM 智能选择）</option>
                  <option value="round_robin">round_robin（轮询）</option>
                  <option value="priority">priority（必要成员优先）</option>
                </select>
              </div>
              <FormField label="终止条件" value={swarmTermination} onChange={setSwarmTermination} isTextarea />
            </>
          )}
          {step === 3 && mode === 'supervisor' && (
            <>
              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 10 }}>👑 主管式配置</div>
              <div style={{ marginBottom: 12 }}>
                <label style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4, display: 'block', fontWeight: 500 }}>Leader（顶层主管）</label>
                <select value={supLeaderAgentId} onChange={(e) => setSupLeaderAgentId(e.target.value)} style={selectStyle}>
                  <option value="">— 选择 Leader —</option>
                  {Array.from(selectedAgents).map(id => {
                    const a = allAgents.find(x => x.id === id);
                    return a ? <option key={id} value={id}>{a.name}</option> : null;
                  })}
                </select>
              </div>
              <div style={{ fontSize: 11, fontWeight: 500, color: 'var(--text-secondary)', marginTop: 16, marginBottom: 8 }}>
                委派关系（每个成员选直属上级）
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 280, overflowY: 'auto' }}>
                {Array.from(selectedAgents).filter(id => id !== supLeaderAgentId).map(subId => {
                  const sub = allAgents.find(a => a.id === subId);
                  const existing = supRelations.find(r => r.subordinateAgentId === subId);
                  return (
                    <div key={subId} style={{
                      display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px',
                      background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', borderRadius: 8,
                    }}>
                      <span style={{ fontSize: 12, color: 'var(--text-secondary)', minWidth: 120 }}>{sub?.name}</span>
                      <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>→ 直属上级：</span>
                      <select
                        value={existing?.supervisorAgentId || ''}
                        onChange={(e) => {
                          const supId = e.target.value;
                          setSupRelations(prev => {
                            const filtered = prev.filter(r => r.subordinateAgentId !== subId);
                            if (supId) filtered.push({ subordinateAgentId: subId, supervisorAgentId: supId });
                            return filtered;
                          });
                        }}
                        style={{ ...miniSelectStyle, flex: 1 }}
                      >
                        <option value="">— 无 —</option>
                        {Array.from(selectedAgents).filter(id => id !== subId).map(id => {
                          const a = allAgents.find(x => x.id === id);
                          return a ? <option key={id} value={id}>{a.name}</option> : null;
                        })}
                      </select>
                    </div>
                  );
                })}
              </div>
            </>
          )}
          {step === 3 && mode === 'langgraph' && (
            <>
              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 10 }}>🔀 图编排配置</div>

              {/* Workflow选择 */}
              <WorkflowSelector
                selectedWorkflowId={lgWorkflowId}
                onWorkflowSelect={(id) => setLgWorkflowId(id || '')}
                onWorkflowCreate={() => {
                  console.log('[TeamCreate] onWorkflowCreate triggered');
                  // 保存当前状态，跳转到SOP设计器
                  const stateToSave = {
                    mode, step: 3,
                    team_name: name, team_desc: description,
                    selected_agents: Array.from(selectedAgents),
                    swarm_config: { maxRounds: swarmMaxRounds, strategy: swarmStrategy, termination: swarmTermination },
                    supervisor_config: { leaderId: supLeaderAgentId, relations: supRelations },
                  };
                  console.log('[TeamCreate] Saving state:', stateToSave);
                  sessionStorage.setItem('team_create_wizard_state', JSON.stringify(stateToSave));
                  console.log('[TeamCreate] Navigating to SOP designer');
                  navigate('/sop-designer?from_team_create=true');
                }}
              />

              {/* Workflow节点列表（当选择Workflow后显示） */}
              {lgWorkflowId && (
                <>
                  <div style={{ marginTop: 16, padding: '10px 12px', background: 'var(--bg-card)', borderRadius: 8, border: '1px solid var(--border-subtle)' }}>
                    <div style={{ fontSize: 11, fontWeight: 500, color: 'var(--text-secondary)', marginBottom: 6 }}>
                      Workflow节点预览
                    </div>
                    {workflowNodes.length > 0 ? (
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                        {workflowNodes.map((node) => (
                          <span
                            key={node.id}
                            style={{
                              fontSize: 10,
                              padding: '3px 8px',
                              background: 'var(--purple-bg)',
                              border: '1px solid var(--purple-border)',
                              borderRadius: 4,
                              color: 'var(--purple-400)',
                            }}
                          >
                            {node.label}
                          </span>
                        ))}
                      </div>
                    ) : (
                      <div style={{ fontSize: 10, color: 'var(--text-dim)' }}>
                        加载节点信息中...
                      </div>
                    )}
                  </div>

                  {/* Agent绑定配置 */}
                  <div style={{ marginTop: 16 }}>
                    <AgentBindingPanel
                      availableAgents={allAgents}
                      selectedAgentIds={selectedAgents}
                      bindings={lgBindings}
                      onBindingsChange={setLgBindings}
                      workflowNodes={workflowNodes}
                    />
                  </div>
                </>
              )}

              {!lgWorkflowId && (
                <div style={{ marginTop: 12, padding: 12, background: 'var(--bg-elevated)', borderRadius: 8, border: '1px dashed var(--border-medium)', fontSize: 11, color: 'var(--text-muted)' }}>
                  💡 选择Workflow后，可以配置团队成员到Workflow节点的绑定关系
                </div>
              )}
            </>
          )}

          {/* Step 4: 确认 */}
          {step === 4 && (
            <>
              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 10 }}>确认创建</div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <ReviewCard label="协作模式" value={`${getModeMeta(mode).icon} ${getModeMeta(mode).title}`} />
                <ReviewCard label="团队名称" value={name || '未命名'} />
                <ReviewCard label="成员数" value={`${selectedAgents.size} 人`} />
                <ReviewCard label="图标" value={icon} />
              </div>
              <div style={{ marginTop: 14, fontSize: 11, color: 'var(--text-muted)' }}>
                {mode === 'swarm' && `· 群聊 max=${swarmMaxRounds} 轮，策略=${swarmStrategy}`}
                {mode === 'supervisor' && `· Leader=${allAgents.find(a => a.id === supLeaderAgentId)?.name || '未选'}，${supRelations.length} 条委派关系`}
                {mode === 'langgraph' && (
                  <>
                    · Workflow={workflows.find(w => w.id === lgWorkflowId)?.name || '未绑定'}
                    {lgBindings.length > 0 && ` · ${lgBindings.length} 个节点绑定`}
                  </>
                )}
              </div>
            </>
          )}
        </div>

        <div style={{ padding: '14px 24px', borderTop: '1px solid var(--border-subtle)', display: 'flex', justifyContent: 'space-between' }}>
          <button
            style={{ visibility: step > 1 ? 'visible' : 'hidden', background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontFamily: 'var(--font-body)', fontSize: 13 }}
            onClick={() => setStep((s) => s - 1)}
          >
            ← 上一步
          </button>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn-secondary" style={btnSecondaryStyle} onClick={onClose}>取消</button>
            {step < 4 ? (
              <button
                className="btn-primary"
                style={btnPrimaryStyle}
                disabled={step === 2 && selectedAgents.size === 0}
                onClick={() => setStep((s) => s + 1)}
              >
                下一步 →
              </button>
            ) : (
              <button className="btn-primary" style={btnPrimaryStyle} onClick={handleCreate} disabled={saving}>
                {saving ? '创建中...' : '创建团队'}
              </button>
            )}
          </div>
        </div>
      </div>
    </>
  );
}

// ── 团队历史 ──

function TeamHistory({ teamId, navigate }: { teamId: string; navigate: (path: string) => void }) {
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    sessionsApi.list({ team_id: teamId, limit: 30 })
      .then(({ sessions: s }) => { setSessions(s); setLoading(false); })
      .catch(() => setLoading(false));
  }, [teamId]);

  if (loading) return <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-dim)', fontSize: 13 }}>加载中...</div>;
  if (sessions.length === 0) return <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-dim)', fontSize: 13 }}>📋 暂无历史会话</div>;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {sessions.map((s) => (
        <div key={s.id} onClick={() => navigate(`/chat?session=${s.id}&team=${s.team_id}`)}
          style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 14px', background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', borderRadius: 10, cursor: 'pointer' }}>
          <div style={{ width: 36, height: 36, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16, background: 'var(--blue-bg)' }}>
            💬
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 13, fontWeight: 600 }}>{s.title}</div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>{s.message_count} 条消息</div>
          </div>
          <span style={{ fontSize: 10, color: 'var(--text-dim)' }}>→</span>
        </div>
      ))}
    </div>
  );
}

// ── 辅助组件 / Styles ──

function MetaItem({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <span style={{ fontSize: 10, color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: 0.5 }}>{label}</span>
      <span style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-secondary)' }}>{value}</span>
    </div>
  );
}

function FormSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 20 }}>
      <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 10, paddingBottom: 6, borderBottom: '1px solid var(--border-subtle)' }}>{title}</div>
      {children}
    </div>
  );
}

function FormField({ label, value, onChange, placeholder, isTextarea }: {
  label: string; value: string; onChange?: (v: string) => void;
  placeholder?: string; isTextarea?: boolean;
}) {
  const s: React.CSSProperties = { width: '100%', padding: '7px 10px', background: 'var(--bg-card)', border: '1px solid var(--border-medium)', borderRadius: 6, color: 'var(--text-primary)', fontSize: 12, fontFamily: 'var(--font-body)', outline: 'none' };
  return (
    <div style={{ marginBottom: 12 }}>
      <label style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4, display: 'block', fontWeight: 500 }}>{label}</label>
      {isTextarea ? (
        <textarea style={{ ...s, minHeight: 60, resize: 'vertical' as const }} value={value} onChange={(e) => onChange?.(e.target.value)} placeholder={placeholder} />
      ) : (
        <input style={s} value={value} onChange={(e) => onChange?.(e.target.value)} placeholder={placeholder} />
      )}
    </div>
  );
}

function ReviewCard({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', borderRadius: 10, padding: 16 }}>
      <div style={{ fontSize: 10, color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6 }}>{label}</div>
      <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{value}</div>
    </div>
  );
}

const ACCENT_COLORS = ['gold', 'blue', 'green', 'purple', 'cyan', 'amber', 'red'];

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
  background: 'var(--bg-card)', color: 'var(--text-secondary)', border: '1px solid var(--border-medium)',
};

const teamCardStyle: React.CSSProperties = {
  background: 'var(--bg-card)', border: '1px solid var(--border-subtle)',
  borderRadius: 14, padding: 22, transition: 'all 0.2s', cursor: 'pointer',
  position: 'relative', overflow: 'hidden',
};
const rosterStyle: React.CSSProperties = {
  width: 30, height: 30, borderRadius: 8, display: 'flex', alignItems: 'center',
  justifyContent: 'center', fontSize: 14, border: '2px solid var(--bg-card)',
  position: 'relative', marginRight: -6,
};
const cardFooterStyle: React.CSSProperties = {
  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
  paddingTop: 14, borderTop: '1px solid var(--border-subtle)', marginTop: 0,
};
const settingsBtnStyle: React.CSSProperties = {
  background: 'none', border: 'none', color: 'var(--text-dim)', fontSize: 14,
  cursor: 'pointer', padding: '3px 6px', borderRadius: 4,
};
const overlayStyle: React.CSSProperties = { position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 99 };
const panelStyle: React.CSSProperties = {
  position: 'fixed', top: 0, right: 0, width: 620, height: '100vh',
  background: 'var(--bg-base)', borderLeft: '1px solid var(--border-subtle)',
  zIndex: 100, display: 'flex', flexDirection: 'column', boxShadow: '0 24px 48px rgba(0,0,0,0.4)',
};
const panelHeaderStyle: React.CSSProperties = {
  padding: '20px 24px 16px', borderBottom: '1px solid var(--border-subtle)',
  display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
};
const closeBtnStyle: React.CSSProperties = {
  background: 'none', border: 'none', color: 'var(--text-muted)', fontSize: 18,
  cursor: 'pointer', padding: '4px 8px', borderRadius: 6,
};
const memberCardStyle: React.CSSProperties = {
  display: 'flex', alignItems: 'center', gap: 12, padding: '12px 14px',
  background: 'var(--bg-card)', border: '1px solid var(--border-subtle)',
  borderRadius: 10, marginBottom: 8,
};
const miniSelectStyle: React.CSSProperties = { padding: '4px 6px', background: 'var(--bg-elevated)', border: '1px solid var(--border-medium)', borderRadius: 5, color: 'var(--text-primary)', fontSize: 11, fontFamily: 'var(--font-body)' };
const miniInputStyle: React.CSSProperties = { padding: '4px 6px', background: 'var(--bg-elevated)', border: '1px solid var(--border-medium)', borderRadius: 5, color: 'var(--text-primary)', fontSize: 11 };
const selectStyle: React.CSSProperties = { width: '100%', padding: '8px 10px', background: 'var(--bg-elevated)', border: '1px solid var(--border-medium)', borderRadius: 6, color: 'var(--text-primary)', fontSize: 12, fontFamily: 'var(--font-body)', outline: 'none' };

export default Teams;

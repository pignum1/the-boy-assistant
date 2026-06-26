/** 团队成员面板：显示团队所有 Agent，支持添加/移除成员 */
import { useState, useEffect } from 'react';
import { api } from '../../shared/api/client';

interface TeamMember {
  agent_id: string;
  agent_name: string;
  role_slot: string;
  joined_at: string;
}

interface AgentItem {
  id: string;
  name: string;
  persona_name?: string;
  status?: string;
}

interface MemberPanelProps {
  teamId: string;
  memberCount: number;
  onCountChange?: (count: number) => void;
  agentStatuses?: Record<string, { status: string; agent_name: string; summary: string; timestamp: string }>;
}

const ROLE_LABEL_MAP: Record<string, { label: string; icon: string; color: string }> = {
  pm:           { label: '产品经理', icon: '📋', color: 'var(--gold-400)' },
  dev:          { label: '开发工程师', icon: '💻', color: 'var(--blue-400)' },
  qa:           { label: '测试工程师', icon: '🧪', color: 'var(--green-400)' },
  designer:     { label: '设计师', icon: '🎨', color: 'var(--purple-400)' },
  ui_designer:  { label: 'UI设计师', icon: '🎨', color: 'var(--purple-400)' },
  architect:    { label: '架构师', icon: '🏗️', color: 'var(--cyan-400)' },
  backend_dev:  { label: '后端工程师', icon: '⚙️', color: 'var(--blue-400)' },
  frontend_dev: { label: '前端工程师', icon: '🖥️', color: 'var(--sky-400)' },
  tester:       { label: '测试员', icon: '🧪', color: 'var(--green-400)' },
  devops:       { label: '部署运维', icon: '🚀', color: 'var(--orange-400)' },
  lead:         { label: '技术主管', icon: '👑', color: 'var(--gold-400)' },
  supervisor:   { label: '主管', icon: '👑', color: 'var(--gold-400)' },
};

// 状态灯颜色映射
const STATUS_DISPLAY: Record<string, { color: string; label: string }> = {
  idle:     { color: 'var(--text-dim)',      label: '空闲' },
  thinking: { color: 'var(--gold-400)',      label: '思考中' },
  working:  { color: 'var(--blue-400)',      label: '工作中' },
  done:     { color: 'var(--green-400)',     label: '完成' },
  busy:     { color: 'var(--purple-400)',    label: '忙碌' },
  error:    { color: 'var(--red-400)',       label: '出错' },
};

export function MemberPanel({ teamId, memberCount, onCountChange, agentStatuses = {} }: MemberPanelProps) {
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [agents, setAgents] = useState<AgentItem[]>([]);
  const [open, setOpen] = useState(true);  // 面板展开/折叠
  const [showAddModal, setShowAddModal] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState('');
  const [selectedRole, setSelectedRole] = useState('dev');
  const [saving, setSaving] = useState(false);

  // 获取团队成员 + 可用 Agent 列表
  useEffect(() => {
    api.get<{ members: TeamMember[] }>(`/api/v1/teams/${teamId}`)
      .then((team) => setMembers(team.members || []))
      .catch(() => {});
    api.get<AgentItem[]>('/api/v1/agents')
      .then(setAgents)
      .catch(() => {});
  }, [teamId, memberCount]);  // memberCount 变化时刷新

  const handleAddMember = async () => {
    if (!selectedAgent || !selectedRole) return;
    setSaving(true);
    try {
      await api.post(`/api/v1/teams/${teamId}/members`, {
        agent_id: selectedAgent,
        role_slot: selectedRole,
      });
      setShowAddModal(false);
      setSelectedAgent('');
      onCountChange?.(members.length + 1);
    } catch (e) {
      alert('添加失败: ' + String(e));
    } finally {
      setSaving(false);
    }
  };

  const handleRemoveMember = async (agentId: string) => {
    try {
      await api.del(`/api/v1/teams/${teamId}/members/${agentId}`);
      onCountChange?.(members.length - 1);
    } catch (e) {
      alert('移除失败: ' + String(e));
    }
  };

  const getRoleInfo = (roleName: string) => {
    const mapped = ROLE_LABEL_MAP[roleName];
    return mapped || { label: roleName, icon: '🤖', color: 'var(--text-muted)' };
  };
  const colorForRole = (roleName: string) => getRoleInfo(roleName).color;

  return (
    <div style={panelStyle}>
      {/* Header */}
      <div onClick={() => setOpen(!open)} style={panelHeaderStyle}>
        <span style={{ fontSize: 12, transform: open ? 'rotate(90deg)' : 'rotate(0deg)', transition: 'transform 0.15s', display: 'inline-block' }}>▶</span>
        <span style={{ fontWeight: 600, fontSize: 13 }}>👥 团队成员</span>
        <span style={{ fontSize: 11, color: 'var(--text-dim)', marginLeft: 'auto' }}>{members.length}</span>
        <button
          onClick={(e) => { e.stopPropagation(); setShowAddModal(true); }}
          style={addBtnStyle}
        >
          +
        </button>
      </div>

      {/* Member List */}
      {open && (
        <div style={memberListStyle}>
          {members.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 16, color: 'var(--text-dim)', fontSize: 11 }}>
              暂无成员
            </div>
          ) : (
            members.map((m: TeamMember & { role_name?: string; role_icon?: string }) => {
              const roleName = m.role_name || m.role_slot || '成员';
              const roleIcon = (m as { role_icon?: string }).role_icon || getRoleInfo(roleName).icon;
              const roleLabel = getRoleInfo(roleName).label;
              const statusInfo = agentStatuses[m.agent_id];
              const status = statusInfo?.status || 'idle';
              const statusConfig = STATUS_DISPLAY[status] || STATUS_DISPLAY.idle;
              return (
                <div key={m.agent_id} style={memberItemStyle} title={statusInfo?.summary || statusConfig.label}>
                  <div style={{
                    width: 28, height: 28, borderRadius: 7, display: 'flex',
                    alignItems: 'center', justifyContent: 'center', fontSize: 14,
                    background: 'var(--bg-elevated)',
                  }}>
                    {roleIcon}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 11.5, fontWeight: 550, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {m.agent_name}
                    </div>
                    <div style={{ fontSize: 9.5, color: colorForRole(roleName) }}>
                      {roleLabel}
                    </div>
                  </div>
                  <div style={{
                    width: 8, height: 8, borderRadius: '50%',
                    background: statusConfig.color,
                    flexShrink: 0,
                    boxShadow: status === 'thinking' || status === 'working' ? `0 0 6px ${statusConfig.color}` : undefined,
                    transition: 'background 0.3s, box-shadow 0.3s',
                  }} />
                  <button
                    onClick={(e) => { e.stopPropagation(); handleRemoveMember(m.agent_id); }}
                    title="移出团队"
                    style={removeBtnStyle}
                  >
                    ✕
                  </button>
                </div>
              );
            })
          )}
        </div>
      )}

      {/* Add Member Modal */}
      {showAddModal && (
        <>
          <div onClick={() => setShowAddModal(false)} style={overlayStyle} />
          <div style={modalStyle}>
            <div style={modalHeaderStyle}>
              <div style={{ fontWeight: 600, fontSize: 15 }}>添加团队成员</div>
              <button onClick={() => setShowAddModal(false)} style={closeBtnStyle}>✕</button>
            </div>
            <div style={{ padding: '16px 20px' }}>
              <label style={labelStyle}>选择 Agent</label>
              <select
                style={selectStyle}
                value={selectedAgent}
                onChange={(e) => setSelectedAgent(e.target.value)}
              >
                <option value="">— 选择 Agent —</option>
                {agents
                  .filter((a) => !members.find((m) => m.agent_id === a.id))
                  .map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name} ({a.persona_name || '无 Persona'})
                    </option>
                  ))}
              </select>
              <label style={{ ...labelStyle, marginTop: 14 }}>角色</label>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
                {ROLE_SLOTS.map((r) => (
                  <div
                    key={r.slot}
                    onClick={() => setSelectedRole(r.slot)}
                    style={{
                      padding: '8px 10px', borderRadius: 6, cursor: 'pointer',
                      fontSize: 12, display: 'flex', alignItems: 'center', gap: 6,
                      background: selectedRole === r.slot ? 'var(--gold-bg)' : 'var(--bg-elevated)',
                      border: selectedRole === r.slot ? '1px solid var(--gold-border)' : '1px solid var(--border-subtle)',
                    }}
                  >
                    <span>{r.icon}</span>
                    <span>{r.label}</span>
                  </div>
                ))}
              </div>
            </div>
            <div style={modalFooterStyle}>
              <button className="btn-secondary" style={btnSecondaryStyle} onClick={() => setShowAddModal(false)}>取消</button>
              <button
                className="btn-primary"
                style={{ ...btnPrimaryStyle, opacity: selectedAgent ? 1 : 0.5 }}
                onClick={handleAddMember}
                disabled={!selectedAgent || saving}
              >
                {saving ? '添加中...' : '添加'}
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// ── Styles ──

const panelStyle: React.CSSProperties = {
  display: 'flex', flexDirection: 'column',
  flex: 1, overflow: 'hidden',
};

const panelHeaderStyle: React.CSSProperties = {
  display: 'flex', alignItems: 'center', gap: 6,
  padding: '10px 12px', cursor: 'pointer',
  borderBottom: '1px solid var(--border-subtle)',
};

const memberListStyle: React.CSSProperties = {
  flex: 1, overflowY: 'auto', padding: '6px 8px',
};

const memberItemStyle: React.CSSProperties = {
  display: 'flex', alignItems: 'center', gap: 8,
  padding: '6px 8px', borderRadius: 8, marginBottom: 3,
  transition: 'background 0.1s',
};

const addBtnStyle: React.CSSProperties = {
  background: 'none', border: 'none', color: 'var(--gold-400)',
  fontSize: 16, cursor: 'pointer', padding: '0 4px', fontWeight: 700,
};

const removeBtnStyle: React.CSSProperties = {
  background: 'none', border: 'none', color: 'var(--text-dim)',
  cursor: 'pointer', fontSize: 10, padding: '1px 3px', opacity: 0.3,
};

const overlayStyle: React.CSSProperties = {
  position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 300,
};

const modalStyle: React.CSSProperties = {
  position: 'fixed', top: '20%', left: '50%', transform: 'translateX(-50%)',
  width: 400, zIndex: 301, borderRadius: 14, overflow: 'hidden',
  background: 'var(--bg-base)', border: '1px solid var(--border-subtle)',
  boxShadow: '0 24px 48px rgba(0,0,0,0.5)',
};

const modalHeaderStyle: React.CSSProperties = {
  padding: '16px 20px', borderBottom: '1px solid var(--border-subtle)',
  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
};

const modalFooterStyle: React.CSSProperties = {
  padding: '12px 20px', borderTop: '1px solid var(--border-subtle)',
  display: 'flex', justifyContent: 'flex-end', gap: 8,
};

const closeBtnStyle: React.CSSProperties = {
  background: 'none', border: 'none', color: 'var(--text-muted)',
  fontSize: 16, cursor: 'pointer',
};

const labelStyle: React.CSSProperties = {
  fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)',
  marginBottom: 6, display: 'block',
};

const selectStyle: React.CSSProperties = {
  width: '100%', padding: '8px 10px', borderRadius: 6,
  background: 'var(--bg-elevated)', border: '1px solid var(--border-medium)',
  color: 'var(--text-primary)', fontSize: 12, fontFamily: 'var(--font-body)',
  outline: 'none',
};

const btnPrimaryStyle: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 6, padding: '8px 14px',
  borderRadius: 8, fontFamily: 'var(--font-body)', fontSize: 12, fontWeight: 500,
  border: 'none', cursor: 'pointer',
  background: 'linear-gradient(135deg, var(--gold-500), #d97706)',
  color: '#0a0f1e',
};

const btnSecondaryStyle: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 6, padding: '8px 14px',
  borderRadius: 8, fontFamily: 'var(--font-body)', fontSize: 12, fontWeight: 500,
  cursor: 'pointer',
  background: 'var(--bg-card)', color: 'var(--text-secondary)',
  border: '1px solid var(--border-medium)',
};

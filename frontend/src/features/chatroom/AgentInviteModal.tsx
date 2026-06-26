/** Agent invitation modal — select agents to invite into the chat room */
import { useState, useEffect } from 'react';

interface AgentSummary {
  agent_id: string;
  name: string;
  role: string;
  status: string;
}

interface Props {
  missingRoles: string[];
  availableAgents: AgentSummary[];
  onInvite: (agentId: string) => void;
  onSkip: () => void;
  onClose: () => void;
}

export function AgentInviteModal({
  missingRoles,
  availableAgents,
  onInvite,
  onSkip,
  onClose,
}: Props) {
  const [selected, setSelected] = useState<string | null>(null);

  const roleNames: Record<string, string> = {
    architect: '架构师',
    backend_dev: '后端工程师',
    frontend_dev: '前端工程师',
    tester: '测试员',
    ui_designer: 'UI设计师',
    devops: '部署运维工程师',
    pm: '产品经理',
  };

  const matchingAgents = availableAgents.filter((a) =>
    missingRoles.includes(a.role)
  );

  return (
    <div style={overlayStyle}>
      <div style={modalStyle} onClick={(e) => e.stopPropagation()}>
        <div style={headerStyle}>
          <h3 style={{ fontSize: 14, fontWeight: 600 }}>
            ⚠️ 缺少 Agent
          </h3>
          <button onClick={onClose} style={closeBtnStyle}>
            ✕
          </button>
        </div>

        <div style={{ padding: '12px 0' }}>
          <p style={{ fontSize: 11, color: '#94a3b8', marginBottom: 8 }}>
            当前团队缺少以下角色:{' '}
            {missingRoles.map((r) => roleNames[r] || r).join('、')}
          </p>

          {matchingAgents.length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {matchingAgents.map((agent) => (
                <div
                  key={agent.agent_id}
                  onClick={() => setSelected(agent.agent_id)}
                  style={{
                    ...agentCardStyle,
                    borderColor:
                      selected === agent.agent_id
                        ? 'var(--gold-400)'
                        : 'rgba(148,163,184,0.1)',
                    background:
                      selected === agent.agent_id
                        ? 'rgba(245,158,11,0.06)'
                        : 'transparent',
                  }}
                >
                  <span style={{ fontSize: 18 }}>🤖</span>
                  <div>
                    <div style={{ fontSize: 11, fontWeight: 600 }}>
                      {agent.name}
                    </div>
                    <div style={{ fontSize: 9, color: '#64748b' }}>
                      {roleNames[agent.role] || agent.role} · {agent.status}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p style={{ fontSize: 10, color: '#64748b' }}>
              没有可用的Agent。你可以快速创建一个新Agent。
            </p>
          )}
        </div>

        <div style={footerStyle}>
          <button onClick={onSkip} style={skipBtnStyle}>
            ⏭ 跳过
          </button>
          <button
            onClick={() => selected && onInvite(selected)}
            disabled={!selected}
            style={inviteBtnStyle(!!selected)}
          >
            📋 邀请
          </button>
        </div>
      </div>
    </div>
  );
}

const overlayStyle: React.CSSProperties = {
  position: 'fixed',
  inset: 0,
  zIndex: 50,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  background: 'rgba(0,0,0,0.5)',
};

const modalStyle: React.CSSProperties = {
  width: 360,
  maxHeight: 400,
  background: '#111827',
  border: '1px solid rgba(148,163,184,0.1)',
  borderRadius: 10,
  padding: '14px 16px',
  overflowY: 'auto',
};

const headerStyle: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
};

const closeBtnStyle: React.CSSProperties = {
  background: 'none',
  border: 'none',
  color: '#64748b',
  fontSize: 16,
  cursor: 'pointer',
};

const agentCardStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  padding: '8px 10px',
  borderRadius: 6,
  border: '1px solid',
  cursor: 'pointer',
  transition: 'all 0.15s',
};

const footerStyle: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'flex-end',
  gap: 8,
  paddingTop: 8,
  borderTop: '1px solid rgba(148,163,184,0.06)',
};

const skipBtnStyle: React.CSSProperties = {
  padding: '6px 14px',
  borderRadius: 5,
  background: 'transparent',
  border: '1px solid rgba(148,163,184,0.1)',
  color: '#64748b',
  fontSize: 11,
  cursor: 'pointer',
};

function inviteBtnStyle(enabled: boolean): React.CSSProperties {
  return {
    padding: '6px 14px',
    borderRadius: 5,
    background: enabled
      ? 'linear-gradient(135deg, #f59e0b, #d97706)'
      : '#1e293b',
    border: 'none',
    color: enabled ? '#000' : '#475569',
    fontSize: 11,
    fontWeight: 600,
    cursor: enabled ? 'pointer' : 'not-allowed',
  };
}

/** 新建会话弹窗：团队卡片选择 + 显示协作模式 */
import { useState, useEffect, useMemo } from 'react';
import { sessionsApi } from '../../shared/api/sessions';
import type { Team } from '../../shared/types/agent';
import { DirectoryPicker } from './DirectoryPicker';

interface Props { teams: Team[]; preSelectedTeamId?: string; onClose: () => void; onCreated: (sessionId: string, teamId: string) => void; }

const MODE_META: Record<string, { icon: string; label: string; color: string; bg: string; border: string }> = {
  swarm:      { icon: '💬', label: '群聊式', color: 'var(--cyan-400)',   bg: 'var(--cyan-bg)',   border: 'var(--cyan-border)' },
  supervisor: { icon: '👑', label: '主管式', color: 'var(--gold-400)',   bg: 'var(--gold-bg)',   border: 'var(--gold-border)' },
  langgraph:  { icon: '🔀', label: '图编排', color: 'var(--purple-400)', bg: 'var(--purple-bg)', border: 'var(--purple-border)' },
};

function modeOf(team: Team): string {
  return (team.collaboration_mode || team.mode || 'supervisor');
}

export function NewSessionModal({ teams, preSelectedTeamId, onClose, onCreated }: Props) {
  const [selectedTeamId, setSelectedTeamId] = useState(preSelectedTeamId || '');
  const [workspacePath, setWorkspacePath] = useState('');
  const [creating, setCreating] = useState(false);
  const [search, setSearch] = useState('');

  useEffect(() => { if (preSelectedTeamId) setSelectedTeamId(preSelectedTeamId); }, [preSelectedTeamId]);

  const handleCreate = async () => {
    if (!selectedTeamId) return;
    setCreating(true);
    try {
      const session = await sessionsApi.create({
        team_id: selectedTeamId,
        workspace_path: workspacePath || undefined,
      });
      onCreated(session.id, selectedTeamId);
    } catch (e) { alert('创建失败: ' + String(e)); }
    finally { setCreating(false); }
  };

  const filtered = useMemo(() => {
    if (!search.trim()) return teams;
    const q = search.toLowerCase();
    return teams.filter(t =>
      (t.name || '').toLowerCase().includes(q) ||
      (t.description || '').toLowerCase().includes(q)
    );
  }, [teams, search]);

  return (
    <>
      <div onClick={onClose} style={overlayStyle} />
      <div style={modalStyle}>
        <div style={headerStyle}>
          <div>
            <div style={{ fontSize: 18, fontWeight: 700 }}>开始新对话</div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
              选择一个团队 · 协作模式决定执行风格
            </div>
          </div>
          <button onClick={onClose} style={closeBtnStyle}>✕</button>
        </div>
        <div style={bodyStyle}>
          <div style={{ marginBottom: 12 }}>
            <input
              placeholder="搜索团队..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={searchStyle}
            />
          </div>

          <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 8, display: 'flex', justifyContent: 'space-between' }}>
            <span>团队 ({filtered.length})</span>
            <span style={{ color: 'var(--text-dim)' }}>{teams.length > filtered.length && `已筛选 / 共 ${teams.length}`}</span>
          </div>

          <div style={teamsListStyle}>
            {filtered.length === 0 && (
              <div style={{ padding: 28, textAlign: 'center', color: 'var(--text-dim)', fontSize: 12 }}>
                没有匹配的团队
              </div>
            )}
            {filtered.map(t => {
              const mode = modeOf(t);
              const meta = MODE_META[mode] || MODE_META.supervisor;
              const sel = t.id === selectedTeamId;
              return (
                <div
                  key={t.id}
                  onClick={() => setSelectedTeamId(t.id)}
                  style={teamCardStyle(sel)}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <div style={{
                      width: 32, height: 32, borderRadius: 8,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: 18, background: meta.bg, border: `1px solid ${meta.border}`,
                      flexShrink: 0,
                    }}>
                      {t.icon || meta.icon}
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {t.name}
                      </div>
                      <div style={{ display: 'flex', gap: 6, marginTop: 3, alignItems: 'center', flexWrap: 'wrap' }}>
                        <span style={{
                          fontSize: 9, padding: '1px 6px', borderRadius: 3,
                          background: meta.bg, color: meta.color, border: `1px solid ${meta.border}`,
                          fontFamily: 'var(--font-mono)', fontWeight: 500,
                        }}>
                          {meta.icon} {meta.label}
                        </span>
                        <span style={{ fontSize: 10, color: 'var(--text-dim)' }}>
                          {t.members?.length || 0} Agent
                        </span>
                      </div>
                    </div>
                    {sel && (
                      <span style={{
                        width: 18, height: 18, borderRadius: '50%',
                        background: 'var(--gold-500)', color: '#0a0f1e',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        fontSize: 11, fontWeight: 700,
                      }}>✓</span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          <div style={{ marginTop: 16 }}>
            <label style={labelStyle}>工作空间目录（可选）</label>
            <DirectoryPicker selectedPath={workspacePath} onSelect={setWorkspacePath} onClear={() => setWorkspacePath('')} />
          </div>
        </div>
        <div style={footerStyle}>
          <button className="btn-secondary" style={btnSecondaryStyle} onClick={onClose}>取消</button>
          <button className="btn-primary" style={{ ...btnPrimaryStyle, opacity: selectedTeamId ? 1 : 0.5 }} onClick={handleCreate} disabled={!selectedTeamId || creating}>
            {creating ? '创建中...' : '开始对话 →'}
          </button>
        </div>
      </div>
    </>
  );
}

const overlayStyle: React.CSSProperties = { position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 200 };
const modalStyle: React.CSSProperties = { position: 'fixed', top: '10%', left: '50%', transform: 'translateX(-50%)', width: 560, maxHeight: '82vh', zIndex: 201, background: 'var(--bg-base)', border: '1px solid var(--border-subtle)', borderRadius: 16, display: 'flex', flexDirection: 'column', boxShadow: '0 24px 80px rgba(0,0,0,0.5)', overflow: 'hidden' };
const headerStyle: React.CSSProperties = { padding: '18px 22px 14px', borderBottom: '1px solid var(--border-subtle)', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' };
const bodyStyle: React.CSSProperties = { padding: '16px 22px', flex: 1, overflowY: 'auto' };
const footerStyle: React.CSSProperties = { padding: '14px 22px', borderTop: '1px solid var(--border-subtle)', display: 'flex', justifyContent: 'flex-end', gap: 8 };
const labelStyle: React.CSSProperties = { fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 6, display: 'block' };
const searchStyle: React.CSSProperties = { width: '100%', padding: '8px 12px', borderRadius: 6, background: 'var(--bg-elevated)', border: '1px solid var(--border-medium)', color: 'var(--text-primary)', fontSize: 12, fontFamily: 'var(--font-body)', outline: 'none' };
const teamsListStyle: React.CSSProperties = { display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 320, overflowY: 'auto', padding: 2 };
const teamCardStyle = (selected: boolean): React.CSSProperties => ({
  padding: '10px 12px', borderRadius: 8, cursor: 'pointer',
  background: selected ? 'var(--gold-bg)' : 'var(--bg-card)',
  border: selected ? '1px solid var(--gold-500)' : '1px solid var(--border-subtle)',
  transition: 'all 0.15s',
});
const closeBtnStyle: React.CSSProperties = { background: 'none', border: 'none', color: 'var(--text-muted)', fontSize: 18, cursor: 'pointer', padding: '4px 8px', borderRadius: 6 };
const btnPrimaryStyle: React.CSSProperties = { display: 'inline-flex', alignItems: 'center', gap: 6, padding: '8px 16px', borderRadius: 8, fontFamily: 'var(--font-body)', fontSize: 13, fontWeight: 500, border: 'none', cursor: 'pointer', transition: 'all 0.15s', background: 'linear-gradient(135deg, var(--gold-500), #d97706)', color: '#0a0f1e', boxShadow: '0 0 16px rgba(245,158,11,0.12)' };
const btnSecondaryStyle: React.CSSProperties = { display: 'inline-flex', alignItems: 'center', gap: 6, padding: '8px 16px', borderRadius: 8, fontFamily: 'var(--font-body)', fontSize: 13, fontWeight: 500, cursor: 'pointer', transition: 'all 0.15s', background: 'var(--bg-card)', color: 'var(--text-secondary)', border: '1px solid var(--border-medium)' };

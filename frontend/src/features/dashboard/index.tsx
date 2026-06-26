import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../../shared/api/client';
import { sessionsApi } from '../../shared/api/sessions';
import { NewSessionModal } from '../sessions/NewSessionModal';

interface DashboardData { teams: any[]; sessions: any[]; agent_summary: { total: number; idle: number; busy: number }; }
interface SopInfo { id: string; name: string; is_template: boolean; }

export function Dashboard() {
  const navigate = useNavigate();
  const [data, setData] = useState<DashboardData>({ teams: [], sessions: [], agent_summary: { total: 0, idle: 0, busy: 0 } });
  const [sops, setSops] = useState<SopInfo[]>([]);
  const [showNewSession, setShowNewSession] = useState(false);

  useEffect(() => {
    api.get<DashboardData>('/api/v1/sessions/dashboard').then(setData).catch(() => {});
    api.get<SopInfo[]>('/api/v1/sops').then(setSops).catch(() => {});
  }, [showNewSession]);

  const handleStartChat = async (teamId: string) => {
    try { const s = await sessionsApi.create({ team_id: teamId }); navigate(`/chat?session=${s.id}&team=${s.team_id}`); }
    catch (e) { alert('创建失败: ' + String(e)); }
  };

  const formatTime = (iso: string) => { const m = Math.floor((Date.now() - new Date(iso).getTime()) / 60000); return m < 1 ? '刚刚' : m < 60 ? `${m}分钟前` : `${Math.floor(m / 60)}小时前`; };

  return (
    <div className="main-area">
      <div style={{ position: 'relative', zIndex: 1, padding: '28px 32px', maxWidth: 1400 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 28 }}>
          <div><h1 style={{ fontSize: 24, fontWeight: 700 }}>工作台</h1><p style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 4 }}>全局概览 · 实时状态</p></div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-dim)' }}>{new Date().toLocaleString('zh-CN', { month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit' })}</span>
            <button className="btn-primary" style={btnPrimaryStyle} onClick={() => setShowNewSession(true)}>+ 开始新对话</button>
          </div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14, marginBottom: 24 }}>
          <StatCard label="团队" value={data.teams.length} color="gold" sub="全部团队" />
          <StatCard label="Agent" value={data.agent_summary.total} color="green" sub={`可用 ${data.agent_summary.idle} / 繁忙 ${data.agent_summary.busy}`} />
          <StatCard label="SOP" value={sops.length} color="purple" sub="已定义流程" />
          <StatCard label="活跃会话" value={data.sessions.length} color="blue" sub="进行中" />
        </div>
        {data.sessions.length > 0 && (
          <div style={{ marginBottom: 20 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 10 }}>💬 活跃会话</div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 10 }}>
              {data.sessions.map((s: any) => (
                <div key={s.id} onClick={() => navigate(`/chat?session=${s.id}&team=${s.team_id}`)} style={sessionCardStyle}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.title}</div>
                    <span style={{ fontSize: 8, color: 'var(--green-400)' }}>●</span>
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-dim)', marginBottom: 6 }}>{s.team_name} · {s.message_count} 条消息</div>
                  {s.task_total > 0 && <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}><div style={{ flex: 1, height: 3, borderRadius: 2, background: 'var(--border-subtle)' }}><div style={{ width: `${(s.task_completed/s.task_total)*100}%`, height: '100%', borderRadius: 2, background: 'var(--green-400)' }} /></div><span style={{ fontSize: 10, color: 'var(--text-dim)' }}>{s.task_completed}/{s.task_total}</span></div>}
                  <div style={{ fontSize: 10, color: 'var(--text-dim)' }}>{formatTime(s.updated_at)}</div>
                </div>
              ))}
            </div>
          </div>
        )}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
          <SectionCard title="👥 团队" badge="L4">
            {data.teams.map((t: any) => (
              <div key={t.id} onClick={() => handleStartChat(t.id)} style={listItemStyle}>
                <div style={{ width: 32, height: 32, borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14, background: 'var(--gold-bg)', border: '1px solid var(--gold-border)' }}>{t.icon || '👥'}</div>
                <div style={{ flex: 1 }}><div style={{ fontSize: 12.5, fontWeight: 550 }}>{t.name}</div><div style={{ fontSize: 10, color: 'var(--text-muted)' }}>{t.member_count} 成员</div></div>
                <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 8, background: t.status==='active'?'var(--green-bg)':'rgba(148,163,184,0.06)', color: t.status==='active'?'var(--green-400)':'var(--text-muted)' }}>{t.status==='active'?'活跃':t.status}</span>
              </div>
            ))}
          </SectionCard>
          <SectionCard title="📋 SOP 流程" badge="L4">
            {sops.map((s: any) => (
              <div key={s.id} onClick={() => navigate(`/sop-designer/${s.id}`)} style={listItemStyle}>
                <div style={{ width: 32, height: 32, borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14, background: 'var(--purple-bg)', border: '1px solid var(--purple-border)' }}>📋</div>
                <div style={{ flex: 1 }}><div style={{ fontSize: 12.5, fontWeight: 550 }}>{s.name}</div></div>
                {s.is_template && <span style={{ fontSize: 9, padding: '2px 6px', borderRadius: 4, background: 'var(--blue-bg)', color: 'var(--blue-400)' }}>模板</span>}
              </div>
            ))}
          </SectionCard>
        </div>
      </div>
      {showNewSession && <NewSessionModal teams={data.teams} onClose={() => setShowNewSession(false)} onCreated={(id, teamId) => { setShowNewSession(false); navigate(`/chat?session=${id}&team=${teamId}`); }} />}
    </div>
  );
}

function StatCard({ label, value, color, sub }: { label: string; value: number; color: string; sub: string }) {
  const map: Record<string, string> = { gold: 'var(--gold-400)', green: 'var(--green-400)', blue: 'var(--blue-400)', purple: 'var(--purple-400)' };
  return <div style={{ padding: '18px 20px', borderRadius: 10, background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', display: 'flex', flexDirection: 'column', gap: 6 }}>
    <div style={{ fontSize: 11, fontWeight: 500, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 0.5 }}>{label}</div>
    <div style={{ fontSize: 32, fontWeight: 700, color: map[color] || 'var(--text-primary)', lineHeight: 1 }}>{value}</div>
    <div style={{ fontSize: 11, color: 'var(--text-dim)' }}>{sub}</div>
  </div>;
}

function SectionCard({ title, badge, children }: { title: string; badge?: string; children: React.ReactNode }) {
  return <div style={{ padding: 16, borderRadius: 10, background: 'var(--bg-card)', border: '1px solid var(--border-subtle)' }}>
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12, paddingBottom: 10, borderBottom: '1px solid var(--border-subtle)' }}>
      <span style={{ fontSize: 14, fontWeight: 600 }}>{title}</span>
      {badge && <span style={{ fontSize: 9, padding: '2px 6px', borderRadius: 4, background: 'var(--gold-bg)', color: 'var(--gold-400)', fontFamily: 'var(--font-mono)' }}>{badge}</span>}
    </div>
    {children}
  </div>;
}

const btnPrimaryStyle: React.CSSProperties = { display: 'inline-flex', alignItems: 'center', gap: 6, padding: '8px 16px', borderRadius: 8, fontFamily: 'var(--font-body)', fontSize: 13, fontWeight: 500, border: 'none', cursor: 'pointer', background: 'linear-gradient(135deg, var(--gold-500), #d97706)', color: '#0a0f1e', boxShadow: '0 0 16px rgba(245,158,11,0.12)' };
const listItemStyle: React.CSSProperties = { display: 'flex', alignItems: 'center', gap: 10, padding: '12px 14px', borderRadius: 8, cursor: 'pointer', transition: 'background 0.15s' };
const sessionCardStyle: React.CSSProperties = { padding: '14px 16px', borderRadius: 10, background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', cursor: 'pointer', transition: 'all 0.15s' };

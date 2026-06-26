import { useState, useEffect } from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import { sessionsApi } from '../shared/api/sessions';
import { api } from '../shared/api/client';
import type { SessionInfo } from '../shared/types/session';
import type { Team } from '../shared/types/agent';
import { NewSessionModal } from '../features/sessions/NewSessionModal';
import { useTheme } from '../contexts/ThemeContext';

const NAV_ITEMS = [
  { path: '/', label: '工作台', icon: '📊', desc: '全局概览 · 实时状态' },
  { path: '/tasks', label: '任务中心', icon: '⚡', desc: 'SOP 任务执行' },
  { path: '/teams', label: '团队管理', icon: '👥', desc: '团队配置与成员' },
  { path: '/sop-designer', label: 'SOP 设计器', icon: '🔧', desc: '工作流设计' },
  { path: '/workflows', label: '工作流列表', icon: '🔀', desc: '查看与管理工作流' },
  { path: '/chat', label: '聊天室', icon: '💬', desc: '多 Agent 协作对话' },
];

const RESOURCE_ITEMS = [
  { path: '/resources/models', label: '模型管理', icon: '🧠' },
  { path: '/resources/mcp-servers', label: 'MCP 服务器', icon: '🔌' },
  { path: '/resources/skills', label: 'Skill 管理', icon: '📐' },
  { path: '/resources/personas', label: 'Persona 管理', icon: '🎭' },
  { path: '/resources/agents', label: 'Agent 管理', icon: '🤖' },
];

function groupSessions(sessions: SessionInfo[]): { today: SessionInfo[]; yesterday: SessionInfo[]; thisWeek: SessionInfo[]; older: SessionInfo[] } {
  const now = new Date();
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const yesterdayStart = todayStart - 86400000;
  const weekStart = todayStart - 6 * 86400000;
  const today: SessionInfo[] = [], yesterday: SessionInfo[] = [], thisWeek: SessionInfo[] = [], older: SessionInfo[] = [];
  for (const s of sessions) {
    const d = new Date(s.updated_at).getTime();
    if (d >= todayStart) today.push(s);
    else if (d >= yesterdayStart) yesterday.push(s);
    else if (d >= weekStart) thisWeek.push(s);
    else older.push(s);
  }
  return { today, yesterday, thisWeek, older };
}

export function Sidebar() {
  const location = useLocation();
  const navigate = useNavigate();
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [teams, setTeams] = useState<Team[]>([]);
  const [showNewSession, setShowNewSession] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<{ id: string; title: string } | null>(null);
  const [hoveredSession, setHoveredSession] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState(false);
  const [navExpanded, setNavExpanded] = useState(false);

  const refreshSessions = () => {
    sessionsApi.list({ limit: 50 }).then(({ sessions: s }) => setSessions(s)).catch(() => {});
  };

  useEffect(() => {
    refreshSessions();
    api.get<Team[]>('/api/v1/teams').then(setTeams).catch(() => {});
  }, [location.pathname]);

  const handleDeleteSession = (id: string, title: string) => setDeleteConfirm({ id, title });

  const confirmDelete = async () => {
    if (!deleteConfirm) return;
    try {
      await sessionsApi.delete(deleteConfirm.id);
      setDeleteConfirm(null);
      refreshSessions();
    } catch (e) {
      alert('删除失败: ' + String(e));
    }
  };

  const grouped = groupSessions(sessions.filter((s) => s.status === 'active'));
  const isActive = (path: string) => location.pathname === path || (path !== '/' && location.pathname.startsWith(path));

  return (
    <>
      <aside style={asideStyle(collapsed)}>
        {/* Logo */}
        <div style={logoSectionStyle(collapsed)}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: collapsed ? 'center' : 'flex-start', gap: collapsed ? 0 : 10 }}>
            <div style={logoIconStyle}>B</div>
            {!collapsed && <div>
              <span style={{ fontWeight: 700, fontSize: 17, color: 'var(--text-primary)' }}>The Boy</span>
              <span style={{ fontSize: 10, color: 'var(--text-muted)', fontWeight: 400, marginLeft: 4 }}>v5.0</span>
            </div>}
          </div>
        </div>

        {/* New Chat button */}
        <div style={{ padding: collapsed ? '0 4px' : '0 10px', marginBottom: 4 }}>
          <button style={newChatBtnStyle(collapsed)} onClick={() => { if (collapsed) setCollapsed(false); setShowNewSession(true); }}>
            <span style={{ fontSize: 16 }}>+</span>
            {!collapsed && <span>新对话</span>}
          </button>
        </div>

        {/* Session History - moved below new chat button */}
        {!collapsed && (
          <div style={historyContainerStyle}>
            {sessions.filter((s) => s.status === 'active').length === 0 ? (
              <div style={emptyHistoryStyle}>暂无会话</div>
            ) : (
              <>
                {grouped.today.length > 0 && (
                  <div style={groupStyle}>
                    <div style={groupLabelStyle}>今天</div>
                    {grouped.today.map((s) => renderSessionItem(s, navigate, handleDeleteSession, hoveredSession, setHoveredSession))}
                  </div>
                )}
                {grouped.yesterday.length > 0 && (
                  <div style={groupStyle}>
                    <div style={groupLabelStyle}>昨天</div>
                    {grouped.yesterday.map((s) => renderSessionItem(s, navigate, handleDeleteSession, hoveredSession, setHoveredSession))}
                  </div>
                )}
                {grouped.thisWeek.length > 0 && (
                  <div style={groupStyle}>
                    <div style={groupLabelStyle}>本周</div>
                    {grouped.thisWeek.map((s) => renderSessionItem(s, navigate, handleDeleteSession, hoveredSession, setHoveredSession))}
                  </div>
                )}
                {grouped.older.length > 0 && (
                  <div style={groupStyle}>
                    <div style={groupLabelStyle}>更早</div>
                    {grouped.older.map((s) => renderSessionItem(s, navigate, handleDeleteSession, hoveredSession, setHoveredSession))}
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {/* Spacer to push nav to bottom */}
        <div style={{ flex: 0, minHeight: 0 }} />

        {/* 主导航 — 可折叠，默认收起 */}
        {!collapsed && (
          <div style={{ borderTop: '1px solid var(--border-subtle)' }}>
            <div
              onClick={() => setNavExpanded(!navExpanded)}
              style={{ fontSize: 10, color: 'var(--text-dim)', padding: '6px 12px', fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}
            >
              菜单
              <span style={{ fontSize: 10, transform: navExpanded ? 'rotate(90deg)' : 'rotate(0deg)', transition: 'transform 0.2s' }}>▶</span>
            </div>
            {navExpanded && (
              <div style={{ padding: '0 8px 8px' }}>
                {NAV_ITEMS.map(item => (
                  <NavLink
                    key={item.path}
                    to={item.path}
                    end={item.path === '/'}
                    style={navItemStyle(isActive(item.path))}
                  >
                    <span style={{ fontSize: 14, width: 22, textAlign: 'center' }}>{item.icon}</span>
                    <span style={{ fontSize: 12, fontWeight: 500 }}>{item.label}</span>
                  </NavLink>
                ))}
                <div style={{ height: 1, background: 'var(--border-subtle)', margin: '6px 4px' }} />
                <div style={{ height: 1, background: 'var(--border-subtle)', margin: '6px 4px' }} />
                {RESOURCE_ITEMS.map(item => (
                  <NavLink
                    key={item.path}
                    to={item.path}
                    style={navItemStyle(isActive(item.path))}
                  >
                    <span style={{ fontSize: 13, width: 22, textAlign: 'center' }}>{item.icon}</span>
                    <span style={{ fontSize: 11.5 }}>{item.label}</span>
                  </NavLink>
                ))}
                <div style={{ height: 1, background: 'var(--border-subtle)', margin: '6px 4px' }} />
                <ThemeMenuItem />
              </div>
            )}
          </div>
        )}

        {/* 收起态：图标导航 — moved to bottom */}
        {collapsed && (
          <div style={{ padding: '8px 4px 4px', display: 'flex', flexDirection: 'column', gap: 4, borderTop: '1px solid var(--border-subtle)' }}>
            {NAV_ITEMS.map(item => (
              <NavLink
                key={item.path}
                to={item.path}
                end={item.path === '/'}
                title={item.label}
                style={collapsedIconStyle(isActive(item.path))}
              >
                {item.icon}
              </NavLink>
            ))}
          </div>
        )}

        {/* Bottom buttons */}
        <div style={{ padding: collapsed ? '0 4px' : '0 10px', marginBottom: 2 }}>
          {/* Toggle collapse */}
          <button
            onClick={() => setCollapsed(!collapsed)}
            style={menuIconBtnStyle(false)}
            title={collapsed ? '展开侧边栏' : '收起侧边栏'}
          >
            {collapsed ? '▶' : '◀'}
          </button>
        </div>

        {/* Footer */}
        {!collapsed && (
          <div style={footerStyle}>
            <div style={{ display: 'flex', gap: 6 }}>
              <div style={{ flex: 1, height: 3, borderRadius: 2, opacity: 0.6, background: 'var(--gold-500)' }} />
              <div style={{ flex: 1, height: 3, borderRadius: 2, opacity: 0.6, background: 'var(--blue-400)' }} />
              <div style={{ flex: 1, height: 3, borderRadius: 2, opacity: 0.6, background: 'var(--purple-400)' }} />
              <div style={{ flex: 1, height: 3, borderRadius: 2, opacity: 0.6, background: 'var(--green-400)' }} />
            </div>
          </div>
        )}
      </aside>

      {/* New Session Modal */}
      {showNewSession && (
        <NewSessionModal
          teams={teams}
          onClose={() => setShowNewSession(false)}
          onCreated={(sessionId, teamId) => {
            setShowNewSession(false);
            navigate(`/chat?session=${sessionId}&team=${teamId}`);
          }}
        />
      )}

      {/* Delete Confirmation Modal */}
      {deleteConfirm && (
        <>
          <div onClick={() => setDeleteConfirm(null)} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 200 }} />
          <div style={deleteModalStyle}>
            <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>确认删除会话？</div>
            <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 20 }}>
              将删除「{deleteConfirm.title}」及其所有对话记录。此操作不可恢复。
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
              <button onClick={() => setDeleteConfirm(null)} style={cancelBtnStyle}>取消</button>
              <button onClick={confirmDelete} style={confirmBtnStyle}>确认删除</button>
            </div>
          </div>
        </>
      )}
    </>
  );
}

// ── Sub-components ──

function renderSessionItem(
  s: SessionInfo, navigate: (p: string) => void,
  onDelete: (id: string, title: string) => void,
  hovered: string | null, setHovered: (id: string | null) => void,
) {
  const isActive = location.pathname === `/chat` && new URLSearchParams(location.search).get('session') === s.id;
  const isHovered = hovered === s.id;
  return (
    <div
      key={s.id}
      onClick={() => navigate(`/chat?session=${s.id}&team=${s.team_id}`)}
      onMouseEnter={() => setHovered(s.id)}
      onMouseLeave={() => setHovered(null)}
      style={sessionItemStyle(isActive)}
    >
      <span style={{ fontSize: 13, flexShrink: 0 }}>💬</span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontSize: 12.5, fontWeight: 500, color: isActive ? 'var(--gold-400)' : 'var(--text-primary)',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {s.title}
        </div>
        <div style={{ fontSize: 10, color: 'var(--text-dim)', marginTop: 1 }}>
          {s.team_name || '未分组'} · {formatRelativeTime(s.updated_at)}
          {(s.task_total || 0) > 0 && <span> · {s.task_completed || 0}/{s.task_total}</span>}
        </div>
        {(s.task_total || 0) > 0 && (
          <div style={{ marginTop: 3, height: 2, borderRadius: 1, background: 'var(--border-subtle)', overflow: 'hidden' }}>
            <div style={{ width: `${((s.task_completed||0)/(s.task_total||1))*100}%`, height: '100%', borderRadius: 1, background: 'var(--green-400)', transition: 'width 0.3s' }} />
          </div>
        )}
      </div>
      {isHovered && (
        <button
          onClick={(e) => { e.stopPropagation(); onDelete(s.id, s.title); }}
          title="删除"
          style={deleteBtnStyle}
        >✕</button>
      )}
    </div>
  );
}

function formatRelativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return '刚刚';
  if (mins < 60) return `${mins}分钟前`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}小时前`;
  return `${Math.floor(hours / 24)}天前`;
}

// ── Styles ──

const asideStyle = (collapsed: boolean): React.CSSProperties => ({
  width: collapsed ? 48 : 'var(--sidebar-width)', flexShrink: 0, background: 'var(--bg-base)',
  borderRight: '1px solid var(--border-subtle)', display: 'flex', flexDirection: 'column',
  position: 'relative', zIndex: 10, transition: 'width 0.2s ease',
});

const logoSectionStyle = (collapsed: boolean): React.CSSProperties => ({
  padding: collapsed ? '12px 4px' : '20px 20px 8px', borderBottom: '1px solid var(--border-subtle)',
});

const logoIconStyle: React.CSSProperties = {
  width: 34, height: 34, background: 'linear-gradient(135deg, var(--gold-500), #d97706)',
  borderRadius: 9, display: 'flex', alignItems: 'center', justifyContent: 'center',
  fontWeight: 800, fontSize: 15, color: '#0a0f1e',
  boxShadow: '0 0 20px rgba(245,158,11,0.15)',
};

const newChatBtnStyle = (collapsed: boolean): React.CSSProperties => ({
  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: collapsed ? 0 : 6,
  width: '100%', padding: collapsed ? '8px 0' : '10px 0', borderRadius: 10,
  fontFamily: 'var(--font-body)', fontSize: 13, fontWeight: 500,
  cursor: 'pointer', border: 'none',
  background: 'linear-gradient(135deg, var(--gold-500), #d97706)',
  color: '#0a0f1e', boxShadow: '0 0 16px rgba(245,158,11,0.12)',
});

const historyContainerStyle: React.CSSProperties = {
  padding: '0 4px', flex: 1, overflowY: 'auto', minHeight: 0,
  borderTop: '1px solid var(--border-subtle)',
};

const navItemStyle = (active: boolean): React.CSSProperties => ({
  display: 'flex', alignItems: 'center', gap: 8, padding: '7px 10px',
  borderRadius: 6, textDecoration: 'none',
  color: active ? 'var(--gold-400)' : 'var(--text-secondary)',
  background: active ? 'var(--gold-bg)' : 'transparent',
  borderLeft: `2px solid ${active ? 'var(--gold-500)' : 'transparent'}`,
  marginBottom: 2,
  transition: 'all 0.15s',
});

const collapsedIconStyle = (active: boolean): React.CSSProperties => ({
  width: 32, height: 32, borderRadius: 6,
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  fontSize: 14, textDecoration: 'none',
  color: active ? 'var(--gold-400)' : 'var(--text-dim)',
  background: active ? 'var(--gold-bg)' : 'transparent',
  border: `1px solid ${active ? 'var(--gold-border)' : 'var(--border-subtle)'}`,
});

const emptyHistoryStyle: React.CSSProperties = {
  padding: '12px', fontSize: 11, color: 'var(--text-dim)',
  textAlign: 'center', fontStyle: 'italic',
};

const groupStyle: React.CSSProperties = { marginBottom: 4 };

const groupLabelStyle: React.CSSProperties = {
  fontSize: 10, color: 'var(--text-dim)', padding: '6px 12px 2px',
  fontWeight: 600,
};

const sessionItemStyle = (active: boolean): React.CSSProperties => ({
  display: 'flex', alignItems: 'center', gap: 8, padding: '7px 8px',
  borderRadius: 6, cursor: 'pointer', transition: 'all 0.1s',
  background: active ? 'var(--gold-bg)' : 'transparent',
});

const deleteBtnStyle: React.CSSProperties = {
  background: 'none', border: 'none', color: 'var(--text-dim)',
  cursor: 'pointer', fontSize: 11, padding: '2px 4px',
  opacity: 0, transition: 'opacity 0.15s',
};

const footerStyle: React.CSSProperties = { padding: '14px 16px' };

const menuIconBtnStyle = (open: boolean): React.CSSProperties => ({
  width: 34, height: 34, borderRadius: 8,
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  fontSize: 16, cursor: 'pointer', border: '1px solid var(--border-subtle)',
  background: open ? 'var(--gold-bg)' : 'transparent',
  color: open ? 'var(--gold-400)' : 'var(--text-dim)',
  transition: 'all 0.2s', flexShrink: 0,
});

// ── Modal Styles ──

const deleteModalStyle: React.CSSProperties = {
  position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%, -50%)',
  zIndex: 201, background: 'var(--bg-base)', border: '1px solid var(--border-subtle)',
  borderRadius: 12, padding: '20px 24px', minWidth: 320,
  boxShadow: '0 24px 80px rgba(0,0,0,0.5)',
};

const cancelBtnStyle: React.CSSProperties = {
  padding: '8px 16px', borderRadius: 8, background: 'var(--bg-card)',
  border: '1px solid var(--border-medium)', color: 'var(--text-secondary)',
  fontSize: 13, cursor: 'pointer',
};

const confirmBtnStyle: React.CSSProperties = {
  padding: '8px 16px', borderRadius: 8, background: 'var(--red-500)',
  border: 'none', color: 'white', fontSize: 13, fontWeight: 500, cursor: 'pointer',
};

function ThemeMenuItem() {
  const { theme, toggle } = useTheme();
  return (
    <div
      onClick={toggle}
      title={theme === 'dark' ? '切换浅色主题' : '切换深色主题'}
      style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '6px 10px', borderRadius: 6, cursor: 'pointer',
        fontSize: 12, fontWeight: 500, color: 'var(--text-secondary)',
        transition: 'all 0.15s',
      }}
      onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-card)'; e.currentTarget.style.color = 'var(--text-primary)'; }}
      onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--text-secondary)'; }}
    >
      <span style={{ fontSize: 14, width: 22, textAlign: 'center' }}>{theme === 'dark' ? '☀️' : '🌙'}</span>
      <span style={{ fontSize: 12, fontWeight: 500 }}>{theme === 'dark' ? '浅色模式' : '深色模式'}</span>
    </div>
  );
}

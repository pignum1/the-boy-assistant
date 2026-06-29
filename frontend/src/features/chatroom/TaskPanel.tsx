/** 会话任务面板 */
import { useState, useEffect } from 'react';

interface Task {
  id: string; title: string; description?: string; status: string;
  priority: string; assigned_agent_name?: string; depends_on?: string[];
}

const API = (import.meta as any).env?.VITE_API_URL || '';

export function TaskPanel({ sessionId }: { sessionId: string }) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [newTitle, setNewTitle] = useState('');
  const [adding, setAdding] = useState(false);

  const loadTasks = async () => {
    try {
      const res = await fetch(`${API}/api/v1/sessions/${sessionId}/tasks`);
      if (res.ok) { const data = await res.json(); setTasks(data.tasks || []); }
    } catch { /* ignore */ }
  };

  useEffect(() => { loadTasks(); }, [sessionId]);

  const addTask = async () => {
    if (!newTitle.trim()) return;
    setAdding(true);
    try {
      await fetch(`${API}/api/v1/sessions/${sessionId}/tasks`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: newTitle.trim() }),
      });
      setNewTitle(''); loadTasks();
    } catch { /* ignore */ } finally { setAdding(false); }
  };

  const updateStatus = async (id: string, status: string) => {
    await fetch(`${API}/api/v1/sessions/${sessionId}/tasks/${id}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    });
    loadTasks();
  };

  const deleteTask = async (id: string) => {
    await fetch(`${API}/api/v1/sessions/${sessionId}/tasks/${id}`, { method: 'DELETE' });
    loadTasks();
  };

  const stats = { total: tasks.length, done: tasks.filter(t => t.status === 'done').length, inProgress: tasks.filter(t => t.status === 'in_progress').length };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ padding: '8px 10px', borderBottom: '1px solid var(--border-subtle)' }}>
        <div style={{ fontSize: 12, fontWeight: 600 }}>📋 任务</div>
        {tasks.length > 0 && <div style={{ fontSize: 10, color: 'var(--text-dim)', marginTop: 2 }}>{stats.done}/{stats.total} 完成</div>}
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: 4 }}>
        {tasks.map(t => (
          <div key={t.id} style={taskItemStyle(t.status)}>
            <input type="checkbox" checked={t.status === 'done'} onChange={() => updateStatus(t.id, t.status === 'done' ? 'pending' : 'done')} style={{ cursor: 'pointer', flexShrink: 0 }} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 11.5, fontWeight: 500, color: t.status === 'done' ? 'var(--text-dim)' : 'var(--text-primary)', textDecoration: t.status === 'done' ? 'line-through' : 'none' }}>
                {t.title}
              </div>
              {t.assigned_agent_name && <div style={{ fontSize: 9, color: 'var(--text-dim)' }}>{t.assigned_agent_name}</div>}
            </div>
            <button onClick={() => deleteTask(t.id)} style={delBtnStyle}>✕</button>
          </div>
        ))}
        {tasks.length === 0 && <div style={{ textAlign: 'center', padding: 16, color: 'var(--text-dim)', fontSize: 11 }}>暂无任务</div>}
      </div>
      <div style={{ padding: '6px 8px', borderTop: '1px solid var(--border-subtle)', display: 'flex', gap: 4 }}>
        <input value={newTitle} onChange={e => setNewTitle(e.target.value)} onKeyDown={e => e.key === 'Enter' && addTask()} placeholder="添加任务..." style={inputStyle} />
        <button onClick={addTask} disabled={adding || !newTitle.trim()} style={addBtnStyle}>+</button>
      </div>
    </div>
  );
}

const taskItemStyle = (status: string): React.CSSProperties => ({
  display: 'flex', alignItems: 'center', gap: 6, padding: '5px 8px',
  borderRadius: 4, opacity: status === 'done' ? 0.6 : 1,
});
const delBtnStyle: React.CSSProperties = { background: 'none', border: 'none', color: 'var(--text-dim)', cursor: 'pointer', fontSize: 10, opacity: 0.3 };
const inputStyle: React.CSSProperties = { flex: 1, padding: '4px 8px', borderRadius: 4, background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)', color: 'var(--text-primary)', fontSize: 11, outline: 'none' };
const addBtnStyle: React.CSSProperties = { padding: '4px 10px', borderRadius: 4, background: 'var(--gold-500)', border: 'none', color: '#0a0f1e', cursor: 'pointer', fontSize: 13, fontWeight: 600 };

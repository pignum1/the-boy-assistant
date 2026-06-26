import { useState, useEffect, useCallback, useMemo } from 'react';
import { api } from '../../shared/api/client';
import { Pagination } from './shared/Pagination';
import {
  btnPrimaryStyle,
  btnSecondaryStyle,
  cardStyle,
  cardHeaderStyle,
  iconStyle,
  cardNameStyle,
  cardDescStyle,
  cardFooterStyle,
  cardMetaStyle,
  actionBtnStyle,
  statusBadgeStyle,
  searchInputStyle,
  overlayStyle,
  panelStyle,
  panelHeaderStyle,
  panelFooterStyle,
  closeBtnStyle,
  formLabelStyle,
  formInputStyle,
} from './shared/styles';

// ── Types ──

interface AgentResource {
  id: string;
  name: string;
  persona_id?: string;
  default_model_id?: string;
  tools?: string[];
  status?: string;
  team_name?: string;
  current_task?: string;
}

interface SelectOption {
  value: string;
  label: string;
}

interface PersonaResource {
  id: string;
  name: string;
  mcp_server_ids?: string[];
  skill_ids?: string[];
}

interface ModelResource {
  id: string;
  name: string;
  provider: string;
}

// ── Status Config ──

const STATUS_STYLE: Record<string, { bg: string; color: string }> = {
  online: { bg: 'var(--green-bg)', color: 'var(--green-400)' },
  busy: { bg: 'var(--gold-bg)', color: 'var(--gold-400)' },
  idle: { bg: 'rgba(148,163,184,0.06)', color: 'var(--text-muted)' },
  offline: { bg: 'rgba(148,163,184,0.04)', color: 'var(--text-dim)' },
};

const STATUS_LABEL: Record<string, string> = {
  online: '在线', busy: '使用中', idle: '空闲', offline: '离线',
};

// ── Chip helpers ──

function chipStyle(color: string): React.CSSProperties {
  const colors: Record<string, { bg: string; color: string; border: string }> = {
    purple: { bg: 'var(--purple-bg)', color: 'var(--purple-400)', border: 'var(--purple-border)' },
    gold: { bg: 'var(--gold-bg)', color: 'var(--gold-400)', border: 'var(--gold-border)' },
    green: { bg: 'var(--green-bg)', color: 'var(--green-400)', border: 'var(--green-border)' },
    blue: { bg: 'var(--blue-bg)', color: 'var(--blue-400)', border: 'var(--blue-border)' },
  };
  const c = colors[color] || colors.green;
  return {
    fontSize: 10, padding: '2px 7px', borderRadius: 4, fontWeight: 500,
    background: c.bg, color: c.color, border: `1px solid ${c.border}`,
    whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 140,
  };
}

// ── Local styles ──

const gridStyle: React.CSSProperties = {
  display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))', gap: 14,
};

const dashedCardStyle: React.CSSProperties = {
  border: '1px dashed var(--border-medium)', borderRadius: 12,
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  cursor: 'pointer', transition: 'all 0.15s',
};

const infoRowStyle: React.CSSProperties = {
  display: 'flex', alignItems: 'flex-start', gap: 6, marginBottom: 4,
};

const infoLabelStyle: React.CSSProperties = {
  fontSize: 10, color: 'var(--text-dim)', whiteSpace: 'nowrap', width: 36, paddingTop: 2, fontWeight: 600,
};

const tagsWrapStyle: React.CSSProperties = {
  display: 'flex', gap: 4, flexWrap: 'wrap',
};

// ── Main Component ──

export function AgentsPage() {
  const [searchQuery, setSearchQuery] = useState('');

  // Data
  const [agents, setAgents] = useState<AgentResource[]>([]);
  const [personas, setPersonas] = useState<PersonaResource[]>([]);
  const [models, setModels] = useState<ModelResource[]>([]);
  const [allTools, setAllTools] = useState<SelectOption[]>([]);
  const [mcpServers, setMcpServers] = useState<SelectOption[]>([]);
  const [skills, setSkills] = useState<SelectOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const [pageSize] = useState(20);
  const [total, setTotal] = useState(0);

  // Panel
  const [panelOpen, setPanelOpen] = useState(false);
  const [editingAgent, setEditingAgent] = useState<AgentResource | null>(null);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [agentsRes, personasRes, modelsRes, toolsRes, mcpRes, skillsRes] = await Promise.allSettled([
        api.get<{items: AgentResource[], total: number}>(`/api/v1/agents?skip=${page * pageSize}&limit=${pageSize}`),
        api.get<{items: any[], total: number}>('/api/v1/personas?limit=200'),
        api.get<{items: any[], total: number}>('/api/v1/models?limit=200'),
        api.get<any[]>('/api/v1/tools'),
        api.get<{items: any[], total: number}>('/api/v1/mcp-servers?limit=200'),
        api.get<{items: any[], total: number}>('/api/v1/skills?limit=200'),
      ]);
      if (agentsRes.status === 'fulfilled') {
        setAgents(agentsRes.value.items);
        setTotal(agentsRes.value.total || 0);
      } else setError('加载Agent列表失败');
      if (personasRes.status === 'fulfilled') {
        const data = personasRes.value as any;
        setPersonas((data.items || data).map((p: any) => ({
          id: p.id, name: p.name,
          mcp_server_ids: p.mcp_server_ids || [],
          skill_ids: p.skill_ids || [],
        })));
      }
      if (modelsRes.status === 'fulfilled') {
        const data = modelsRes.value as any;
        setModels((data.items || data).map((m: any) => ({
          id: m.id, name: m.name, provider: m.provider,
        })));
      }
      if (toolsRes.status === 'fulfilled') {
        const data = toolsRes.value as any;
        setAllTools((Array.isArray(data) ? data : data.items || []).map((t: any) => ({ value: t.id, label: t.name })));
      }
      if (mcpRes.status === 'fulfilled') {
        const data = mcpRes.value as any;
        setMcpServers((data.items || data).map((s: any) => ({ value: s.id, label: s.name })));
      }
      if (skillsRes.status === 'fulfilled') {
        const data = skillsRes.value as any;
        setSkills((data.items || data).map((s: any) => ({ value: s.id, label: s.name })));
      }
    } catch (e) {
      setError('加载失败: ' + String(e));
    }
    setLoading(false);
  }, [page, pageSize]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const filteredAgents = useMemo(() => {
    if (!searchQuery) return agents;
    const q = searchQuery.toLowerCase();
    return agents.filter((a) => {
      const pName = personas.find((p) => p.id === a.persona_id)?.name || '';
      const mName = models.find((m) => m.id === a.default_model_id)?.name || '';
      return a.name.toLowerCase().includes(q) || pName.toLowerCase().includes(q) || mName.toLowerCase().includes(q);
    });
  }, [agents, personas, models, searchQuery]);

  if (loading) {
    return (
      <div style={{ padding: '40px 32px', position: 'relative', zIndex: 1 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, letterSpacing: -0.5 }}>Agent 管理</h1>
        <p style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 8 }}>加载中...</p>
      </div>
    );
  }

  if (error && agents.length === 0) {
    return (
      <div style={{ padding: '40px 32px', position: 'relative', zIndex: 1 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, letterSpacing: -0.5 }}>Agent 管理</h1>
        <div style={{ textAlign: 'center', padding: 60 }}>
          <div style={{ fontSize: 48, marginBottom: 16, opacity: 0.6 }}>⚠️</div>
          <div style={{ fontSize: 15, color: 'var(--text-secondary)', marginBottom: 16 }}>{error}</div>
          <button style={btnPrimaryStyle} onClick={fetchAll}>重试</button>
        </div>
      </div>
    );
  }

  const lookup = { personas, models, skills, mcpServers, allTools };

  return (
    <div style={{ padding: '28px 32px', maxWidth: 1400, position: 'relative', zIndex: 1 }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 700, letterSpacing: -0.5 }}>Agent 管理</h1>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>创建和管理 AI Agent 实例 · 工具从 Persona 自动继承</div>
        </div>
        <button style={btnPrimaryStyle} onClick={() => { setEditingAgent(null); setPanelOpen(true); }}>
          + 注册 Agent
        </button>
      </div>

      {/* Search */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 20, alignItems: 'center' }}>
        <input style={searchInputStyle} placeholder="搜索 Agent 名称 / Persona / Model..." value={searchQuery} onChange={(e) => { setSearchQuery(e.target.value); setPage(0); }} />
      </div>

      {/* Card Grid */}
      {filteredAgents.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 60, color: 'var(--text-dim)' }}>
          <div style={{ fontSize: 48, marginBottom: 16, opacity: 0.4 }}>🤖</div>
          <div style={{ fontSize: 15, marginBottom: 8 }}>暂无 Agent</div>
          <div style={{ fontSize: 13 }}>点击「+ 注册 Agent」创建第一个 Agent 实例</div>
        </div>
      ) : (
        <div style={gridStyle}>
          {filteredAgents.map((a) => (
            <AgentCard key={a.id} data={a} lookup={lookup} onClick={() => { setEditingAgent(a); setPanelOpen(true); }} />
          ))}
          <div style={{ ...dashedCardStyle, minHeight: 220 }} onClick={() => { setEditingAgent(null); setPanelOpen(true); }}>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 24, marginBottom: 6, opacity: 0.3 }}>+</div>
              <div style={{ fontSize: 13, color: 'var(--text-dim)' }}>注册 Agent</div>
              <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 4 }}>绑定 Persona + 选择模型</div>
            </div>
          </div>
        </div>
      )}

      <Pagination skip={page * pageSize} limit={pageSize} total={total} onPageChange={(skip) => setPage(Math.floor(skip / pageSize))} />

      {/* Panel */}
      {panelOpen && (
        <AgentPanel
          agent={editingAgent}
          personas={personas}
          models={models}
          mcpServers={mcpServers}
          skills={skills}
          allTools={allTools}
          onClose={() => { setPanelOpen(false); setEditingAgent(null); }}
          onRefresh={fetchAll}
        />
      )}
    </div>
  );
}

// ── AgentCard ──

function AgentCard({ data, lookup, onClick }: {
  data: AgentResource;
  lookup: { personas: PersonaResource[]; models: ModelResource[]; skills: SelectOption[]; mcpServers: SelectOption[]; allTools: SelectOption[] };
  onClick: () => void;
}) {
  const st = STATUS_STYLE[data.status || 'idle'] || STATUS_STYLE.idle;
  const label = STATUS_LABEL[data.status || 'idle'] || '空闲';

  // Resolve from lookup data
  const persona = lookup.personas.find((p) => p.id === data.persona_id);
  const model = lookup.models.find((m) => m.id === data.default_model_id);

  const skillNames = (persona?.skill_ids || []).map((sid) => lookup.skills.find((s) => s.value === sid)?.label).filter(Boolean) as string[];
  const mcpNames = (persona?.mcp_server_ids || []).map((sid) => lookup.mcpServers.find((s) => s.value === sid)?.label).filter(Boolean) as string[];

  // Tools from persona's MCP servers (matched by server_id)
  const toolNames = (data.tools || []).map((tid) => lookup.allTools.find((t) => t.value === tid)?.label).filter(Boolean) as string[];

  return (
    <div style={cardStyle} onClick={onClick}>
      <div style={cardHeaderStyle}>
        <div style={{ ...iconStyle, background: 'var(--gold-bg)', border: '1px solid var(--gold-border)' }}>🤖</div>
        <span style={{ ...statusBadgeStyle, ...st }}>{label}</span>
      </div>
      <div style={cardNameStyle}>{data.name}</div>
      <div style={cardDescStyle}>{persona?.name || '—'} · {model ? `${model.name} (${model.provider})` : '—'}</div>

      {/* Persona info row */}
      {persona && (
        <div style={{ marginTop: 10, padding: '8px 10px', background: 'rgba(255,255,255,0.02)', borderRadius: 6, border: '1px solid var(--border-subtle)' }}>
          {skillNames.length > 0 && (
            <div style={infoRowStyle}>
              <span style={infoLabelStyle}>Skills</span>
              <div style={tagsWrapStyle}>
                {skillNames.slice(0, 4).map((s) => <span key={s} style={chipStyle('blue')}>{s}</span>)}
                {skillNames.length > 4 && <span style={chipStyle('blue')}>+{skillNames.length - 4}</span>}
              </div>
            </div>
          )}
          {mcpNames.length > 0 && (
            <div style={infoRowStyle}>
              <span style={infoLabelStyle}>MCP</span>
              <div style={tagsWrapStyle}>
                {mcpNames.map((s) => <span key={s} style={chipStyle('purple')}>{s}</span>)}
              </div>
            </div>
          )}
          {toolNames.length > 0 && (
            <div style={infoRowStyle}>
              <span style={infoLabelStyle}>Tools</span>
              <div style={tagsWrapStyle}>
                {toolNames.slice(0, 3).map((t) => <span key={t} style={chipStyle('green')}>{t}</span>)}
                {toolNames.length > 3 && <span style={chipStyle('green')}>+{toolNames.length - 3}</span>}
              </div>
            </div>
          )}
          {skillNames.length === 0 && mcpNames.length === 0 && toolNames.length === 0 && (
            <div style={{ fontSize: 10, color: 'var(--text-dim)' }}>Persona 暂无关联资源</div>
          )}
        </div>
      )}

      <div style={cardFooterStyle}>
        <div style={cardMetaStyle}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11 }}>{data.current_task ? `任务: ${data.current_task}` : '空闲'}</span>
        </div>
        <div style={{ display: 'flex', gap: 4 }}><div style={actionBtnStyle}>⚙</div></div>
      </div>
    </div>
  );
}

// ── AgentPanel ──

function AgentPanel({
  agent, personas, models, mcpServers, skills, allTools, onClose, onRefresh,
}: {
  agent: AgentResource | null;
  personas: PersonaResource[];
  models: ModelResource[];
  mcpServers: SelectOption[];
  skills: SelectOption[];
  allTools: SelectOption[];
  onClose: () => void;
  onRefresh: () => void;
}) {
  const isNew = !agent;
  const [name, setName] = useState(agent?.name || '');
  const [personaId, setPersonaId] = useState(agent?.persona_id || '');
  const [defaultModelId, setDefaultModelId] = useState(agent?.default_model_id || '');
  const [selectedProvider, setSelectedProvider] = useState('');
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' | 'info' } | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<{ agentId: string; agentName: string } | null>(null);
  const [deleting, setDeleting] = useState(false);

  const showToast = (message: string, type: 'success' | 'error' | 'info' = 'info') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  };

  // ── Derived ──

  const providers = useMemo(() => [...new Set(models.map((m) => m.provider))].sort(), [models]);
  const filteredModels = useMemo(() => selectedProvider ? models.filter((m) => m.provider === selectedProvider) : [], [models, selectedProvider]);

  useEffect(() => {
    if (agent && defaultModelId && !selectedProvider) {
      const m = models.find((x) => x.id === defaultModelId);
      if (m) setSelectedProvider(m.provider);
    }
  }, [agent, defaultModelId, models, selectedProvider]);

  const handleProviderChange = (prov: string) => { setSelectedProvider(prov); setDefaultModelId(''); };

  const selectedPersona = useMemo(() => personas.find((p) => p.id === personaId), [personas, personaId]);

  const personaMcpNames = useMemo(() =>
    (selectedPersona?.mcp_server_ids || []).map((sid) => mcpServers.find((s) => s.value === sid)?.label).filter(Boolean) as string[],
    [selectedPersona, mcpServers]);

  const personaSkillNames = useMemo(() =>
    (selectedPersona?.skill_ids || []).map((sid) => skills.find((s) => s.value === sid)?.label).filter(Boolean) as string[],
    [selectedPersona, skills]);

  // Tools from persona's MCP servers
  const personaToolNames = useMemo(() =>
    (agent?.tools || []).map((tid) => allTools.find((t) => t.value === tid)?.label).filter(Boolean) as string[],
    [agent, allTools]);

  // ── Actions ──

  const handleSave = async () => {
    if (!name.trim()) { showToast('请输入 Agent 名称', 'error'); return; }
    if (!personaId) { showToast('请选择 Persona', 'error'); return; }
    if (!defaultModelId) { showToast('请选择模型', 'error'); return; }
    setSaving(true);
    try {
      const body = {
        name: name.trim(),
        persona_id: personaId,
        model_id: defaultModelId,
      };
      if (isNew) {
        await api.post('/api/v1/agents', body);
        showToast('Agent 创建成功', 'success');
      } else if (agent) {
        await api.put(`/api/v1/agents/${agent.id}`, body);
        showToast('Agent 更新成功', 'success');
      }
      onRefresh();
      onClose();
    } catch (e: any) {
      showToast('保存失败: ' + (e?.message || String(e)), 'error');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!confirmDelete) return;
    setDeleting(true);
    try {
      await api.del(`/api/v1/agents/${confirmDelete.agentId}`);
      setConfirmDelete(null); onRefresh(); onClose();
      showToast('Agent 已删除', 'success');
    } catch (e: any) {
      setConfirmDelete(null);
      showToast('删除失败: ' + (e?.message || String(e)), 'error');
    } finally {
      setDeleting(false);
    }
  };

  const headerPersona = personas.find((p) => p.id === (agent?.persona_id || personaId));
  const headerModel = models.find((m) => m.id === (agent?.default_model_id || defaultModelId));

  return (
    <>
      <div onClick={onClose} style={overlayStyle} />
      <div style={{ ...panelStyle, right: 0 }}>

        {/* Confirm Delete */}
        {confirmDelete && (
          <>
            <div onClick={() => setConfirmDelete(null)} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 200, backdropFilter: 'blur(4px)' }} />
            <div style={{ position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%,-50%)', zIndex: 201, width: 380, background: 'var(--bg-base)', borderRadius: 16, border: '1px solid var(--border-subtle)', padding: 28, boxShadow: '0 24px 48px rgba(0,0,0,0.5)', textAlign: 'center' }}>
              <div style={{ fontSize: 40, marginBottom: 12 }}>⚠️</div>
              <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 6 }}>确认删除</div>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6, marginBottom: 24 }}>确定要删除 Agent「{confirmDelete.agentName}」吗？此操作不可撤销。</div>
              <div style={{ display: 'flex', gap: 10, justifyContent: 'center' }}>
                <button onClick={() => setConfirmDelete(null)} style={{ padding: '8px 24px', borderRadius: 8, border: '1px solid var(--border-medium)', background: 'var(--bg-card)', color: 'var(--text-secondary)', cursor: 'pointer', fontSize: 13 }}>取消</button>
                <button disabled={deleting} onClick={handleDelete} style={{ padding: '8px 24px', borderRadius: 8, border: 'none', background: 'var(--red-400)', color: '#fff', cursor: 'pointer', fontSize: 13, fontWeight: 600 }}>{deleting ? '删除中...' : '确认删除'}</button>
              </div>
            </div>
          </>
        )}

        {/* Header */}
        <div style={panelHeaderStyle}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{ width: 44, height: 44, borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20, background: 'var(--gold-bg)', border: '1px solid var(--gold-border)' }}>🤖</div>
            <div>
              <div style={{ fontSize: 18, fontWeight: 700 }}>{isNew ? '注册 Agent' : name}</div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 3 }}>
                {isNew ? '绑定 Persona + 选择模型' : `${headerPersona?.name || '—'} · ${headerModel?.name || '—'}`}
              </div>
            </div>
          </div>
          <button onClick={onClose} style={closeBtnStyle}>✕</button>
        </div>

        {/* Formula bar */}
        <div style={{ padding: '12px 24px', borderBottom: '1px solid var(--border-subtle)', background: 'var(--bg-card)', fontSize: 11 }}>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <span style={chipStyle('purple')}>🎭 Persona (自带 Skills + MCP)</span>
            <span style={{ color: 'var(--text-dim)' }}>+</span>
            <span style={chipStyle('gold')}>🧠 Model</span>
            <span style={{ color: 'var(--text-dim)' }}>=</span>
            <span style={{ ...chipStyle('green'), fontWeight: 600 }}>🤖 Agent</span>
          </div>
        </div>

        {/* Body */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px' }}>
          {/* Name */}
          <div style={{ marginBottom: 16 }}>
            <label style={formLabelStyle}>Agent 名称</label>
            <input style={formInputStyle} value={name} onChange={(e) => setName(e.target.value)} placeholder="输入 Agent 名称" />
          </div>

          {/* Persona select */}
          <div style={{ marginBottom: 16 }}>
            <label style={formLabelStyle}>绑定 Persona</label>
            <select value={personaId} onChange={(e) => setPersonaId(e.target.value)} style={{ ...formInputStyle, cursor: 'pointer' }}>
              <option value="">— 选择 Persona —</option>
              {personas.map((p) => (
                <option key={p.id} value={p.id}>{p.name} ({(p.skill_ids || []).length} skills, {(p.mcp_server_ids || []).length} MCP)</option>
              ))}
            </select>
          </div>

          {/* Persona inherited resources */}
          {selectedPersona && (
            <div style={{ marginBottom: 16, padding: 12, background: 'var(--bg-card)', borderRadius: 8, border: '1px solid var(--border-subtle)' }}>
              <div style={{ fontSize: 11, color: 'var(--text-dim)', marginBottom: 8, fontWeight: 600 }}>Persona 携带资源（自动继承，无需手动配置）</div>
              {personaSkillNames.length > 0 && (
                <div style={infoRowStyle}>
                  <span style={infoLabelStyle}>Skills</span>
                  <div style={tagsWrapStyle}>
                    {personaSkillNames.map((s) => <span key={s} style={chipStyle('blue')}>{s}</span>)}
                  </div>
                </div>
              )}
              {personaMcpNames.length > 0 && (
                <div style={infoRowStyle}>
                  <span style={infoLabelStyle}>MCP</span>
                  <div style={tagsWrapStyle}>
                    {personaMcpNames.map((s) => <span key={s} style={chipStyle('purple')}>{s}</span>)}
                  </div>
                </div>
              )}
              {!isNew && personaToolNames.length > 0 && (
                <div style={infoRowStyle}>
                  <span style={infoLabelStyle}>Tools</span>
                  <div style={tagsWrapStyle}>
                    {personaToolNames.map((t) => <span key={t} style={chipStyle('green')}>{t}</span>)}
                  </div>
                </div>
              )}
              {personaSkillNames.length === 0 && personaMcpNames.length === 0 && (
                <div style={{ fontSize: 10, color: 'var(--text-dim)' }}>该 Persona 暂无关联资源</div>
              )}
            </div>
          )}

          {/* Model: Provider → Model */}
          <div style={{ marginBottom: 8 }}>
            <label style={formLabelStyle}>默认模型</label>
            <div style={{ display: 'flex', gap: 8 }}>
              <select value={selectedProvider} onChange={(e) => handleProviderChange(e.target.value)} style={{ ...formInputStyle, cursor: 'pointer', flex: 1 }}>
                <option value="">— 选择供应商 —</option>
                {providers.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
              <select value={defaultModelId} onChange={(e) => setDefaultModelId(e.target.value)} style={{ ...formInputStyle, cursor: 'pointer', flex: 1 }} disabled={!selectedProvider}>
                <option value="">— 选择模型 —</option>
                {filteredModels.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
              </select>
            </div>
          </div>
          <div style={{ fontSize: 10, color: 'var(--text-dim)', marginBottom: 16 }}>
            先选供应商，再选模型。运行时可在 SOP 节点中按复杂度动态路由
          </div>

          {/* Info hint */}
          <div style={{ background: 'var(--blue-bg)', border: '1px solid var(--blue-border)', borderRadius: 8, padding: '10px 14px', fontSize: 11, color: 'var(--blue-400)' }}>
            工具自动继承：绑定 Persona 后，Agent 自动获得该 Persona 关联的 MCP 服务器工具和技能，无需手动配置
          </div>
        </div>

        {/* Footer */}
        <div style={panelFooterStyle}>
          {!isNew && (
            <button style={{ ...btnSecondaryStyle, color: 'var(--red-400)', borderColor: 'var(--red-border)', marginRight: 'auto' }} onClick={() => agent && setConfirmDelete({ agentId: agent.id, agentName: agent.name })}>删除</button>
          )}
          <button style={btnSecondaryStyle} onClick={onClose}>取消</button>
          <button style={btnPrimaryStyle} onClick={handleSave} disabled={saving}>{saving ? '保存中...' : '保存'}</button>
        </div>
      </div>

      {/* Toast */}
      {toast && (
        <div style={{
          position: 'fixed', bottom: 32, left: '50%', transform: 'translateX(-50%)', zIndex: 300,
          padding: '10px 24px', borderRadius: 10,
          background: toast.type === 'success' ? 'var(--green-bg)' : toast.type === 'error' ? 'var(--red-bg)' : 'var(--blue-bg)',
          border: `1px solid ${toast.type === 'success' ? 'var(--green-border)' : toast.type === 'error' ? 'var(--red-border)' : 'var(--blue-border)'}`,
          color: toast.type === 'success' ? 'var(--green-400)' : toast.type === 'error' ? 'var(--red-400)' : 'var(--blue-400)',
          fontSize: 13, fontWeight: 500, boxShadow: '0 8px 24px rgba(0,0,0,0.3)',
        }}>
          <span style={{ marginRight: 8 }}>{toast.type === 'success' ? '✓' : toast.type === 'error' ? '✗' : 'ℹ'}</span>
          {toast.message}
        </div>
      )}
    </>
  );
}

import { Pagination } from './shared/Pagination';
import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { api } from '../../shared/api/client';
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
  tagsStyle,
  tagStyle,
  searchInputStyle,
} from './shared/styles';

// ── Types ──

interface PersonaResource {
  id: string; name: string;
  role?: string; expertise?: string; constraints?: string;
  system_prompt?: string; prompt_template?: string;
  output_format?: string; tags?: string[];
  skill_ids?: string[]; mcp_server_ids?: string[];
  output_prefs?: Record<string, string>;
  agent_count?: number;
}

interface SkillSummary {
  id: string; name: string; description?: string;
}

interface MCPServerSummary {
  id: string; name: string; transport: string; status: string;
}

const ICON_COLORS = ['gold', 'green', 'blue', 'purple'] as const;

const PRESET_TAG_OPTIONS = [
  // 产品经理
  '产品经理', 'PRD', '需求分析', '竞品分析', '指标定义', '验收', '升级处理',
  // 架构师
  '架构设计', '技术选型', '接口设计', '系统拆分', '非功能需求', 'ADR', '成本估算', '架构一致性',
  // UI/交互设计师
  'UI设计', '交互设计', '设计系统', '响应式', '组件设计', 'Design Token', '用户体验',
  // 后端工程师
  '后端开发', 'API实现', '数据库', '缓存', '消息队列', 'Debugging', '单元测试', '修复模式',
  // 前端工程师
  '前端开发', 'React', 'Vue', '组件开发', '状态管理', 'TypeScript',
  // 部署运维工程师
  'DevOps', 'SRE', 'CI/CD', 'Kubernetes', 'Docker', '部署', '灰度发布', '监控', '回滚', 'IaC',
  // 测试员
  'QA', '测试', 'Bug报告', '性能测试', '自动化测试', 'AC提取', '回归建议', '冒烟测试', '安全审计', 'OWASP',
  // 通用
  '文档编写', '团队协作',
];

// ── Local styles ──

const gridStyle: React.CSSProperties = {
  display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 14,
};

const dashedCardStyle: React.CSSProperties = {
  border: '1px dashed var(--border-medium)', borderRadius: 12,
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  cursor: 'pointer', transition: 'all 0.15s',
};

const formLabelStyle: React.CSSProperties = {
  display: 'block', fontSize: 11, fontWeight: 600,
  color: 'var(--text-dim)', marginBottom: 4,
};

const formInputStyle: React.CSSProperties = {
  width: '100%', padding: '8px 12px', borderRadius: 8,
  border: '1px solid var(--border-medium)',
  background: 'var(--bg-card)', color: 'var(--text-primary)',
  fontSize: 13, boxSizing: 'border-box', outline: 'none',
};

function hashName(name: string): number {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = ((hash << 5) - hash) + name.charCodeAt(i);
    hash |= 0;
  }
  return Math.abs(hash);
}

// ── Main Component ──

export function PersonasPage() {
  const [searchQuery, setSearchQuery] = useState('');
  const [personas, setPersonas] = useState<PersonaResource[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(20);
  const [total, setTotal] = useState(0);

  // Panel state
  const [panelOpen, setPanelOpen] = useState(false);
  const [editingPersona, setEditingPersona] = useState<PersonaResource | null>(null);

  const fetchPersonas = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.get<{ items: PersonaResource[]; total: number }>(
        '/api/v1/personas',
        { skip: page * pageSize, limit: pageSize }
      );
      setPersonas(Array.isArray(data) ? data : (data as any).items || []);
      if (!Array.isArray(data) && (data as any).total !== undefined) {
        setTotal((data as any).total);
      }
    } catch { /* keep current */ }
    setLoading(false);
  }, [page, pageSize]);

  useEffect(() => { fetchPersonas(); }, [fetchPersonas]);

  const openPanel = (persona: PersonaResource | null) => {
    setEditingPersona(persona);
    setPanelOpen(true);
  };

  const closePanel = () => {
    setPanelOpen(false);
    setEditingPersona(null);
  };

  const filteredPersonas = useMemo(() => {
    if (!searchQuery) return personas;
    const q = searchQuery.toLowerCase();
    return personas.filter((p) =>
      p.name.toLowerCase().includes(q) ||
      (p.role || '').toLowerCase().includes(q) ||
      (p.expertise || '').toLowerCase().includes(q) ||
      (p.tags || []).some((t) => t.toLowerCase().includes(q))
    );
  }, [personas, searchQuery]);

  if (loading) {
    return (
      <div style={{ padding: '40px 32px', position: 'relative', zIndex: 1 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, letterSpacing: -0.5 }}>Persona 管理</h1>
        <p style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 8 }}>加载中...</p>
      </div>
    );
  }

  return (
    <div style={{ padding: '28px 32px', maxWidth: 1400, position: 'relative', zIndex: 1 }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 700, letterSpacing: -0.5 }}>Persona 管理</h1>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>定义 AI 角色的人格、能力与行为约束</div>
        </div>
        <button style={btnPrimaryStyle} onClick={() => openPanel(null)}>
          + 创建 Persona
        </button>
      </div>

      {/* Search */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 20, alignItems: 'center' }}>
        <input
          style={searchInputStyle}
          placeholder="搜索 Persona 名称..."
          value={searchQuery}
          onChange={(e) => { setSearchQuery(e.target.value); setPage(0); }}
        />
      </div>

      {/* Card Grid */}
      <div style={gridStyle}>
        {filteredPersonas.map((p) => (
          <PersonaCard key={p.id} data={p} onClick={() => openPanel(p)} />
        ))}
        <div
          style={{ ...dashedCardStyle, minHeight: 180 }}
          onClick={() => openPanel(null)}
        >
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 24, marginBottom: 6, opacity: 0.3 }}>+</div>
            <div style={{ fontSize: 13, color: 'var(--text-dim)' }}>
              {personas.length === 0 ? '创建第一个 Persona' : '创建 Persona'}
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 4 }}>定义角色 + 技能 + MCP 服务器</div>
          </div>
        </div>
      </div>

      {/* Persona Panel */}
      <Pagination skip={page * pageSize} limit={pageSize} total={total} onPageChange={(skip) => setPage(Math.floor(skip / pageSize))} />

      {panelOpen && (
        <PersonaPanel
          key={editingPersona?.id || 'new'}
          persona={editingPersona}
          onClose={closePanel}
          onRefresh={fetchPersonas}
        />
      )}
    </div>
  );
}

// ── PersonaCard ──

function PersonaCard({ data, onClick }: { data: PersonaResource; onClick: () => void }) {
  const colorClass = ICON_COLORS[hashName(data.name) % ICON_COLORS.length];
  const tags = data.tags || [];

  return (
    <div style={cardStyle} onClick={onClick}>
      <div style={cardHeaderStyle}>
        <div style={{ ...iconStyle, background: `var(--${colorClass}-bg)`, border: `1px solid var(--${colorClass}-border)` }}>🎭</div>
        {data.agent_count !== undefined && data.agent_count > 0 && (
          <span style={{
            fontSize: 10, fontWeight: 600, padding: '2px 8px', borderRadius: 10,
            background: `var(--${colorClass}-bg)`,
            color: `var(--${colorClass}-400)`,
            border: `1px solid var(--${colorClass}-border)`,
          }}>
            {data.agent_count} Agent
          </span>
        )}
      </div>
      <div style={cardNameStyle}>{data.name}</div>
      <div style={cardDescStyle}>
        {data.role ? (data.role.length > 60 ? data.role.slice(0, 60) + '...' : data.role) : '—'}
      </div>

      {/* Tags */}
      {tags.length > 0 && (
        <div style={tagsStyle}>
          {tags.slice(0, 4).map((tag) => (
            <span key={tag} style={{
              ...tagStyle,
              background: `var(--${colorClass}-bg)`,
              color: `var(--${colorClass}-400)`,
              border: `1px solid var(--${colorClass}-border)`,
            }}>{tag}</span>
          ))}
          {tags.length > 4 && <span style={{ fontSize: 10, color: 'var(--text-dim)' }}>+{tags.length - 4}</span>}
        </div>
      )}

      <div style={cardFooterStyle}>
        <div style={cardMetaStyle}>
          <span style={{ fontFamily: 'var(--font-mono)' }}>
            {data.agent_count && data.agent_count > 0 ? `实例化: ${data.agent_count} Agent` : `实例化: 0 Agent`}
          </span>
        </div>
        <div style={{ display: 'flex', gap: 4 }}><div style={actionBtnStyle}>⚙</div></div>
      </div>
    </div>
  );
}

// ── PersonaPanel (Centered Modal) ──

function PersonaPanel({ persona, onClose, onRefresh }: {
  persona: PersonaResource | null;
  onClose: () => void;
  onRefresh: () => void;
}) {
  const isNew = !persona;

  // Form state — initialized from persona prop
  const [formData, setFormData] = useState<Record<string, string>>({
    name: persona?.name || '',
    role: persona?.role || '',
    expertise: persona?.expertise || '',
    constraints: persona?.constraints || '',
    prompt_template: persona?.prompt_template || '',
    output_format: persona?.output_format || '',
  });

  // Tags — search + select
  const [selectedTags, setSelectedTags] = useState<Set<string>>(new Set(persona?.tags || []));
  const [tagSearch, setTagSearch] = useState('');
  const [tagDropdownOpen, setTagDropdownOpen] = useState(false);
  const tagDropdownRef = useRef<HTMLDivElement>(null);

  // Skills
  const [allSkills, setAllSkills] = useState<SkillSummary[]>([]);
  const [selectedSkillIds, setSelectedSkillIds] = useState<Set<string>>(new Set(persona?.skill_ids || []));
  const [skillSearch, setSkillSearch] = useState('');
  const [skillDropdownOpen, setSkillDropdownOpen] = useState(false);
  const skillDropdownRef = useRef<HTMLDivElement>(null);

  // MCP Servers
  const [allServers, setAllServers] = useState<MCPServerSummary[]>([]);
  const [selectedServerIds, setSelectedServerIds] = useState<Set<string>>(new Set(persona?.mcp_server_ids || []));
  const [serverSearch, setServerSearch] = useState('');
  const [serverDropdownOpen, setServerDropdownOpen] = useState(false);
  const serverDropdownRef = useRef<HTMLDivElement>(null);

  // Toast
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' | 'info' } | null>(null);
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [fullPreviewOpen, setFullPreviewOpen] = useState(false);

  const showToast = (message: string, type: 'success' | 'error' | 'info' = 'info') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  };

  // Load reference data
  // 注意：/skills 与 /mcp-servers 返回的是 { items: [...] } 分页结构（非裸数组），
  // 直接 setAllSkills(data) 会让 state 变成对象，后续 .filter 抛 TypeError。
  // 统一解包为数组（与 fetchPersonas 同样的防御范式）。
  const unwrapItems = <T,>(data: unknown): T[] =>
    Array.isArray(data) ? data : ((data as { items?: T[] })?.items ?? []);

  useEffect(() => {
    api.get<unknown>('/api/v1/skills')
      .then((data) => setAllSkills(unwrapItems<SkillSummary>(data)))
      .catch(() => {});
    api.get<unknown>('/api/v1/mcp-servers')
      .then((data) => setAllServers(unwrapItems<MCPServerSummary>(data)))
      .catch(() => {});
  }, []);

  // Close dropdowns on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (tagDropdownRef.current && !tagDropdownRef.current.contains(e.target as Node)) setTagDropdownOpen(false);
      if (skillDropdownRef.current && !skillDropdownRef.current.contains(e.target as Node)) setSkillDropdownOpen(false);
      if (serverDropdownRef.current && !serverDropdownRef.current.contains(e.target as Node)) setServerDropdownOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const updateField = (field: string, value: string) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
  };

  const handleSave = async () => {
    if (!formData.name.trim()) {
      showToast('请输入角色名称', 'error');
      return;
    }
    setSaving(true);
    try {
      const body: Record<string, any> = {
        name: formData.name.trim(),
        role: formData.role || undefined,
        expertise: formData.expertise || undefined,
        constraints: formData.constraints || undefined,
        prompt_template: formData.prompt_template || undefined,
        output_format: formData.output_format || undefined,
        tags: selectedTags.size > 0 ? Array.from(selectedTags) : [],
        skill_ids: selectedSkillIds.size > 0 ? Array.from(selectedSkillIds) : undefined,
        mcp_server_ids: selectedServerIds.size > 0 ? Array.from(selectedServerIds) : undefined,
      };

      if (isNew) {
        await api.post('/api/v1/personas', body);
        showToast('Persona 创建成功', 'success');
      } else {
        await api.put(`/api/v1/personas/${persona!.id}`, body);
        showToast('Persona 更新成功', 'success');
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
    if (!persona?.id) return;
    setDeleting(true);
    try {
      await api.del(`/api/v1/personas/${persona.id}`);
      setConfirmDelete(false);
      onRefresh();
      onClose();
      showToast('Persona 已删除', 'success');
    } catch (e: any) {
      showToast('删除失败: ' + (e?.message || String(e)), 'error');
    } finally {
      setDeleting(false);
    }
  };

  // Filter helpers
  const filteredSkills = allSkills.filter((s) =>
    !selectedSkillIds.has(s.id) && s.name.toLowerCase().includes(skillSearch.toLowerCase())
  );
  const filteredServers = allServers.filter((s) =>
    !selectedServerIds.has(s.id) && s.name.toLowerCase().includes(serverSearch.toLowerCase())
  );

  // Lookup helpers
  const skillNameMap = useMemo(() => {
    const m: Record<string, string> = {};
    allSkills.forEach((s) => { m[s.id] = s.name; });
    return m;
  }, [allSkills]);
  const serverNameMap = useMemo(() => {
    const m: Record<string, string> = {};
    allServers.forEach((s) => { m[s.id] = s.name; });
    return m;
  }, [allServers]);

  const colorClass = 'purple';
  const panelName = formData.name || (isNew ? '创建 Persona' : persona?.name);

  return (
    <>
      {/* Overlay */}
      <div onClick={onClose} style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
        zIndex: 100, backdropFilter: 'blur(4px)',
      }} />

      {/* Modal */}
      <div style={{
        position: 'fixed', top: '50%', left: '50%',
        transform: 'translate(-50%, -50%)',
        zIndex: 101, width: 620, height: 600,
        background: 'var(--bg-base)', borderRadius: 16,
        border: '1px solid var(--border-subtle)',
        boxShadow: '0 24px 64px rgba(0,0,0,0.55)',
        display: 'flex', flexDirection: 'column',
      }}>
        {/* Header */}
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: '20px 24px', borderBottom: '1px solid var(--border-subtle)', flexShrink: 0,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{
              width: 44, height: 44, borderRadius: 12, display: 'flex',
              alignItems: 'center', justifyContent: 'center', fontSize: 20,
              background: `var(--${colorClass}-bg)`, border: `1px solid var(--${colorClass}-border)`,
            }}>🎭</div>
            <div>
              <div style={{ fontSize: 18, fontWeight: 700 }}>{panelName}</div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 3 }}>
                {isNew ? '定义 AI 角色的人格、能力与行为约束' : (persona?.role || '').slice(0, 50) || '—'}
              </div>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {!isNew && (
              <button
                onClick={() => setConfirmDelete(true)}
                style={{
                  width: 32, height: 32, borderRadius: 8,
                  border: '1px solid var(--red-border)', background: 'var(--red-bg)',
                  color: 'var(--red-400)', cursor: 'pointer', fontSize: 14,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}
              >🗑</button>
            )}
            <button onClick={onClose} style={{
              width: 32, height: 32, borderRadius: 8,
              border: '1px solid var(--border-medium)', background: 'var(--bg-card)',
              color: 'var(--text-muted)', cursor: 'pointer', fontSize: 14,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>✕</button>
          </div>
        </div>

        {/* Body */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px', minHeight: 0 }}>
          {/* Section: 角色定义 */}
          <SectionTitle>角色定义</SectionTitle>

          <FormField label="角色名称">
            <input
              style={formInputStyle}
              value={formData.name}
              onChange={(e) => updateField('name', e.target.value)}
              placeholder="输入角色名称"
            />
          </FormField>

          <FormField label="角色定位">
            <textarea
              style={{ ...formInputStyle, minHeight: 64, resize: 'vertical' as const }}
              value={formData.role}
              onChange={(e) => updateField('role', e.target.value)}
              placeholder="你是一位资深软件架构师，拥有15年企业级系统设计经验..."
            />
          </FormField>

          <FormField label="专业领域">
            <textarea
              style={{ ...formInputStyle, minHeight: 64, resize: 'vertical' as const }}
              value={formData.expertise}
              onChange={(e) => updateField('expertise', e.target.value)}
              placeholder={'核心能力：\n- 系统架构设计：微服务、事件驱动、DDD\n- 技术选型评估：框架对比、ROI分析'}
            />
          </FormField>

          <FormField label="行为约束">
            <textarea
              style={{ ...formInputStyle, minHeight: 64, resize: 'vertical' as const }}
              value={formData.constraints}
              onChange={(e) => updateField('constraints', e.target.value)}
              placeholder={'行为边界：\n- 不做具体代码实现\n- 方案必须包含trade-off分析'}
            />
          </FormField>

          <FormField label="输出格式规范">
            <textarea
              style={{ ...formInputStyle, minHeight: 64, resize: 'vertical' as const }}
              value={formData.output_format}
              onChange={(e) => updateField('output_format', e.target.value)}
              placeholder={'先给出架构概览，再逐层分析。方案必须包含：\n- 替代方案对比\n- 优劣分析\n- 成本估算\n- 安全风险评估'}
            />
          </FormField>

          <FormField label="提示词模板">
            <textarea
              style={{ ...formInputStyle, minHeight: 60, resize: 'vertical' as const, fontFamily: 'var(--font-mono)', fontSize: 12 }}
              value={formData.prompt_template}
              onChange={(e) => updateField('prompt_template', e.target.value)}
              placeholder={`# 角色身份\n{role}\n\n# 核心能力\n{expertise}\n\n# 行为边界\n{constraints}\n\n# 可用技能\n{skills}\n\n# MCP 服务器\n{mcp_servers}\n\n# 任务\n{task}`}
            />
            <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 6 }}>
              可用变量: {'{'}role{'}'} {'{'}expertise{'}'} {'{'}constraints{'}'} {'{'}output_format{'}'} {'{'}skills{'}'} {'{'}mcp_servers{'}'} {'{'}task{'}'} — Agent 运行时会替换
            </div>
          </FormField>

          {/* Prompt preview */}
          <PromptPreview
            template={formData.prompt_template}
            role={formData.role}
            expertise={formData.expertise}
            constraints={formData.constraints}
            outputFormat={formData.output_format}
            skillIds={selectedSkillIds}
            serverIds={selectedServerIds}
            skillNameMap={skillNameMap}
            serverNameMap={serverNameMap}
          />

          {/* Section: 技能配置 */}
          <SectionTitle>技能配置</SectionTitle>

          {/* Selected skill chips */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 8 }}>
            {Array.from(selectedSkillIds).map((sid) => (
              <span key={sid} style={{
                display: 'inline-flex', alignItems: 'center', gap: 4,
                padding: '4px 8px', borderRadius: 6, fontSize: 11, fontWeight: 500,
                background: 'var(--gold-bg)', color: 'var(--gold-400)',
                border: '1px solid var(--gold-border)',
              }}>
                📐 {skillNameMap[sid] || sid.slice(0, 8)}
                <span
                  onClick={() => setSelectedSkillIds((prev) => { const next = new Set(prev); next.delete(sid); return next; })}
                  style={{ cursor: 'pointer', fontSize: 13, opacity: 0.6, marginLeft: 2 }}
                >×</span>
              </span>
            ))}
          </div>

          <div ref={skillDropdownRef} style={{ position: 'relative' }}>
            <div
              onClick={() => setSkillDropdownOpen(!skillDropdownOpen)}
              style={{
                ...formInputStyle, cursor: 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                color: 'var(--text-dim)',
              }}
            >
              <span>+ 添加 Skill</span>
              <span style={{ fontSize: 10 }}>▼</span>
            </div>
            {skillDropdownOpen && (
              <div style={{
                position: 'absolute', top: '100%', left: 0, right: 0,
                marginTop: 4, background: 'var(--bg-base)',
                border: '1px solid var(--border-subtle)', borderRadius: 10,
                boxShadow: '0 12px 32px rgba(0,0,0,0.35)', zIndex: 10,
                maxHeight: 200, overflow: 'hidden',
                display: 'flex', flexDirection: 'column',
              }}>
                <input
                  autoFocus
                  style={{ ...formInputStyle, border: 'none', borderRadius: 0, borderBottom: '1px solid var(--border-subtle)' }}
                  placeholder="搜索 Skill..."
                  value={skillSearch}
                  onChange={(e) => setSkillSearch(e.target.value)}
                  onClick={(e) => e.stopPropagation()}
                />
                <div style={{ overflowY: 'auto', flex: 1 }}>
                  {filteredSkills.length === 0 ? (
                    <div style={{ padding: 12, fontSize: 12, color: 'var(--text-dim)', textAlign: 'center' }}>无可用 Skill</div>
                  ) : (
                    filteredSkills.map((s) => (
                      <div
                        key={s.id}
                        onClick={() => {
                          setSelectedSkillIds((prev) => new Set(prev).add(s.id));
                          setSkillSearch('');
                        }}
                        style={{
                          padding: '7px 12px', cursor: 'pointer', fontSize: 12,
                          color: 'var(--text-primary)',
                          borderBottom: '1px solid var(--border-subtle)',
                        }}
                        onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--bg-card)'; }}
                        onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
                      >
                        <span>📐 {s.name}</span>
                        {s.description && (
                          <span style={{ fontSize: 10, color: 'var(--text-dim)', marginLeft: 8 }}>{s.description.slice(0, 40)}</span>
                        )}
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Section: MCP 服务器 */}
          <SectionTitle>MCP 服务器</SectionTitle>

          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 8 }}>
            {Array.from(selectedServerIds).map((sid) => (
              <span key={sid} style={{
                display: 'inline-flex', alignItems: 'center', gap: 4,
                padding: '4px 8px', borderRadius: 6, fontSize: 11, fontWeight: 500,
                background: 'var(--blue-bg)', color: 'var(--blue-400)',
                border: '1px solid var(--blue-border)',
              }}>
                🔌 {serverNameMap[sid] || sid.slice(0, 8)}
                <span
                  onClick={() => setSelectedServerIds((prev) => { const next = new Set(prev); next.delete(sid); return next; })}
                  style={{ cursor: 'pointer', fontSize: 13, opacity: 0.6, marginLeft: 2 }}
                >×</span>
              </span>
            ))}
          </div>

          <div ref={serverDropdownRef} style={{ position: 'relative' }}>
            <div
              onClick={() => setServerDropdownOpen(!serverDropdownOpen)}
              style={{
                ...formInputStyle, cursor: 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                color: 'var(--text-dim)',
              }}
            >
              <span>+ 添加 MCP 服务器</span>
              <span style={{ fontSize: 10 }}>▼</span>
            </div>
            {serverDropdownOpen && (
              <div style={{
                position: 'absolute', top: '100%', left: 0, right: 0,
                marginTop: 4, background: 'var(--bg-base)',
                border: '1px solid var(--border-subtle)', borderRadius: 10,
                boxShadow: '0 12px 32px rgba(0,0,0,0.35)', zIndex: 10,
                maxHeight: 200, overflow: 'hidden',
                display: 'flex', flexDirection: 'column',
              }}>
                <input
                  autoFocus
                  style={{ ...formInputStyle, border: 'none', borderRadius: 0, borderBottom: '1px solid var(--border-subtle)' }}
                  placeholder="搜索 MCP 服务器..."
                  value={serverSearch}
                  onChange={(e) => setServerSearch(e.target.value)}
                  onClick={(e) => e.stopPropagation()}
                />
                <div style={{ overflowY: 'auto', flex: 1 }}>
                  {filteredServers.length === 0 ? (
                    <div style={{ padding: 12, fontSize: 12, color: 'var(--text-dim)', textAlign: 'center' }}>无可用 MCP 服务器</div>
                  ) : (
                    filteredServers.map((srv) => (
                      <div
                        key={srv.id}
                        onClick={() => {
                          setSelectedServerIds((prev) => new Set(prev).add(srv.id));
                          setServerSearch('');
                        }}
                        style={{
                          padding: '7px 12px', cursor: 'pointer', fontSize: 12,
                          color: 'var(--text-primary)',
                          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                          borderBottom: '1px solid var(--border-subtle)',
                        }}
                        onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--bg-card)'; }}
                        onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
                      >
                        <span>🔌 {srv.name}</span>
                        <span style={{
                          fontSize: 9, fontWeight: 500,
                          color: srv.status === 'connected' ? 'var(--green-400)' : 'var(--text-dim)',
                        }}>{srv.transport}</span>
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Section: 标签 */}
          <SectionTitle>标签</SectionTitle>

          {/* Selected tag chips */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 8 }}>
            {Array.from(selectedTags).map((tag) => (
              <span key={tag} style={{
                display: 'inline-flex', alignItems: 'center', gap: 4,
                padding: '4px 8px', borderRadius: 6, fontSize: 11, fontWeight: 500,
                background: 'var(--purple-bg)', color: 'var(--purple-400)',
                border: '1px solid var(--purple-border)',
              }}>
                {tag}
                <span
                  onClick={() => setSelectedTags((prev) => { const next = new Set(prev); next.delete(tag); return next; })}
                  style={{ cursor: 'pointer', fontSize: 13, opacity: 0.6, marginLeft: 2 }}
                >×</span>
              </span>
            ))}
          </div>

          <div ref={tagDropdownRef} style={{ position: 'relative' }}>
            <div
              onClick={() => setTagDropdownOpen(!tagDropdownOpen)}
              style={{
                ...formInputStyle, cursor: 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                color: 'var(--text-dim)',
              }}
            >
              <span>+ 添加标签</span>
              <span style={{ fontSize: 10 }}>▼</span>
            </div>
            {tagDropdownOpen && (
              <div style={{
                position: 'absolute', top: '100%', left: 0, right: 0,
                marginTop: 4, background: 'var(--bg-base)',
                border: '1px solid var(--border-subtle)', borderRadius: 10,
                boxShadow: '0 12px 32px rgba(0,0,0,0.35)', zIndex: 10,
                maxHeight: 200, overflow: 'hidden',
                display: 'flex', flexDirection: 'column',
              }}>
                <input
                  autoFocus
                  style={{ ...formInputStyle, border: 'none', borderRadius: 0, borderBottom: '1px solid var(--border-subtle)' }}
                  placeholder="搜索或输入新标签..."
                  value={tagSearch}
                  onChange={(e) => setTagSearch(e.target.value)}
                  onClick={(e) => e.stopPropagation()}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && tagSearch.trim()) {
                      const newTag = tagSearch.trim();
                      if (!selectedTags.has(newTag)) {
                        setSelectedTags((prev) => new Set(prev).add(newTag));
                      }
                      setTagSearch('');
                    }
                  }}
                />
                <div style={{ overflowY: 'auto', flex: 1 }}>
                  {PRESET_TAG_OPTIONS.filter((t) =>
                    !selectedTags.has(t) && t.toLowerCase().includes(tagSearch.toLowerCase())
                  ).length === 0 ? (
                    <div style={{ padding: 12, fontSize: 12, color: 'var(--text-dim)', textAlign: 'center' }}>
                      {tagSearch.trim() ? '按 Enter 添加新标签' : '无可用标签'}
                    </div>
                  ) : (
                    PRESET_TAG_OPTIONS.filter((t) =>
                      !selectedTags.has(t) && t.toLowerCase().includes(tagSearch.toLowerCase())
                    ).map((tag) => (
                      <div
                        key={tag}
                        onClick={() => {
                          setSelectedTags((prev) => new Set(prev).add(tag));
                          setTagSearch('');
                        }}
                        style={{
                          padding: '7px 12px', cursor: 'pointer', fontSize: 12,
                          color: 'var(--text-primary)',
                          borderBottom: '1px solid var(--border-subtle)',
                        }}
                        onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--bg-card)'; }}
                        onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
                      >{tag}</div>
                    ))
                  )}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div style={{
          display: 'flex', justifyContent: 'space-between', gap: 8,
          padding: '16px 24px', borderTop: '1px solid var(--border-subtle)', flexShrink: 0,
        }}>
          <button
            style={{ ...btnSecondaryStyle, display: 'flex', alignItems: 'center', gap: 4 }}
            onClick={() => setFullPreviewOpen(true)}
          >👁 预览完整 Prompt</button>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              style={btnSecondaryStyle}
              onClick={() => {
                setFormData({
                  name: '', role: '', expertise: '', constraints: '',
                  prompt_template: '', output_format: '',
                });
                setSelectedTags(new Set());
                setSelectedSkillIds(new Set());
                setSelectedServerIds(new Set());
              }}
            >重置</button>
            <button
              style={btnPrimaryStyle}
              onClick={handleSave}
              disabled={saving}
            >{saving ? '保存中...' : '保存'}</button>
          </div>
        </div>
      </div>

      {/* Full Prompt Preview Modal */}
      {fullPreviewOpen && (
        <FullPromptPreview
          template={formData.prompt_template}
          role={formData.role}
          expertise={formData.expertise}
          constraints={formData.constraints}
          outputFormat={formData.output_format}
          skillIds={selectedSkillIds}
          serverIds={selectedServerIds}
          skillNameMap={skillNameMap}
          serverNameMap={serverNameMap}
          personaName={formData.name}
          onClose={() => setFullPreviewOpen(false)}
        />
      )}

      {/* Confirm Delete Modal */}
      {confirmDelete && (
        <>
          <div onClick={() => setConfirmDelete(false)} style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 200, backdropFilter: 'blur(4px)',
          }} />
          <div style={{
            position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%,-50%)', zIndex: 201,
            width: 380, background: 'var(--bg-base)', borderRadius: 16,
            border: '1px solid var(--border-subtle)', padding: 28,
            boxShadow: '0 24px 48px rgba(0,0,0,0.5)', textAlign: 'center',
          }}>
            <div style={{ fontSize: 40, marginBottom: 12 }}>⚠️</div>
            <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 6 }}>确认删除</div>
            <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6, marginBottom: 24 }}>
              确定要删除 Persona「{persona?.name}」吗？此操作不可撤销。
            </div>
            <div style={{ display: 'flex', gap: 10, justifyContent: 'center' }}>
              <button onClick={() => setConfirmDelete(false)} style={{
                padding: '8px 24px', borderRadius: 8, border: '1px solid var(--border-medium)',
                background: 'var(--bg-card)', color: 'var(--text-secondary)', cursor: 'pointer', fontSize: 13,
              }}>取消</button>
              <button disabled={deleting} onClick={handleDelete} style={{
                padding: '8px 24px', borderRadius: 8, border: 'none',
                background: 'var(--red-400)', color: '#fff', cursor: 'pointer', fontSize: 13, fontWeight: 600,
              }}>{deleting ? '删除中...' : '确认删除'}</button>
            </div>
          </div>
        </>
      )}

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
          <span style={{ marginRight: 8 }}>
            {toast.type === 'success' ? '✓' : toast.type === 'error' ? '✗' : 'ℹ'}
          </span>
          {toast.message}
        </div>
      )}
    </>
  );
}

// ── PromptPreview ──

function PromptPreview({ template, role, expertise, constraints, outputFormat, skillIds, serverIds, skillNameMap, serverNameMap }: {
  template: string;
  role: string;
  expertise: string;
  constraints: string;
  outputFormat: string;
  skillIds: Set<string>; serverIds: Set<string>;
  skillNameMap: Record<string, string>; serverNameMap: Record<string, string>;
}) {
  const skillText = skillIds.size > 0
    ? Array.from(skillIds).map((id) => `- ${skillNameMap[id] || id}`).join('\n')
    : '(未配置)';
  const serverText = serverIds.size > 0
    ? Array.from(serverIds).map((id) => `- ${serverNameMap[id] || id}`).join('\n')
    : '(未配置)';

  const assembled = template
    .replace(/\{role\}/g, role || '(未填写)')
    .replace(/\{expertise\}/g, expertise || '(未填写)')
    .replace(/\{constraints\}/g, constraints || '(未填写)')
    .replace(/\{output_format\}/g, outputFormat || '(未填写)')
    .replace(/\{skills\}/g, skillText)
    .replace(/\{mcp_servers\}/g, serverText)
    .replace(/\{task\}/g, '{用户任务}');

  const hasContent = template.trim().length > 0;

  return (
    <div style={{ marginTop: 4 }}>
      <div style={{
        fontSize: 10, fontWeight: 600, color: 'var(--text-dim)',
        textTransform: 'uppercase' as const, letterSpacing: 0.5,
        marginBottom: 6, display: 'flex', alignItems: 'center', gap: 6,
      }}>
        最终 Prompt 预览
        <span style={{
          fontSize: 9, fontWeight: 400, color: 'var(--text-dim)',
          background: 'var(--bg-card)', padding: '1px 6px', borderRadius: 3,
        }}>实时</span>
      </div>
      <pre style={{
        background: '#0d1117',
        border: '1px solid rgba(148,163,184,0.1)',
        borderRadius: 8,
        padding: 12,
        fontSize: 11,
        fontFamily: 'var(--font-mono)',
        color: hasContent ? '#c9d1d9' : 'var(--text-dim)',
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-word',
        lineHeight: 1.5,
        maxHeight: 200,
        overflowY: 'auto',
        margin: 0,
      }}>
        {hasContent ? assembled : '在提示词模板中填入内容并引用变量后，此处将显示组装后的最终 Prompt'}
      </pre>
    </div>
  );
}

// ── FullPromptPreview (full-screen modal) ──

function FullPromptPreview({
  template, role, expertise, constraints, outputFormat,
  skillIds, serverIds, skillNameMap, serverNameMap, personaName, onClose,
}: {
  template: string; role: string; expertise: string; constraints: string; outputFormat: string;
  skillIds: Set<string>; serverIds: Set<string>;
  skillNameMap: Record<string, string>; serverNameMap: Record<string, string>;
  personaName: string; onClose: () => void;
}) {
  const skillText = skillIds.size > 0
    ? Array.from(skillIds).map((id) => `- ${skillNameMap[id] || id}`).join('\n')
    : '(未配置)';
  const serverText = serverIds.size > 0
    ? Array.from(serverIds).map((id) => `- ${serverNameMap[id] || id}`).join('\n')
    : '(未配置)';

  const skillList = Array.from(skillIds);
  const serverList = Array.from(serverIds);

  const assembled = (template || '').trim()
    ? template
        .replace(/\{role\}/g, role || '(未填写)')
        .replace(/\{expertise\}/g, expertise || '(未填写)')
        .replace(/\{constraints\}/g, constraints || '(未填写)')
        .replace(/\{output_format\}/g, outputFormat || '(未填写)')
        .replace(/\{skills\}/g, skillText)
        .replace(/\{mcp_servers\}/g, serverText)
        .replace(/\{task\}/g, '{用户任务}')
    : '';

  // If no template, build from structured fields directly
  const fallbackPrompt = !(template || '').trim()
    ? [
        role && `# 角色身份\n${role}`,
        expertise && `# 核心能力\n${expertise}`,
        constraints && `# 行为边界\n${constraints}`,
        outputFormat && `# 输出格式\n${outputFormat}`,
        skillList.length > 0 && `# 可用技能\n${skillList.map((id) => `- ${skillNameMap[id] || id}`).join('\n')}`,
        serverList.length > 0 && `# 可用MCP服务器\n${serverList.map((id) => `- ${serverNameMap[id] || id}`).join('\n')}`,
        '\n# 任务\n{用户任务}',
      ].filter(Boolean).join('\n\n')
    : '';

  const finalPrompt = assembled || fallbackPrompt;

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(finalPrompt);
    } catch {
      // fallback
      const ta = document.createElement('textarea');
      ta.value = finalPrompt;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
    }
  };

  return (
    <>
      <div onClick={onClose} style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)',
        zIndex: 300, backdropFilter: 'blur(6px)',
      }} />
      <div style={{
        position: 'fixed', top: '50%', left: '50%',
        transform: 'translate(-50%, -50%)',
        zIndex: 301, width: '85vw', maxWidth: 860,
        height: '85vh', maxHeight: 720,
        background: 'var(--bg-base)', borderRadius: 16,
        border: '1px solid var(--border-subtle)',
        boxShadow: '0 24px 64px rgba(0,0,0,0.55)',
        display: 'flex', flexDirection: 'column',
      }}>
        {/* Header */}
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: '16px 24px', borderBottom: '1px solid var(--border-subtle)', flexShrink: 0,
        }}>
          <div>
            <div style={{ fontSize: 16, fontWeight: 700 }}>
              完整 Prompt 预览{personaName ? ` — ${personaName}` : ''}
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 3 }}>
              组装后的完整系统提示词，Agent 运行时将使用此内容
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              onClick={handleCopy}
              style={{
                padding: '6px 16px', borderRadius: 8, fontSize: 12, fontWeight: 600,
                border: '1px solid var(--border-medium)', background: 'var(--bg-card)',
                color: 'var(--text-primary)', cursor: 'pointer',
                display: 'flex', alignItems: 'center', gap: 4,
              }}
            >📋 复制</button>
            <button onClick={onClose} style={{
              width: 32, height: 32, borderRadius: 8,
              border: '1px solid var(--border-medium)', background: 'var(--bg-card)',
              color: 'var(--text-muted)', cursor: 'pointer', fontSize: 14,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>✕</button>
          </div>
        </div>

        {/* Body */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px', minHeight: 0 }}>
          <pre style={{
            background: '#0d1117',
            border: '1px solid rgba(148,163,184,0.12)',
            borderRadius: 10,
            padding: '20px 24px',
            fontSize: 12,
            fontFamily: 'var(--font-mono)',
            color: finalPrompt ? '#c9d1d9' : 'var(--text-dim)',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
            lineHeight: 1.65,
            margin: 0,
            minHeight: 200,
          }}>
            {finalPrompt || '请填写角色定义和提示词模板后，再预览完整 Prompt'}
          </pre>
        </div>
      </div>
    </>
  );
}

// ── Form Helpers ──

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      fontSize: 11, fontWeight: 600, color: 'var(--text-dim)',
      textTransform: 'uppercase' as const, letterSpacing: 0.5,
      marginBottom: 10, marginTop: 22,
      display: 'flex', alignItems: 'center', gap: 6,
    }}>
      {children}
    </div>
  );
}

function FormField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <label style={formLabelStyle}>{label}</label>
      {children}
    </div>
  );
}

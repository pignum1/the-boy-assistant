import { useState, useEffect, useCallback, useMemo } from 'react';
import { api } from '../../shared/api/client';

// ── Types ──

interface ModelResource {
  id: string; name: string; provider: string; context_window: number;
  capabilities?: string[]; status?: string; api_key_masked?: string;
  agent_count?: number;
}

interface PersonaResource {
  id: string; name: string;
  role?: string; expertise?: string; constraints?: string;
  system_prompt?: string; prompt_template?: string;
  capabilities?: Record<string, number>; tags?: string[];
  tools_declared?: string[]; output_prefs?: Record<string, string>;
  temperature?: number; max_tokens?: number; top_p?: number;
  agent_count?: number;
}

interface ToolResource {
  id: string; name: string; description?: string; tool_type?: string;
  status?: string; agent_count?: number; call_count?: number;
}

interface AgentResource {
  id: string; name: string; persona_id?: string; default_model_id?: string;
  persona_name?: string; model_name?: string; tools?: string[];
  status?: string; team_name?: string; current_task?: string;
}

interface SkillResource {
  id: string; name: string; description?: string;
  file_path?: string; trigger_condition?: string;
  tags?: string[]; status?: string;
}

type TabKey = 'models' | 'tools' | 'skills' | 'personas' | 'agents';

// ── Provider Config ──

const PROVIDER_CONFIG: Record<string, { icon: string; label: string; color: string }> = {
  openai: { icon: 'O', label: 'OpenAI', color: 'var(--green-400)' },
  anthropic: { icon: 'A', label: 'Anthropic', color: 'var(--orange-400)' },
  google: { icon: 'G', label: 'Google', color: 'var(--blue-400)' },
  deepseek: { icon: 'D', label: 'DeepSeek', color: 'var(--cyan-400)' },
  meta: { icon: 'M', label: 'Meta', color: 'var(--blue-400)' },
  zhipu: { icon: '智', label: '智谱', color: 'var(--red-400)' },
  mistral: { icon: 'M', label: 'Mistral', color: 'var(--indigo-400)' },
  xai: { icon: 'X', label: 'xAI', color: 'var(--white)' },
  test: { icon: 'T', label: 'Test', color: 'var(--text-muted)' },
};

const PROVIDER_OPTIONS = Object.entries(PROVIDER_CONFIG).map(([key, cfg]) => ({
  value: key,
  label: `${cfg.icon}  ${cfg.label}`,
}));

// ── Static model versions fallback (when provider API is unreachable) ──

const PROVIDER_MODELS: Record<string, {value: string; label: string}[]> = {
  openai: [
    {value: 'gpt-4.1', label: 'GPT-4.1'},
    {value: 'gpt-4.1-mini', label: 'GPT-4.1 Mini'},
    {value: 'gpt-4.1-nano', label: 'GPT-4.1 Nano'},
    {value: 'o4-mini', label: 'o4 Mini'},
  ],
  anthropic: [
    {value: 'claude-opus-4-6', label: 'Claude Opus 4.6'},
    {value: 'claude-sonnet-4-6', label: 'Claude Sonnet 4.6'},
    {value: 'claude-haiku-4-5', label: 'Claude Haiku 4.5'},
  ],
  google: [
    {value: 'gemini-2.5-pro', label: 'Gemini 2.5 Pro'},
    {value: 'gemini-2.5-flash', label: 'Gemini 2.5 Flash'},
  ],
  deepseek: [
    {value: 'deepseek-v4-pro', label: 'DeepSeek V4 Pro'},
    {value: 'deepseek-v4-flash', label: 'DeepSeek V4 Flash'},
  ],
  meta: [
    {value: 'llama-4-maverick', label: 'Llama 4 Maverick'},
    {value: 'llama-4-scout', label: 'Llama 4 Scout'},
  ],
  zhipu: [
    {value: 'glm-5.1', label: 'GLM-5.1'},
    {value: 'glm-5.1-flash', label: 'GLM-5.1 Flash'},
  ],
  mistral: [
    {value: 'mistral-large-2', label: 'Mistral Large 2'},
  ],
  xai: [
    {value: 'grok-3', label: 'Grok-3'},
  ],
};

function getProviderColorKey(color?: string): string {
  const match = color?.match(/var\(--(\w+)-\d+\)/);
  return match ? match[1] : 'gold';
}

const PROVIDER_DEFAULT_BASE_URL: Record<string, string> = {
  openai: 'https://api.openai.com/v1',
  deepseek: 'https://api.deepseek.com/v1',
  anthropic: 'https://api.anthropic.com/v1',
  google: 'https://generativelanguage.googleapis.com/v1beta',
  zhipu: 'https://open.bigmodel.cn/api/paas/v4',
  meta: 'https://api.llama-api.com/v1',
  mistral: 'https://api.mistral.ai/v1',
  xai: 'https://api.x.ai/v1',
};

// ── Style helpers ──

const ICON_COLORS = ['gold', 'green', 'blue', 'purple'] as const;

const TAB_CONFIG: Record<TabKey, { label: string; icon: string; layer: string; layerLabel: string }> = {
  models: { label: '模型', icon: '🧠', layer: 'l1', layerLabel: 'L1' },
  tools: { label: '工具', icon: '🔧', layer: 'l1', layerLabel: 'L1' },
  skills: { label: 'Skill', icon: '📐', layer: 'l3', layerLabel: 'L3' },
  personas: { label: 'Persona', icon: '🎭', layer: 'l1', layerLabel: 'L1' },
  agents: { label: 'Agent', icon: '🤖', layer: 'l1c', layerLabel: 'L1组合' },
};

const SEARCH_HINTS: Record<TabKey, string> = {
  models: '搜索模型名称...', tools: '搜索工具名称...', skills: '搜索 Skill 名称...',
  personas: '搜索 Persona 名称...', agents: '搜索 Agent 名称...',
};

const REGISTER_LABELS: Record<TabKey, string> = {
  models: '+ 注册模型', tools: '+ 注册工具', skills: '+ 注册 Skill',
  personas: '+ 创建 Persona', agents: '+ 注册 Agent',
};

const STATUS_STYLE: Record<string, { bg: string; color: string }> = {
  online: { bg: 'var(--green-bg)', color: 'var(--green-400)' },
  busy: { bg: 'var(--gold-bg)', color: 'var(--gold-400)' },
  idle: { bg: 'rgba(148,163,184,0.06)', color: 'var(--text-muted)' },
  offline: { bg: 'rgba(148,163,184,0.04)', color: 'var(--text-dim)' },
};

const STATUS_LABEL: Record<string, string> = {
  online: '在线', busy: '使用中', idle: '空闲', offline: '离线',
};

// ── Main Component ──

export function Resources() {
  const [activeTab, setActiveTab] = useState<TabKey>('models');
  const [searchQuery, setSearchQuery] = useState('');
  const [filterStatus, setFilterStatus] = useState('全部状态');

  // Data
  const [models, setModels] = useState<ModelResource[]>([]);
  const [personas, setPersonas] = useState<PersonaResource[]>([]);
  const [tools, setTools] = useState<ToolResource[]>([]);
  const [agents, setAgents] = useState<AgentResource[]>([]);
  const [skills, setSkills] = useState<SkillResource[]>([]);
  const [loading, setLoading] = useState(true);

  // Detail panel
  const [panelOpen, setPanelOpen] = useState(false);
  const [panelMode, setPanelMode] = useState<'edit' | 'register'>('edit');
  const [panelResource, setPanelResource] = useState<Record<string, unknown> | null>(null);
  const [panelType, setPanelType] = useState<TabKey>('models');

  // Provider panel (models tab only)
  const [providerPanelOpen, setProviderPanelOpen] = useState(false);
  const [providerPanelKey, setProviderPanelKey] = useState<string | null>(null);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [modelsRes, personasRes, toolsRes, agentsRes, skillsRes] = await Promise.allSettled([
        api.get<ModelResource[]>('/api/v1/models'),
        api.get<PersonaResource[]>('/api/v1/personas'),
        api.get<ToolResource[]>('/api/v1/tools'),
        api.get<AgentResource[]>('/api/v1/agents'),
        api.get<SkillResource[]>('/api/v1/skills'),
      ]);
      if (modelsRes.status === 'fulfilled') setModels(modelsRes.value);
      if (personasRes.status === 'fulfilled') setPersonas(personasRes.value);
      if (toolsRes.status === 'fulfilled') setTools(toolsRes.value);
      if (agentsRes.status === 'fulfilled') setAgents(agentsRes.value);
      if (skillsRes.status === 'fulfilled') setSkills(skillsRes.value);
    } catch { /* use defaults */ }
    setLoading(false);
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const getData = (tab: TabKey) => {
    const map: Record<TabKey, unknown[]> = { models, personas, tools, agents, skills };
    return map[tab];
  };

  // Group models by provider
  const providerSummaries = useMemo(() => {
    const map = new Map<string, ModelResource[]>();
    for (const m of models) {
      if (!map.has(m.provider)) map.set(m.provider, []);
      map.get(m.provider)!.push(m);
    }
    return Object.entries(PROVIDER_CONFIG)
      .filter(([key]) => key !== 'test')
      .map(([key, config]) => ({
        key,
        config,
        models: map.get(key) || [],
        apiKeyConfigured: (map.get(key) || []).some((m) => m.api_key_masked !== null),
      }));
  }, [models]);

  const openPanel = (type: TabKey, resource: Record<string, unknown> | null, mode: 'edit' | 'register') => {
    setPanelType(type);
    setPanelResource(resource);
    setPanelMode(mode);
    setPanelOpen(true);
  };

  const closePanel = () => setPanelOpen(false);

  const switchTab = (tab: TabKey) => {
    setActiveTab(tab);
    setSearchQuery('');
    setFilterStatus('全部状态');
  };

  if (loading) {
    return (
      <div style={{ padding: '40px 32px', position: 'relative', zIndex: 1 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, letterSpacing: -0.5 }}>资源中心</h1>
        <p style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 8 }}>加载中...</p>
      </div>
    );
  }

  return (
    <div style={{ padding: '28px 32px', maxWidth: 1400, position: 'relative', zIndex: 1 }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 700, letterSpacing: -0.5 }}>资源中心</h1>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>L1 能力层 · 按依赖顺序管理资源</div>
        </div>
        <button
          className="btn-primary"
          style={btnPrimaryStyle}
          onClick={() => {
            if (activeTab === 'models') {
              setProviderPanelKey(null);
              setProviderPanelOpen(true);
            } else {
              openPanel(activeTab, null, 'register');
            }
          }}
        >
          {activeTab === 'models' ? (models.length === 0 ? '+ 配置供应商' : '+ 添加模型') : REGISTER_LABELS[activeTab]}
        </button>
      </div>

      {/* Dependency Chain */}
      <DependencyChain activeTab={activeTab} onSwitch={switchTab} />

      {/* Sub Tabs */}
      <SubTabs activeTab={activeTab} onSwitch={switchTab} counts={{
        models: models.length, personas: personas.length,
        tools: tools.length, agents: agents.length, skills: skills.length,
      }} />

      {/* Search / Filter */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 20, alignItems: 'center' }}>
        <input
          style={searchInputStyle}
          placeholder={SEARCH_HINTS[activeTab]}
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
        />
        <select
          style={filterSelectStyle}
          value={filterStatus}
          onChange={(e) => setFilterStatus(e.target.value)}
        >
          <option>全部状态</option>
          <option>在线</option>
          <option>离线</option>
          <option>使用中</option>
          <option>空闲</option>
        </select>
      </div>

      {/* Card Grid */}
      <div style={gridStyle}>
        {activeTab === 'models' ? (
          <>
            {providerSummaries
              .filter((ps) => {
                if (!searchQuery) return true;
                const q = searchQuery.toLowerCase();
                return ps.config.label.toLowerCase().includes(q) ||
                  ps.models.some((m) => String(m.name || '').toLowerCase().includes(q) ||
                    String(m.model_name || '').toLowerCase().includes(q));
              })
              .map((ps) => (
                <ProviderCard key={ps.key} summary={ps} onClick={() => { setProviderPanelKey(ps.key); setProviderPanelOpen(true); }} />
              ))}
            <div
              style={{ ...dashedCardStyle, minHeight: 180 }}
              onClick={() => { setProviderPanelKey(null); setProviderPanelOpen(true); }}
            >
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: 24, marginBottom: 6, opacity: 0.3 }}>+</div>
                <div style={{ fontSize: 13, color: 'var(--text-dim)' }}>{models.length === 0 ? '配置供应商' : '添加模型'}</div>
                <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 4 }}>选择 Provider · 配置 API Key · 管理模型</div>
              </div>
            </div>
          </>
        ) : (
          <>
            {renderCards(activeTab, getData(activeTab) as Record<string, unknown>[], searchQuery, filterStatus, openPanel)}
            <div
              style={{ ...dashedCardStyle, minHeight: 180 }}
              onClick={() => openPanel(activeTab, null, 'register')}
            >
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: 24, marginBottom: 6, opacity: 0.3 }}>+</div>
                <div style={{ fontSize: 13, color: 'var(--text-dim)' }}>
                  {REGISTER_LABELS[activeTab].replace('+ ', '')}
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 4 }}>
                  {activeTab === 'personas' ? '定义角色 + 提示词模板' :
                   activeTab === 'tools' ? 'MCP Server / REST API / 内置' :
                   activeTab === 'agents' ? '选择 Persona + Model + Tools' :
                   '文件目录 · SKILL.md + config.yaml'}
                </div>
              </div>
            </div>
          </>
        )}
      </div>

      {/* Provider Panel (models tab only) */}
      {providerPanelOpen && (
        <ProviderPanel
          providerKey={providerPanelKey}
          models={models}
          onSelectProvider={(key) => setProviderPanelKey(key)}
          onClose={() => { setProviderPanelOpen(false); setProviderPanelKey(null); }}
          onRefresh={fetchAll}
        />
      )}

      {/* Detail Panel (other tabs) */}
      {panelOpen && (
        <DetailPanel
          type={panelType}
          mode={panelMode}
          resource={panelResource}
          onClose={closePanel}
          onSwitchTab={switchTab}
          onSaved={fetchAll}
        />
      )}
    </div>
  );
}

// ── Sub-components ──

function DependencyChain({ activeTab, onSwitch }: { activeTab: TabKey; onSwitch: (t: TabKey) => void }) {
  const items: { key: TabKey; label: string; layer: string }[] = [
    { key: 'models', label: '模型', layer: 'L1' },
    { key: 'tools', label: '工具', layer: 'L1' },
    { key: 'skills', label: 'Skill', layer: 'L3' },
    { key: 'personas', label: 'Persona', layer: 'L1' },
    { key: 'agents', label: 'Agent', layer: 'L1组合' },
  ];

  return (
    <div style={relationBarStyle}>
      {items.map((item, i) => (
        <span key={item.key} style={{ display: 'flex', alignItems: 'center', gap: 0 }}>
          <span
            onClick={() => onSwitch(item.key)}
            style={{
              ...relationItemStyle,
              color: activeTab === item.key ? 'var(--gold-400)' : 'var(--text-secondary)',
              fontWeight: activeTab === item.key ? 600 : 500,
            }}
          >
            <span style={{
              fontSize: 8, padding: '1px 4px', borderRadius: 3, fontWeight: 600,
              fontFamily: 'var(--font-mono)',
              background: item.key === 'agents' ? 'var(--gold-bg)' : item.key === 'skills' ? 'var(--blue-bg)' : 'var(--green-bg)',
              color: item.key === 'agents' ? 'var(--gold-400)' : item.key === 'skills' ? 'var(--blue-400)' : 'var(--green-400)',
              border: `1px solid ${item.key === 'agents' ? 'var(--gold-border)' : item.key === 'skills' ? 'var(--blue-border)' : 'var(--green-border)'}`,
            }}>
              {item.layer}
            </span>
            {' '}{item.label}
          </span>
          {i < items.length - 1 && (
            <span style={{ fontSize: 10, color: 'var(--text-dim)', padding: '0 4px' }}>→</span>
          )}
        </span>
      ))}
      <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--text-dim)' }}>
        多模型协作在团队层配置 →
      </span>
    </div>
  );
}

function SubTabs({ activeTab, onSwitch, counts }: {
  activeTab: TabKey; onSwitch: (t: TabKey) => void; counts: Record<TabKey, number>;
}) {
  return (
    <div style={{ display: 'flex', gap: 0, borderBottom: '1px solid var(--border-subtle)', marginBottom: 20 }}>
      {(Object.entries(TAB_CONFIG) as [TabKey, typeof TAB_CONFIG['models']][]).map(([key, cfg]) => (
        <div
          key={key}
          onClick={() => onSwitch(key)}
          style={{
            padding: '10px 18px', fontSize: 13, fontWeight: 500,
            color: activeTab === key ? 'var(--green-400)' : 'var(--text-muted)',
            cursor: 'pointer', borderBottom: `2px solid ${activeTab === key ? 'var(--green-400)' : 'transparent'}`,
            transition: 'all 0.15s', display: 'flex', alignItems: 'center', gap: 6,
            whiteSpace: 'nowrap' as const,
          }}
        >
          {cfg.icon} {cfg.label}
          <span style={{
            fontSize: 10, fontFamily: 'var(--font-mono)', background: 'var(--bg-elevated)',
            padding: '1px 6px', borderRadius: 4, color: 'var(--text-dim)',
          }}>
            {counts[key]}
          </span>
          <span style={{
            fontSize: 8, padding: '1px 5px', borderRadius: 3, fontWeight: 600,
            fontFamily: 'var(--font-mono)',
            color: cfg.layer === 'l3' ? 'var(--blue-400)' : cfg.layer === 'l1c' ? 'var(--gold-400)' : 'var(--green-400)',
          }}>
            {cfg.layerLabel}
          </span>
        </div>
      ))}
    </div>
  );
}

function renderCards(
  tab: TabKey, data: Record<string, unknown>[],
  searchQuery: string, filterStatus: string,
  openPanel: (type: TabKey, resource: Record<string, unknown> | null, mode: 'edit' | 'register') => void,
) {
  let filtered = data;
  if (searchQuery) {
    const q = searchQuery.toLowerCase();
    filtered = filtered.filter((d) => String(d.name || '').toLowerCase().includes(q));
  }

  const renderMap: Record<TabKey, (d: Record<string, unknown>, i: number) => React.ReactNode> = {
    models: (d, i) => <ModelCard key={i} data={d as unknown as ModelResource} onClick={() => openPanel('models', d, 'edit')} />,
    personas: (d, i) => <PersonaCard key={i} data={d as unknown as PersonaResource} onClick={() => openPanel('personas', d, 'edit')} />,
    tools: (d, i) => <ToolCard key={i} data={d as unknown as ToolResource} onClick={() => openPanel('tools', d, 'edit')} />,
    agents: (d, i) => <AgentCard key={i} data={d as unknown as AgentResource} onClick={() => openPanel('agents', d, 'edit')} />,
    skills: (d, i) => <SkillCard key={i} data={d as unknown as SkillResource} onClick={() => openPanel('skills', d, 'edit')} />,
  };

  return filtered.map((d, i) => renderMap[tab](d, i));
}

// ── Resource Cards ──

function ProviderCard({ summary, onClick }: {
  summary: { key: string; config: { icon: string; label: string; color: string }; models: ModelResource[]; apiKeyConfigured: boolean };
  onClick: () => void;
}) {
  const { config, models, apiKeyConfigured } = summary;
  const colorKey = getProviderColorKey(config.color);
  return (
    <div style={cardStyle} onClick={onClick}>
      <div style={cardHeaderStyle}>
        <div style={{ ...iconStyle, background: `var(--${colorKey}-bg)`, border: `1px solid var(--${colorKey}-border)`, fontSize: 20 }}>{config.icon}</div>
        <span style={{
          fontSize: 10, fontWeight: 600, padding: '2px 8px', borderRadius: 10,
          background: apiKeyConfigured ? 'var(--green-bg)' : 'rgba(148,163,184,0.06)',
          color: apiKeyConfigured ? 'var(--green-400)' : 'var(--text-dim)',
          border: `1px solid ${apiKeyConfigured ? 'var(--green-border)' : 'var(--border-medium)'}`,
        }}>
          {apiKeyConfigured ? '已配置' : '未配置'}
        </span>
      </div>
      <div style={cardNameStyle}>{config.label}</div>
      <div style={cardDescStyle}>{models.length} 个模型{models.length > 0 ? ` · ${models.map((m) => m.name).join(', ')}` : ''}</div>
      <div style={{ ...cardDescStyle, marginTop: 6, display: 'flex', alignItems: 'center', gap: 4 }}>
        <span style={{ width: 6, height: 6, borderRadius: '50%', background: apiKeyConfigured ? 'var(--green-400)' : 'var(--text-dim)', display: 'inline-block' }} />
        {apiKeyConfigured ? 'API Key 已配置' : '需要配置 API Key'}
      </div>
      <div style={tagsStyle}>
        <span style={{ ...tagStyle, background: `var(--${colorKey}-bg)`, color: config.color || 'var(--text-muted)', border: `1px solid var(--${colorKey}-border)` }}>{config.label}</span>
        {models.length > 0 && <span style={{ ...tagStyle, background: 'var(--bg-elevated)', color: 'var(--text-muted)', border: '1px solid var(--border-medium)' }}>{models.length} models</span>}
      </div>
    </div>
  );
}

function ModelCard({ data, onClick }: { data: ModelResource; onClick: () => void }) {
  const pc = PROVIDER_CONFIG[data.provider];
  const colorKey = getProviderColorKey(pc?.color);
  return (
    <div style={cardStyle} onClick={onClick}>
      <div style={cardHeaderStyle}>
        <div style={{ ...iconStyle, background: `var(--${colorKey}-bg)`, border: `1px solid var(--${colorKey}-border)`, fontSize: 16 }}>{pc?.icon || '🧠'}</div>
        <span style={{ ...statusBadgeStyle, ...(STATUS_STYLE.online || {}) }}>{STATUS_LABEL.online}</span>
      </div>
      <div style={cardNameStyle}>{data.name}</div>
      <div style={cardDescStyle}>{pc?.label || data.provider}{data.capabilities?.length ? ` · ${data.capabilities.join(', ')}` : ''}</div>
      <div style={modelStatsStyle}>
        <div style={modelStatStyle}><div style={modelStatLabelStyle}>上下文</div><div style={modelStatValueStyle}>{formatContextWindow(data.context_window)}</div></div>
        <div style={modelStatStyle}><div style={modelStatLabelStyle}>延迟</div><div style={modelStatValueStyle}>-</div></div>
      </div>
      <div style={tagsStyle}>
        <span style={{ ...tagStyle, background: `var(--${colorKey}-bg)`, color: pc?.color || 'var(--text-muted)', border: `1px solid var(--${colorKey}-border)` }}>{pc?.label || data.provider}</span>
      </div>
      <div style={cardFooterStyle}>
        <div style={cardMetaStyle}>
          <span style={{ fontFamily: 'var(--font-mono)' }}>Agent: {data.agent_count ?? '-'}</span>
          <span style={{ fontFamily: 'var(--font-mono)' }}>Key: {data.api_key_masked ?? '****'}</span>
        </div>
        <div style={{ display: 'flex', gap: 4 }}>
          <div style={actionBtnStyle}>⚙</div>
        </div>
      </div>
    </div>
  );
}

function PersonaCard({ data, onClick }: { data: PersonaResource; onClick: () => void }) {
  const colorClass = ICON_COLORS[Math.floor(Math.random() * ICON_COLORS.length)];
  const capEntries = data.capabilities ? Object.entries(data.capabilities) : [];
  const tags = data.tags || [];
  return (
    <div style={cardStyle} onClick={onClick}>
      <div style={cardHeaderStyle}>
        <div style={{ ...iconStyle, background: `var(--${colorClass}-bg)`, border: `1px solid var(--${colorClass}-border)` }}>🎭</div>
        <span style={{ ...statusBadgeStyle, ...(STATUS_STYLE.busy || {}) }}>使用中</span>
      </div>
      <div style={cardNameStyle}>{data.name}</div>
      <div style={cardDescStyle}>{data.role ? (data.role.length > 60 ? data.role.slice(0, 60) + '...' : data.role) : '—'}</div>
      {/* Capability bars */}
      {capEntries.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 3, marginBottom: 10 }}>
          {capEntries.slice(0, 4).map(([k, v]) => (
            <div key={k} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ fontSize: 10, color: 'var(--text-dim)', width: 48, textAlign: 'right', flexShrink: 0 }}>{k}</span>
              <div style={{ flex: 1, height: 4, borderRadius: 2, background: 'var(--border-medium)', overflow: 'hidden' }}>
                <div style={{ height: '100%', width: `${Math.round((v as number) * 100)}%`, background: `var(--${colorClass}-400)`, borderRadius: 2 }} />
              </div>
              <span style={{ fontSize: 9, color: 'var(--text-dim)', width: 28, fontFamily: 'var(--font-mono)' }}>{Math.round((v as number) * 100)}%</span>
            </div>
          ))}
        </div>
      )}
      {/* Tags */}
      {tags.length > 0 && (
        <div style={tagsStyle}>
          {tags.slice(0, 4).map((tag) => (
            <span key={tag} style={{ ...tagStyle, background: `var(--${colorClass}-bg)`, color: `var(--${colorClass}-400)`, border: `1px solid var(--${colorClass}-border)` }}>{tag}</span>
          ))}
          {tags.length > 4 && <span style={{ fontSize: 10, color: 'var(--text-dim)' }}>+{tags.length - 4}</span>}
        </div>
      )}
      {/* Model params */}
      {(data.temperature !== undefined || data.max_tokens !== undefined) && (
        <div style={{ display: 'flex', gap: 10, marginTop: tags.length > 0 ? 6 : 10, marginBottom: 4 }}>
          {data.temperature !== undefined && <span style={{ fontSize: 10, color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>τ={data.temperature}</span>}
          {data.max_tokens !== undefined && <span style={{ fontSize: 10, color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>max={data.max_tokens}</span>}
          {data.top_p !== undefined && <span style={{ fontSize: 10, color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>top_p={data.top_p}</span>}
        </div>
      )}
      <div style={cardFooterStyle}>
        <div style={cardMetaStyle}>
          <span style={{ fontFamily: 'var(--font-mono)' }}>实例化: {data.agent_count ?? 0} Agent</span>
        </div>
        <div style={{ display: 'flex', gap: 4 }}><div style={actionBtnStyle}>⚙</div></div>
      </div>
    </div>
  );
}

function ToolCard({ data, onClick }: { data: ToolResource; onClick: () => void }) {
  const colorClass = ICON_COLORS[Math.floor(Math.random() * ICON_COLORS.length)];
  return (
    <div style={cardStyle} onClick={onClick}>
      <div style={cardHeaderStyle}>
        <div style={{ ...iconStyle, background: `var(--${colorClass}-bg)`, border: `1px solid var(--${colorClass}-border)` }}>🔧</div>
        <span style={{ ...statusBadgeStyle, ...(STATUS_STYLE.online || {}) }}>已连接</span>
      </div>
      <div style={cardNameStyle}>{data.name}</div>
      <div style={cardDescStyle}>{data.description || '—'}{data.tool_type ? ` · ${data.tool_type}` : ''}</div>
      <div style={tagsStyle}>
        <span style={{ ...tagStyle, background: `var(--${colorClass}-bg)`, color: `var(--${colorClass}-400)`, border: `1px solid var(--${colorClass}-border)` }}>{data.tool_type || 'tool'}</span>
      </div>
      <div style={cardFooterStyle}>
        <div style={cardMetaStyle}>
          <span style={{ fontFamily: 'var(--font-mono)' }}>Agent: {data.agent_count ?? '-'}</span>
          <span style={{ fontFamily: 'var(--font-mono)' }}>调用: {data.call_count ?? '-'}</span>
        </div>
        <div style={{ display: 'flex', gap: 4 }}><div style={actionBtnStyle}>⚙</div></div>
      </div>
    </div>
  );
}

function AgentCard({ data, onClick }: { data: AgentResource; onClick: () => void }) {
  const isBusy = data.status === 'busy';
  return (
    <div style={cardStyle} onClick={onClick}>
      <div style={cardHeaderStyle}>
        <div style={{ ...iconStyle, background: 'var(--gold-bg)', border: '1px solid var(--gold-border)' }}>🤖</div>
        <span style={{
          ...statusBadgeStyle,
          ...(isBusy ? STATUS_STYLE.busy : STATUS_STYLE.idle),
        }}>
          {isBusy ? '执行中' : '空闲'}
        </span>
      </div>
      <div style={cardNameStyle}>{data.name}</div>
      <div style={cardDescStyle}>
        {data.persona_name || '—'} · {data.model_name || '—'}
      </div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
        {data.persona_name && <span style={compChipStyle('purple')}>🎭 {data.persona_name}</span>}
        {data.model_name && <span style={compChipStyle('gold')}>🧠 {data.model_name}</span>}
        {data.tools?.length ? <span style={compChipStyle('green')}>🔧 {data.tools.join(', ')}</span> : null}
      </div>
      <div style={cardFooterStyle}>
        <div style={cardMetaStyle}>
          <span style={{ fontFamily: 'var(--font-mono)' }}>Team: {data.team_name || '—'}</span>
          <span style={{ fontFamily: 'var(--font-mono)' }}>{data.current_task ? `任务: ${data.current_task}` : '空闲'}</span>
        </div>
        <div style={{ display: 'flex', gap: 4 }}><div style={actionBtnStyle}>⚙</div></div>
      </div>
    </div>
  );
}

function SkillCard({ data, onClick }: { data: SkillResource; onClick: () => void }) {
  return (
    <div style={cardStyle} onClick={onClick}>
      <div style={cardHeaderStyle}>
        <div style={{ ...iconStyle, background: 'var(--gold-bg)', border: '1px solid var(--gold-border)' }}>📐</div>
        <span style={{ ...statusBadgeStyle, ...(STATUS_STYLE.busy || {}) }}>使用中</span>
      </div>
      <div style={cardNameStyle}>{data.name}</div>
      <div style={cardDescStyle}>{data.description || '—'}</div>
      <div style={{ fontSize: 10, color: 'var(--text-dim)', fontFamily: 'var(--font-mono)', background: 'var(--bg-elevated)', padding: '3px 8px', borderRadius: 4, marginBottom: 12, display: 'inline-flex', alignItems: 'center', gap: 4 }}>
        📄 {data.file_path || 'skills/'}
      </div>
      <div style={tagsStyle}>
        {data.tags?.map((t) => (
          <span key={t} style={{ ...tagStyle, background: 'var(--gold-bg)', color: 'var(--gold-400)', border: '1px solid var(--gold-border)' }}>{t}</span>
        ))}
      </div>
      <div style={cardFooterStyle}>
        <div style={cardMetaStyle}>
          <span style={{ fontFamily: 'var(--font-mono)' }}>触发: {data.trigger_condition || '手动'}</span>
        </div>
        <div style={{ display: 'flex', gap: 4 }}><div style={actionBtnStyle}>⚙</div></div>
      </div>
    </div>
  );
}

// ── Provider Panel (Models tab only) ──

function ProviderPanel({ providerKey, models, onSelectProvider, onClose, onRefresh }: {
  providerKey: string | null;
  models: ModelResource[];
  onSelectProvider: (key: string) => void;
  onClose: () => void;
  onRefresh: () => void;
}) {
  const pc = providerKey ? PROVIDER_CONFIG[providerKey] : null;
  const providerModels = useMemo(() =>
    providerKey ? models.filter((m) => m.provider === providerKey) : [],
    [models, providerKey],
  );
  const [apiKey, setApiKey] = useState('');
  const [baseUrl, setBaseUrl] = useState('');

  const existingMaskedKey = providerKey ? providerModels.find((m) => m.api_key_masked)?.api_key_masked : null;

  useEffect(() => {
    if (providerKey) {
      setBaseUrl(PROVIDER_DEFAULT_BASE_URL[providerKey] || '');
      setApiKey('');
      // Fetch real API key for display
      api.get<{api_key: string}>(`/api/v1/models/provider/${providerKey}/key`)
        .then((data) => setApiKey(data.api_key))
        .catch(() => {}); // No key configured — stay empty
    } else {
      setApiKey('');
      setBaseUrl('');
    }
  }, [providerKey]);
  const [testConn, setTestConn] = useState<{open: boolean; loading: boolean; result: {success: boolean; message: string} | null}>({open: false, loading: false, result: null});
  const [showAddForm, setShowAddForm] = useState(false);
  const [savingKey, setSavingKey] = useState(false);
  const [saveKeyMsg, setSaveKeyMsg] = useState<string | null>(null);
  const [showFetchModal, setShowFetchModal] = useState(false);
  const [fetchingModels, setFetchingModels] = useState(false);
  const [fetchedModels, setFetchedModels] = useState<{value: string; label: string; isRegistered: boolean; selected: boolean}[]>([]);
  const [newModel, setNewModel] = useState({ model_name: '', display_name: '', context_window: '128000', rpm_limit: '60', tpm_limit: '100000' });
  const [editingModelId, setEditingModelId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState({ display_name: '', context_window: '', rpm_limit: '', tpm_limit: '', capabilities: '' });

  // Toast & confirm modal
  const [toast, setToast] = useState<{message: string; type: 'success' | 'error' | 'info'} | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<{modelId: string; modelName: string} | null>(null);
  const [deleting, setDeleting] = useState(false);

  const showToast = (message: string, type: 'success' | 'error' | 'info' = 'info') => {
    setToast({message, type});
    setTimeout(() => setToast(null), 3000);
  };

  // Initialize API key from first model
  // ── Provider selector (when no provider selected) ──
  if (!providerKey) {
    return (
      <>
        <div onClick={onClose} style={overlayStyle} />
        <div style={{ ...panelStyle, right: 0 }}>
          <div style={panelHeaderStyle}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <div style={{ width: 44, height: 44, borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20, background: 'var(--gold-bg)', border: '1px solid var(--gold-border)' }}>🧠</div>
              <div>
                <div style={{ fontSize: 18, fontWeight: 700 }}>选择供应商</div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 3 }}>选择一个供应商来配置模型</div>
              </div>
            </div>
            <button onClick={onClose} style={closeBtnStyle}>✕</button>
          </div>
          <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px' }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 12 }}>
              {Object.entries(PROVIDER_CONFIG).filter(([k]) => k !== 'test').map(([key, cfg]) => {
                const colorKey = getProviderColorKey(cfg.color);
                const modelCount = models.filter((m) => m.provider === key).length;
                return (
                  <div
                    key={key}
                    onClick={() => onSelectProvider(key)}
                    style={{
                      padding: 16, borderRadius: 12, cursor: 'pointer',
                      background: 'var(--bg-card)', border: '1px solid var(--border-subtle)',
                      display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8,
                      transition: 'all 0.15s',
                    }}
                    onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.borderColor = `var(--${colorKey}-border)`; }}
                    onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'var(--border-subtle)'; }}
                  >
                    <div style={{ fontSize: 28 }}>{cfg.icon}</div>
                    <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{cfg.label}</div>
                    <div style={{ fontSize: 11, color: 'var(--text-dim)' }}>{modelCount} 个模型</div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </>
    );
  }

  // ── API Key initialized ──
  return (
    <>
      <div onClick={onClose} style={overlayStyle} />
      <div style={{ ...panelStyle, right: 0, width: 520 }}>
        {/* Test connection modal */}
        {testConn.open && (
          <>
            <div onClick={() => setTestConn({open: false, loading: false, result: null})} style={{position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 200, backdropFilter: 'blur(4px)'}} />
            <div style={{position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%,-50%)', zIndex: 201, width: 400, background: 'var(--bg-base)', borderRadius: 16, border: '1px solid var(--border-subtle)', padding: 32, boxShadow: '0 24px 48px rgba(0,0,0,0.5)', textAlign: 'center'}}>
              <button onClick={() => setTestConn({open: false, loading: false, result: null})} style={{position: 'absolute', top: 16, right: 16, width: 28, height: 28, borderRadius: 6, border: '1px solid var(--border-medium)', background: 'var(--bg-card)', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 14}}>✕</button>
              {testConn.loading ? (
                <>
                  <div style={{fontSize: 36, marginBottom: 12}}>⏳</div>
                  <div style={{fontSize: 16, fontWeight: 600, color: 'var(--text-primary)'}}>正在测试连接...</div>
                  <div style={{fontSize: 12, color: 'var(--text-muted)', marginTop: 6}}>正在验证 {pc.label} API Key</div>
                </>
              ) : testConn.result?.success ? (
                <>
                  <div style={{fontSize: 48, marginBottom: 12}}>✅</div>
                  <div style={{fontSize: 16, fontWeight: 600, color: 'var(--green-400)'}}>连接成功</div>
                  <div style={{fontSize: 13, color: 'var(--text-secondary)', marginTop: 8, lineHeight: 1.5}}>{testConn.result.message}</div>
                </>
              ) : (
                <>
                  <div style={{fontSize: 48, marginBottom: 12}}>❌</div>
                  <div style={{fontSize: 16, fontWeight: 600, color: 'var(--red-400)'}}>连接失败</div>
                  <div style={{fontSize: 13, color: 'var(--text-secondary)', marginTop: 8, lineHeight: 1.5, wordBreak: 'break-all'}}>{testConn.result?.message}</div>
                </>
              )}
            </div>
          </>
        )}

        {/* Fetch models checklist modal */}
        {showFetchModal && (
          <>
            <div onClick={() => setShowFetchModal(false)} style={{position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 200, backdropFilter: 'blur(4px)'}} />
            <div style={{position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%,-50%)', zIndex: 201, width: 480, maxHeight: '80vh', background: 'var(--bg-base)', borderRadius: 16, border: '1px solid var(--border-subtle)', padding: 24, boxShadow: '0 24px 48px rgba(0,0,0,0.5)', overflowY: 'auto'}}>
              <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16}}>
                <div style={{fontSize: 16, fontWeight: 600}}>发现 {fetchedModels.length} 个模型</div>
                <button onClick={() => setShowFetchModal(false)} style={{width: 28, height: 28, borderRadius: 6, border: '1px solid var(--border-medium)', background: 'var(--bg-card)', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 14}}>✕</button>
              </div>
              {fetchedModels.length === 0 ? (
                <div style={{textAlign: 'center', padding: 24, color: 'var(--text-dim)', fontSize: 13}}>未获取到模型</div>
              ) : (
                <div style={{display: 'flex', flexDirection: 'column', gap: 4, marginBottom: 16}}>
                  {fetchedModels.map((m) => (
                    <label key={m.value} style={{
                      display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px', borderRadius: 8,
                      background: m.isRegistered ? 'var(--bg-card)' : 'transparent',
                      opacity: m.isRegistered ? 0.6 : 1, cursor: m.isRegistered ? 'default' : 'pointer',
                    }}>
                      <input
                        type="checkbox"
                        checked={m.isRegistered || m.selected}
                        disabled={m.isRegistered}
                        style={{width: 16, height: 16, accentColor: 'var(--green-400)'}}
                        onChange={() => {
                          setFetchedModels((prev) => prev.map((f) => f.value === m.value ? {...f, selected: !f.selected} : f));
                        }}
                      />
                      <span style={{fontSize: 13, color: 'var(--text-primary)'}}>{m.label}</span>
                      {m.isRegistered && <span style={{fontSize: 10, color: 'var(--text-dim)', marginLeft: 'auto'}}>已注册</span>}
                    </label>
                  ))}
                </div>
              )}
              <div style={{display: 'flex', gap: 8, justifyContent: 'flex-end'}}>
                <button className="btn-secondary" style={btnSecondaryStyle} onClick={() => setShowFetchModal(false)}>取消</button>
                <button
                  className="btn-primary"
                  style={btnPrimaryStyle}
                  onClick={async () => {
                    const toAdd = fetchedModels.filter((m) => m.selected);
                    if (toAdd.length === 0) { setShowFetchModal(false); return; }
                    const results = await Promise.allSettled(toAdd.map((m) =>
                      api.post('/api/v1/models', {
                        provider: providerKey,
                        model_name: m.value,
                        display_name: m.label,
                        context_window: 128000,
                        rpm_limit: 60,
                        tpm_limit: 100000,
                        api_key_ref: apiKey || undefined,
                      })
                    ));
                    const succeeded = results.filter((r) => r.status === 'fulfilled').length;
                    const failed = results.filter((r) => r.status === 'rejected').length;
                    setShowFetchModal(false);
                    if (failed > 0) showToast(`已添加 ${succeeded} 个模型，${failed} 个失败`, failed > 0 ? 'error' : 'success');
                    else showToast(`已添加 ${succeeded} 个模型`, 'success');
                    onRefresh();
                  }}
                >
                  添加选中模型
                </button>
              </div>
            </div>
          </>
        )}

        {/* Header */}
        <div style={panelHeaderStyle}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{ ...iconStyle, background: `var(--${getProviderColorKey(pc.color)}-bg)`, border: `1px solid var(--${getProviderColorKey(pc.color)}-border)`, fontSize: 20 }}>
              {pc.icon}
            </div>
            <div>
              <div style={{ fontSize: 18, fontWeight: 700 }}>{pc.label}</div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 3 }}>{providerModels.length} 个模型已注册</div>
            </div>
          </div>
          <button onClick={onClose} style={closeBtnStyle}>✕</button>
        </div>

        {/* Body */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px' }}>
          {/* API Configuration */}
          <div style={{ marginBottom: 24 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 10 }}>API 配置</div>
            <div style={{ marginBottom: 10 }}>
              <label style={formLabelStyle}>API Key</label>
              <div style={{ display: 'flex', gap: 8 }}>
                <input
                  style={formInputStyle}
                  type="password"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder={existingMaskedKey ? '输入新 Key 替换现有配置' : '请输入 API Key — 用于测试连接和获取模型列表'}
                />
              </div>
              {existingMaskedKey && (
                <div style={{ fontSize: 10, color: 'var(--text-dim)', marginTop: 4 }}>
                  当前已配置 Key：{existingMaskedKey}
                </div>
              )}
            </div>
            <div style={{ marginBottom: 10 }}>
              <label style={formLabelStyle}>Base URL</label>
              <input
                style={formInputStyle}
                type="text"
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder="https://api.example.com/v1"
              />
            </div>
            <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
              <button
                className="btn-primary"
                style={{ ...btnPrimaryStyle, fontSize: 12 }}
                onClick={async () => {
                  if (!apiKey) { showToast('请先输入 API Key', 'error'); return; }
                  setTestConn({open: true, loading: true, result: null});
                  try {
                    const result = await api.post<{models: {id: string}[]}>('/api/v1/models/fetch-provider-models', {
                      provider: providerKey,
                      api_key: apiKey,
                      base_url: baseUrl || undefined,
                    });
                    setTestConn({open: true, loading: false, result: {
                      success: true,
                      message: `连接成功 — 获取到 ${result.models?.length || 0} 个模型`,
                    }});
                  } catch (e: any) {
                    setTestConn({open: true, loading: false, result: {
                      success: false,
                      message: `连接失败 — ${typeof e === 'string' ? e : (e?.detail || e?.message || String(e))}`,
                    }});
                  }
                }}
              >
                测试连接
              </button>
              <button
                className="btn-secondary"
                style={{ ...btnSecondaryStyle, fontSize: 12 }}
                disabled={savingKey}
                onClick={async () => {
                  if (!apiKey) return;
                  setSavingKey(true);
                  setSaveKeyMsg(null);
                  try {
                    if (providerModels.length > 0) {
                      await api.put('/api/v1/models/provider/key', { provider: providerKey, api_key_ref: apiKey });
                      onRefresh();
                      setSaveKeyMsg('已同步到全部模型');
                    } else {
                      setSaveKeyMsg('Key 已就绪，添加模型时将自动使用');
                    }
                  } catch (e) {
                    setSaveKeyMsg('保存失败: ' + String(e));
                  } finally {
                    setSavingKey(false);
                    setTimeout(() => setSaveKeyMsg(null), 3000);
                  }
                }}
              >
                {savingKey ? '保存中...' : '保存 API Key'}
              </button>
              {saveKeyMsg && (
                <div style={{ fontSize: 11, color: 'var(--green-400)', marginTop: 6 }}>{saveKeyMsg}</div>
              )}
            </div>
          </div>

          {/* Models */}
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 10 }}>
              已注册模型 ({providerModels.length})
            </div>
            {providerModels.length === 0 ? (
              <div style={{ padding: 24, textAlign: 'center', color: 'var(--text-dim)', fontSize: 13, background: 'var(--bg-card)', borderRadius: 10, border: '1px dashed var(--border-medium)' }}>
                暂无模型
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {providerModels.map((m) => (
                  <div key={m.id}>
                    <div
                      style={{
                        padding: '10px 12px', borderRadius: 8, background: 'var(--bg-card)',
                        border: `1px solid ${editingModelId === m.id ? 'var(--green-border)' : 'var(--border-subtle)'}`,
                        cursor: 'pointer', transition: 'all 0.15s',
                      }}
                      onClick={() => {
                        if (editingModelId === m.id) {
                          setEditingModelId(null);
                        } else {
                          setEditingModelId(m.id);
                          setEditForm({
                            display_name: m.name || '',
                            context_window: String(m.context_window || 128000),
                            rpm_limit: '',
                            tpm_limit: '',
                            capabilities: (m.capabilities || []).join(', '),
                          });
                        }
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div>
                          <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)' }}>{m.name}</div>
                          <div style={{ fontSize: 11, color: 'var(--text-dim)', fontFamily: 'var(--font-mono)', marginTop: 2 }}>
                            {m.model_name} · {formatContextWindow(m.context_window)}
                          </div>
                        </div>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setConfirmDelete({ modelId: m.id, modelName: m.name });
                          }}
                          style={{
                            width: 28, height: 28, borderRadius: 6, border: '1px solid var(--border-medium)',
                            background: 'transparent', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 12,
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                          }}
                          title="删除模型"
                        >
                          🗑
                        </button>
                      </div>
                    </div>
                    {/* Inline edit form */}
                    {editingModelId === m.id && (
                      <div style={{
                        padding: '12px 14px', marginTop: 2, borderRadius: 8,
                        background: 'var(--bg-elevated)', border: '1px solid var(--green-border)',
                      }}>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                          <div>
                            <label style={formLabelStyle}>显示名称</label>
                            <input style={formInputStyle} value={editForm.display_name} onChange={(e) => setEditForm((prev) => ({...prev, display_name: e.target.value}))} />
                          </div>
                          <div>
                            <label style={formLabelStyle}>上下文窗口</label>
                            <input style={formInputStyle} value={editForm.context_window} onChange={(e) => setEditForm((prev) => ({...prev, context_window: e.target.value}))} />
                          </div>
                          <div>
                            <label style={formLabelStyle}>RPM 限制</label>
                            <input style={formInputStyle} value={editForm.rpm_limit} placeholder="60" onChange={(e) => setEditForm((prev) => ({...prev, rpm_limit: e.target.value}))} />
                          </div>
                          <div>
                            <label style={formLabelStyle}>TPM 限制</label>
                            <input style={formInputStyle} value={editForm.tpm_limit} placeholder="100000" onChange={(e) => setEditForm((prev) => ({...prev, tpm_limit: e.target.value}))} />
                          </div>
                        </div>
                        <div style={{ marginTop: 8 }}>
                          <label style={formLabelStyle}>Capabilities (逗号分隔)</label>
                          <input style={formInputStyle} value={editForm.capabilities} onChange={(e) => setEditForm((prev) => ({...prev, capabilities: e.target.value}))} />
                        </div>
                        <div style={{ display: 'flex', gap: 8, marginTop: 10, justifyContent: 'flex-end' }}>
                          <button className="btn-secondary" style={{ ...btnSecondaryStyle, fontSize: 11 }}
                            onClick={(e) => { e.stopPropagation(); setEditingModelId(null); }}
                          >取消</button>
                          <button className="btn-primary" style={{ ...btnPrimaryStyle, fontSize: 11 }}
                            onClick={async (e) => {
                              e.stopPropagation();
                              try {
                                await api.put(`/api/v1/models/${m.id}`, {
                                  display_name: editForm.display_name || undefined,
                                  context_window: Number(editForm.context_window) || undefined,
                                  rpm_limit: Number(editForm.rpm_limit) || undefined,
                                  tpm_limit: Number(editForm.tpm_limit) || undefined,
                                  capabilities: editForm.capabilities ? editForm.capabilities.split(',').map((s: string) => s.trim()).filter(Boolean) : undefined,
                                });
                                setEditingModelId(null);
                                onRefresh();
                              } catch (err) {
                                showToast('保存失败: ' + String(err), 'error');
                              }
                            }}
                          >保存</button>
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Action buttons */}
            <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
              <button className="btn-secondary" style={{ ...btnSecondaryStyle, fontSize: 12 }} onClick={() => setShowAddForm(!showAddForm)}>
                {showAddForm ? '取消' : '+ 手动添加'}
              </button>
              <button
                className="btn-secondary"
                style={{ ...btnSecondaryStyle, fontSize: 12 }}
                onClick={async () => {
                  if (!apiKey) { showToast('请先输入 API Key', 'error'); return; }
                  setFetchingModels(true);
                  try {
                    const data = await api.post<{models: {id: string; display_name: string}[]}>('/api/v1/models/fetch-provider-models', {
                      provider: providerKey,
                      api_key: apiKey,
                      base_url: baseUrl || undefined,
                    });
                    const registeredNames = new Set(providerModels.map((m) => m.model_name));
                    setFetchedModels((data.models || []).map((m: {id: string; display_name: string}) => ({
                      value: m.id,
                      label: m.display_name || m.id,
                      isRegistered: registeredNames.has(m.id),
                      selected: false,
                    })));
                    setShowFetchModal(true);
                  } catch (e: any) {
                    showToast(`获取模型列表失败: ${String(e)}`, 'error');
                  } finally {
                    setFetchingModels(false);
                  }
                }}
                disabled={fetchingModels}
              >
                {fetchingModels ? '获取中...' : '从 API 获取模型列表'}
              </button>
            </div>

            {/* Add model inline form */}
            {showAddForm && (
              <div style={{
                marginTop: 12, padding: 14, borderRadius: 10,
                background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)',
              }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 10 }}>手动添加模型</div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                  <div>
                    <label style={formLabelStyle}>Model Name *</label>
                    <input style={formInputStyle} value={newModel.model_name} onChange={(e) => {
                      const v = e.target.value;
                      setNewModel((prev) => ({
                        ...prev,
                        model_name: v,
                        display_name: prev.display_name || v,
                      }));
                    }} placeholder="模型标识" />
                  </div>
                  <div>
                    <label style={formLabelStyle}>显示名称</label>
                    <input style={formInputStyle} value={newModel.display_name} onChange={(e) => setNewModel((prev) => ({...prev, display_name: e.target.value}))} placeholder="显示名称" />
                  </div>
                  <div>
                    <label style={formLabelStyle}>上下文窗口</label>
                    <input style={formInputStyle} value={newModel.context_window} onChange={(e) => setNewModel((prev) => ({...prev, context_window: e.target.value}))} />
                  </div>
                  <div>
                    <label style={formLabelStyle}>RPM 限制</label>
                    <input style={formInputStyle} value={newModel.rpm_limit} onChange={(e) => setNewModel((prev) => ({...prev, rpm_limit: e.target.value}))} />
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 8, marginTop: 10, justifyContent: 'flex-end' }}>
                  <button className="btn-secondary" style={{ ...btnSecondaryStyle, fontSize: 11 }} onClick={() => setShowAddForm(false)}>取消</button>
                  <button className="btn-primary" style={{ ...btnPrimaryStyle, fontSize: 11 }}
                    onClick={async () => {
                      if (!newModel.model_name) { showToast('请输入 Model Name', 'error'); return; }
                      try {
                        await api.post('/api/v1/models', {
                          provider: providerKey,
                          model_name: newModel.model_name,
                          display_name: newModel.display_name || newModel.model_name,
                          context_window: Number(newModel.context_window) || 128000,
                          rpm_limit: Number(newModel.rpm_limit) || 60,
                          tpm_limit: Number(newModel.tpm_limit) || 100000,
                          api_key_ref: apiKey || undefined,
                        });
                        setNewModel({ model_name: '', display_name: '', context_window: '128000', rpm_limit: '60', tpm_limit: '100000' });
                        setShowAddForm(false);
                        onRefresh();
                        showToast('模型添加成功', 'success');
                      } catch (e) {
                        showToast('添加失败: ' + String(e), 'error');
                      }
                    }}
                  >添加</button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Confirm Delete Modal */}
      {confirmDelete && (
        <>
          <div onClick={() => setConfirmDelete(null)} style={{position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 200, backdropFilter: 'blur(4px)'}} />
          <div style={{position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%,-50%)', zIndex: 201, width: 380, background: 'var(--bg-base)', borderRadius: 16, border: '1px solid var(--border-subtle)', padding: 28, boxShadow: '0 24px 48px rgba(0,0,0,0.5)', textAlign: 'center'}}>
            <div style={{fontSize: 40, marginBottom: 12}}>⚠️</div>
            <div style={{fontSize: 15, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 6}}>确认删除</div>
            <div style={{fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6, marginBottom: 24}}>
              确定要删除模型「{confirmDelete.modelName}」吗？此操作不可撤销。
            </div>
            <div style={{display: 'flex', gap: 10, justifyContent: 'center'}}>
              <button
                onClick={() => setConfirmDelete(null)}
                style={{
                  padding: '8px 24px', borderRadius: 8, border: '1px solid var(--border-medium)',
                  background: 'var(--bg-card)', color: 'var(--text-secondary)', cursor: 'pointer', fontSize: 13,
                }}
              >取消</button>
              <button
                disabled={deleting}
                onClick={async () => {
                  setDeleting(true);
                  try {
                    await api.del(`/api/v1/models/${confirmDelete.modelId}`);
                    setConfirmDelete(null);
                    onRefresh();
                    showToast('模型已删除', 'success');
                  } catch (err: any) {
                    setConfirmDelete(null);
                    showToast('删除失败: ' + (err?.message || String(err)), 'error');
                  } finally {
                    setDeleting(false);
                  }
                }}
                style={{
                  padding: '8px 24px', borderRadius: 8, border: 'none',
                  background: 'var(--red-400)', color: '#fff', cursor: 'pointer', fontSize: 13, fontWeight: 600,
                }}
              >{deleting ? '删除中...' : '确认删除'}</button>
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
          fontSize: 13, fontWeight: 500,
          boxShadow: '0 8px 24px rgba(0,0,0,0.3)',
          animation: 'fadeIn 0.2s ease',
        }}>
          <span style={{marginRight: 8}}>
            {toast.type === 'success' ? '✓' : toast.type === 'error' ? '✗' : 'ℹ'}
          </span>
          {toast.message}
        </div>
      )}
    </>
  );
}

// ── Detail Panel ──

function DetailPanel({ type, mode, resource, onClose, onSwitchTab, onSaved }: {
  type: TabKey; mode: 'edit' | 'register';
  resource: Record<string, unknown> | null;
  onClose: () => void; onSwitchTab: (t: TabKey) => void;
  onSaved: () => void;
}) {
  const name = (resource?.name as string) || '';
  const desc = (resource?.description as string) || '';
  const iconText = TAB_CONFIG[type].icon;
  const colorClass = type === 'agents' || type === 'skills' ? 'gold' : type === 'tools' ? 'green' : type === 'personas' ? 'purple' : 'gold';

  const meta = REGISTER_LABELS[type].replace('+ ', '').split(' · ');
  const panelName = mode === 'register' ? (REGISTER_LABELS[type].replace('+ ', '')) : name;
  const panelDesc = mode === 'register' ? meta[meta.length - 1] || '' : desc;

  const [saving, setSaving] = useState(false);
  const [fetchingModels, setFetchingModels] = useState(false);
  const [fetchedModels, setFetchedModels] = useState<{value: string; label: string}[]>([]);
  const [testConn, setTestConn] = useState<{open: boolean; loading: boolean; result: {success: boolean; message: string} | null}>({open: false, loading: false, result: null});
  const [capabilityTags, setCapabilityTags] = useState<{id: string; name: string; key: string; category: string}[]>([]);
  const [selectedTags, setSelectedTags] = useState<Set<string>>(new Set(
    resource?.tags ? (resource?.tags as string[]) : []
  ));

  // Fetch capability tags when persona panel opens
  useEffect(() => {
    if (type === 'personas') {
      api.get<{id: string; name: string; key: string; category: string}[]>('/api/v1/capabilities')
        .then(setCapabilityTags)
        .catch(() => {});
    }
  }, [type]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const endpoints: Record<TabKey, string> = {
        models: '/api/v1/models',
        personas: '/api/v1/personas',
        tools: '/api/v1/tools',
        agents: '/api/v1/agents',
        skills: '/api/v1/skills',
      };
      let body: Record<string, unknown> = formData;
      if (type === 'models') {
        body = {
          provider: formData.provider,
          model_name: formData.model_name,
          display_name: formData.name,
          context_window: Number(formData.context_window) || 128000,
          rpm_limit: Number(formData.rpm_limit) || 60,
          tpm_limit: Number(formData.tpm_limit) || 100000,
          api_key_ref: formData.api_key || undefined,
          capabilities: formData.capabilities ? formData.capabilities.split(',').map((s: string) => s.trim()).filter(Boolean) : [],
        };
      } else if (type === 'personas') {
        const capsStr = formData.capabilities || '';
        const capsObj: Record<string, number> = {};
        if (capsStr) {
          for (const cap of capsStr.split(',')) {
            const [k, v] = cap.trim().split(':').map((s: string) => s.trim());
            if (k) capsObj[k] = parseFloat(v) || 0.5;
          }
        }
        body = {
          name: formData.name,
          role: formData.role || undefined,
          expertise: formData.expertise || undefined,
          constraints: formData.constraints || undefined,
          system_prompt: formData.system_prompt || undefined,
          prompt_template: formData.prompt_template || undefined,
          capabilities: Object.keys(capsObj).length > 0 ? capsObj : undefined,
          tags: Array.from(selectedTags),
          tools_declared: formData.tools_declared ? formData.tools_declared.split(',').map((s: string) => s.trim()).filter(Boolean) : undefined,
          output_prefs: undefined,
          temperature: formData.temperature ? Number(formData.temperature) : undefined,
          max_tokens: formData.max_tokens ? Number(formData.max_tokens) : undefined,
          top_p: formData.top_p ? Number(formData.top_p) : undefined,
        };
      }
      if (mode === 'register') {
        await api.post(endpoints[type], body);
      } else if (resource?.id) {
        await api.put(`${endpoints[type]}/${resource.id}`, body);
      }
      onSaved();
      onClose();
    } catch (e) {
      alert('保存失败: ' + String(e));
    } finally {
      setSaving(false);
    }
  };

  const [formData, setFormData] = useState<Record<string, string>>({
    name: name, description: desc,
    provider: (resource?.provider as string) || '',
    model_name: (resource?.model_name as string) || '',
    api_key: (resource?.api_key_ref as string) || '',
    api_endpoint: (resource?.api_endpoint as string) || '',
    system_prompt: (resource?.system_prompt as string) || '',
    system_prompt_template: (resource?.system_prompt_template as string) || '',
    role: (resource?.role as string) || '',
    expertise: (resource?.expertise as string) || '',
    constraints: (resource?.constraints as string) || '',
    prompt_template: (resource?.prompt_template as string) || '',
    tags: Array.isArray(resource?.tags) ? (resource?.tags as string[]).join(', ') : '',
    tools_declared: Array.isArray(resource?.tools_declared) ? (resource?.tools_declared as string[]).join(', ') : '',
    temperature: (resource?.temperature as string) || '0.7',
    max_tokens: (resource?.max_tokens as string) || '4096',
    top_p: (resource?.top_p as string) || '1.0',
    tool_type: (resource?.tool_type as string) || '',
    connection_url: (resource?.connection_url as string) || '',
    persona_id: (resource?.persona_id as string) || '',
    default_model_id: (resource?.default_model_id as string) || '',
    file_path: (resource?.file_path as string) || '',
    trigger_condition: (resource?.trigger_condition as string) || '',
    context_window: (resource?.context_window as string) || '',
    rpm_limit: (resource?.rpm_limit as string) || '',
    tpm_limit: (resource?.tpm_limit as string) || '',
    capabilities: Array.isArray(resource?.capabilities) ? (resource?.capabilities as string[]).join(', ') : '',
  });

  const updateField = (field: string, value: string) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
  };

  return (
    <>
      <div onClick={onClose} style={overlayStyle} />
      <div style={{ ...panelStyle, right: 0 }}>
        {/* Header */}
        <div style={panelHeaderStyle}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{
              width: 44, height: 44, borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 20, background: `var(--${colorClass}-bg)`, border: `1px solid var(--${colorClass}-border)`,
            }}>
              {iconText}
            </div>
            <div>
              <div style={{ fontSize: 18, fontWeight: 700 }}>{panelName}</div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 3 }}>{panelDesc}</div>
            </div>
          </div>
          <button onClick={onClose} style={closeBtnStyle}>✕</button>
        </div>

        {/* Relation chain */}
        <PanelRelationChain type={type} onSwitch={onSwitchTab} onClose={onClose} />

        {/* Body */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px' }}>
          {renderPanelForm(type, formData, updateField, {fetchingModels, setFetchingModels, fetchedModels, setFetchedModels, testConn, setTestConn, capabilityTags, selectedTags, setSelectedTags})}
        </div>

        {/* Footer */}
        <div style={panelFooterStyle}>
          <button className="btn-secondary" style={btnSecondaryStyle} onClick={() => setFormData({ name: '', description: '', provider: '', model_name: '', api_key: '', api_endpoint: '', system_prompt: '', system_prompt_template: '', role: '', expertise: '', constraints: '', prompt_template: '', tags: '', tools_declared: '', temperature: '0.7', max_tokens: '4096', top_p: '1.0', tool_type: '', connection_url: '', persona_id: '', default_model_id: '', file_path: '', trigger_condition: '', context_window: '', rpm_limit: '', tpm_limit: '', capabilities: '' })}>重置</button>
          <button className="btn-primary" style={btnPrimaryStyle} onClick={handleSave} disabled={saving}>
            {saving ? '保存中...' : '保存'}
          </button>
        </div>
      </div>
    </>
  );
}

function PanelRelationChain({ type, onSwitch, onClose }: {
  type: TabKey; onSwitch: (t: TabKey) => void; onClose: () => void;
}) {
  const items: { key: TabKey; label: string; icon: string }[] = [
    { key: 'models', label: '模型', icon: '🧠' },
    { key: 'tools', label: '工具', icon: '🔧' },
    { key: 'skills', label: 'Skill', icon: '📐' },
    { key: 'personas', label: 'Persona', icon: '🎭' },
    { key: 'agents', label: 'Agent', icon: '🤖' },
  ];

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '12px 24px', borderBottom: '1px solid var(--border-subtle)', background: 'var(--bg-card)', fontSize: 11 }}>
      {items.map((item, i) => (
        <span key={item.key} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <span
            onClick={() => { onSwitch(item.key); onClose(); }}
            style={{
              padding: '3px 8px', borderRadius: 4, cursor: 'pointer', transition: 'all 0.15s',
              color: item.key === type ? 'var(--green-400)' : 'var(--text-dim)',
              fontWeight: item.key === type ? 600 : 400,
            }}
          >
            {item.icon} {item.label}
          </span>
          {i < items.length - 1 && (
            <span style={{ color: 'var(--text-dim)', fontSize: 9 }}>→</span>
          )}
        </span>
      ))}
    </div>
  );
}

function renderPanelForm(
  type: TabKey, formData: Record<string, string>,
  updateField: (field: string, value: string) => void,
  extra: {
    fetchingModels: boolean; setFetchingModels: (v: boolean) => void;
    fetchedModels: {value: string; label: string}[];
    setFetchedModels: (v: {value: string; label: string}[]) => void;
    testConn: {open: boolean; loading: boolean; result: {success: boolean; message: string} | null};
    setTestConn: (v: {open: boolean; loading: boolean; result: {success: boolean; message: string} | null}) => void;
    capabilityTags: {id: string; name: string; key: string; category: string}[];
    selectedTags: Set<string>;
    setSelectedTags: React.Dispatch<React.SetStateAction<Set<string>>>;
  },
) {
  const Input = ({ label, field, placeholder, isPassword, isTextarea }: {
    label: string; field: string; placeholder?: string; isPassword?: boolean; isTextarea?: boolean;
  }) => (
    <div style={{ marginBottom: 14 }}>
      <label style={formLabelStyle}>{label}</label>
      {isTextarea ? (
        <textarea
          style={{ ...formInputStyle, minHeight: 80, resize: 'vertical' as const, fontFamily: 'var(--font-mono)', fontSize: 12 }}
          value={formData[field] || ''}
          onChange={(e) => updateField(field, e.target.value)}
          placeholder={placeholder}
        />
      ) : (
        <input
          style={formInputStyle}
          type={isPassword ? 'password' : 'text'}
          value={formData[field] || ''}
          onChange={(e) => updateField(field, e.target.value)}
          placeholder={placeholder}
        />
      )}
    </div>
  );

  const Select = ({ label, field, options }: { label: string; field: string; options: (string | {value: string; label: string})[] }) => (
    <div style={{ marginBottom: 14 }}>
      <label style={formLabelStyle}>{label}</label>
      <select
        style={{ ...formInputStyle, cursor: 'pointer' } as React.CSSProperties}
        value={formData[field] || (typeof options[0] === 'string' ? options[0] : (options[0] as {value: string}).value)}
        onChange={(e) => updateField(field, e.target.value)}
      >
        {options.map((o) => {
          const val = typeof o === 'string' ? o : o.value;
          const lbl = typeof o === 'string' ? o : o.label;
          return <option key={val} value={val}>{lbl}</option>;
        })}
      </select>
    </div>
  );

  const SectionTitle = ({ children }: { children: React.ReactNode }) => (
    <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 10, marginTop: 22, display: 'flex', alignItems: 'center', gap: 6 }}>
      {children}
    </div>
  );

  switch (type) {
    case 'models': {
      const provider = formData.provider || '';
      const staticModels = PROVIDER_MODELS[provider] || [];
      const modelOptions = extra.fetchedModels.length > 0 ? extra.fetchedModels : staticModels;

      const handleFetchModels = async () => {
        const apiKey = formData.api_key || '';
        if (!provider) { alert('请先选择 Provider'); return; }
        if (!apiKey) { showToast('请先输入 API Key', 'error'); return; }
        extra.setFetchingModels(true);
        try {
          const data = await api.post<{models: {id: string; display_name: string}[]}>('/api/v1/models/fetch-provider-models', {
            provider,
            api_key: apiKey,
          });
          const models = (data.models || []).map((m: {id: string; display_name: string}) => ({
            value: m.id,
            label: m.display_name || m.id,
          }));
          extra.setFetchedModels(models);
          if (models.length === 0) {
            alert('该供应商未返回任何模型');
          }
        } catch (e: any) {
          // Fallback to static list
          if (staticModels.length > 0) {
            extra.setFetchedModels(staticModels);
            alert(`动态获取失败，已加载预设模型列表: ${String(e)}`);
          } else {
            alert(`获取模型列表失败: ${String(e)}`);
          }
        } finally {
          extra.setFetchingModels(false);
        }
      };

      const handleTestConnection = async () => {
        const name = formData.name || '';
        const modelName = formData.model_name || '';
        if (!name || !provider || !modelName) { alert('请先填写模型名称、Provider 和 Model Name'); return; }
        extra.setTestConn({open: true, loading: true, result: null});
        try {
          // Save model first
          const created = await api.post<{id: string}>('/api/v1/models', {
            provider,
            model_name: modelName,
            display_name: name,
            context_window: Number(formData.context_window) || 128000,
            rpm_limit: Number(formData.rpm_limit) || 60,
            tpm_limit: Number(formData.tpm_limit) || 100000,
            api_key_ref: formData.api_key || undefined,
            capabilities: formData.capabilities ? formData.capabilities.split(',').map((s: string) => s.trim()).filter(Boolean) : [],
          });
          // Then test
          const result = await api.post<{connected: boolean; error?: string}>(`/api/v1/models/${created.id}/test`);
          extra.setTestConn({open: true, loading: false, result: {
            success: result.connected,
            message: result.connected
              ? `连接成功 — ${provider}/${modelName}`
              : `连接失败 — ${result.error || '未知错误'}`,
          }});
        } catch (e: any) {
          const msg = typeof e === 'string' ? e : (e?.detail || e?.message || String(e));
          extra.setTestConn({open: true, loading: false, result: {success: false, message: `连接失败 — ${msg}`}});
        }
      };

      return (
        <>
          {/* Test connection modal */}
          {extra.testConn.open && (
            <>
              <div onClick={() => extra.setTestConn({open: false, loading: false, result: null})} style={{position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 200, backdropFilter: 'blur(4px)'}} />
              <div style={{position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%,-50%)', zIndex: 201, width: 400, background: 'var(--bg-base)', borderRadius: 16, border: '1px solid var(--border-subtle)', padding: 32, boxShadow: '0 24px 48px rgba(0,0,0,0.5)', textAlign: 'center'}}>
                <button onClick={() => extra.setTestConn({open: false, loading: false, result: null})} style={{position: 'absolute', top: 16, right: 16, width: 28, height: 28, borderRadius: 6, border: '1px solid var(--border-medium)', background: 'var(--bg-card)', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 14}}>✕</button>
                {extra.testConn.loading ? (
                  <>
                    <div style={{fontSize: 36, marginBottom: 12}}>⏳</div>
                    <div style={{fontSize: 16, fontWeight: 600, color: 'var(--text-primary)'}}>正在测试连接...</div>
                    <div style={{fontSize: 12, color: 'var(--text-muted)', marginTop: 6}}>正在验证 {provider}/{formData.model_name || '...'}</div>
                  </>
                ) : extra.testConn.result?.success ? (
                  <>
                    <div style={{fontSize: 48, marginBottom: 12}}>✅</div>
                    <div style={{fontSize: 16, fontWeight: 600, color: 'var(--green-400)'}}>连接成功</div>
                    <div style={{fontSize: 13, color: 'var(--text-secondary)', marginTop: 8, lineHeight: 1.5}}>{extra.testConn.result.message}</div>
                  </>
                ) : (
                  <>
                    <div style={{fontSize: 48, marginBottom: 12}}>❌</div>
                    <div style={{fontSize: 16, fontWeight: 600, color: 'var(--red-400)'}}>连接失败</div>
                    <div style={{fontSize: 13, color: 'var(--text-secondary)', marginTop: 8, lineHeight: 1.5, wordBreak: 'break-all'}}>{extra.testConn.result?.message}</div>
                  </>
                )}
              </div>
            </>
          )}

          <SectionTitle>模型配置</SectionTitle>
          <Select label="Provider" field="provider" options={PROVIDER_OPTIONS} />
          <Input label="模型名称" field="name" placeholder="显示名称，如 DeepSeek V4 Pro" />
          <div style={{marginBottom: 14}}>
            <label style={formLabelStyle}>Model Name</label>
            <div style={{display: 'flex', gap: 8}}>
              <select
                style={{...formInputStyle, cursor: 'pointer', flex: 1}}
                value={formData.model_name || ''}
                onChange={(e) => updateField('model_name', e.target.value)}
              >
                <option value="">{modelOptions.length > 0 ? '— 选择模型版本 —' : provider ? '— 输入 API Key 后点击获取 —' : '— 请先选择 Provider —'}</option>
                {modelOptions.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
              </select>
              <button
                className="btn-primary"
                style={{...btnPrimaryStyle, whiteSpace: 'nowrap', fontSize: 11, padding: '8px 12px'}}
                onClick={handleFetchModels}
                disabled={extra.fetchingModels || !provider}
              >
                {extra.fetchingModels ? '获取中...' : '获取模型列表'}
              </button>
            </div>
            <div style={{fontSize: 10, color: 'var(--text-dim)', marginTop: 4}}>
              也可直接输入 model_name（下拉选项为预设 + 动态获取的模型）
            </div>
          </div>
          <Input label="API Key" field="api_key" isPassword placeholder="sk-***" />
          <SectionTitle>参数</SectionTitle>
          <Input label="最大上下文" field="context_window" placeholder="128000" />
          <Input label="RPM 限制" field="rpm_limit" placeholder="60" />
          <Input label="TPM 限制" field="tpm_limit" placeholder="100000" />
          <div style={{marginTop: 12, display: 'flex', gap: 8}}>
            <button className="btn-primary" style={btnPrimaryStyle} onClick={handleTestConnection}>测试连接</button>
          </div>
        </>
      );
    }
    case 'personas':
      return (
        <>
          <SectionTitle>角色定义</SectionTitle>
          <Input label="角色名称" field="name" />
          <Input label="角色身份" field="role" isTextarea placeholder="你是一位资深软件架构师，拥有15年企业级系统设计经验..." />
          <Input label="核心能力" field="expertise" isTextarea placeholder={"核心能力：\n- 系统架构设计：微服务、事件驱动、DDD\n- 技术选型评估：框架对比、ROI分析\n- 需求分析：用户故事映射、事件风暴"} />
          <Input label="行为边界" field="constraints" isTextarea placeholder={"行为边界：\n- 不做具体代码实现\n- 方案必须包含trade-off分析\n- 始终关注安全性和可扩展性"} />
          <Input label="系统提示词" field="system_prompt" isTextarea placeholder="你是一位高级软件架构师，擅长系统架构设计。输出格式：先给出架构概览，再逐层分析。" />
          <Input label="提示词模板" field="prompt_template" isTextarea placeholder={'# 角色身份\n{role}\n\n# 核心能力\n{expertise}\n\n# 行为边界\n{constraints}\n\n# 任务\n{task}'} />
          <div style={{ fontSize: 11, color: 'var(--text-dim)', marginBottom: 14 }}>使用 {'{'}role{'}'}, {'{'}expertise{'}'}, {'{'}constraints{'}'}, {'{'}task{'}'} 等变量，Agent 运行时替换</div>

          <SectionTitle>能力标签</SectionTitle>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 14 }}>
            {extra.capabilityTags.map((tag) => {
              const isSelected = extra.selectedTags.has(tag.name);
              const catColor = tag.category === 'technical' ? 'var(--blue-400)' : tag.category === 'soft' ? 'var(--green-400)' : 'var(--gold-400)';
              return (
                <div
                  key={tag.key}
                  onClick={() => {
                    extra.setSelectedTags((prev) => {
                      const next = new Set(prev);
                      if (isSelected) next.delete(tag.name);
                      else next.add(tag.name);
                      return next;
                    });
                  }}
                  style={{
                    padding: '4px 10px', borderRadius: 6, cursor: 'pointer',
                    fontSize: 11, fontWeight: 500,
                    background: isSelected ? catColor : 'var(--bg-card)',
                    color: isSelected ? '#fff' : 'var(--text-dim)',
                    border: `1px solid ${isSelected ? catColor : 'var(--border-medium)'}`,
                    transition: 'all 0.15s ease',
                  }}
                >
                  {tag.name}
                </div>
              );
            })}
          </div>
          <div style={{ fontSize: 10, color: 'var(--text-dim)', marginTop: -8, marginBottom: 14 }}>
            点击标签选择角色能力维度 · 蓝色=技术 · 绿色=软技能 · 金色=领域
          </div>

          <SectionTitle>工具声明</SectionTitle>
          <Input label="声明的工具" field="tools_declared" placeholder="file-read, file-write, terminal (逗号分隔)" />
          <div style={{ fontSize: 10, color: 'var(--text-dim)', marginTop: -8, marginBottom: 14 }}>
            该角色可使用的工具列表，逗号分隔
          </div>

          <SectionTitle>模型参数</SectionTitle>
          <div style={{ marginBottom: 14 }}>
            <label style={formLabelStyle}>Temperature · {formData.temperature || '0.7'}</label>
            <input
              type="range" min="0" max="2" step="0.1"
              value={formData.temperature || '0.7'}
              onChange={(e) => updateField('temperature', e.target.value)}
              style={{ width: '100%', marginTop: 4, accentColor: 'var(--gold-400)' }}
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: 'var(--text-dim)' }}>
              <span>0 — 精确</span><span>2 — 创造</span>
            </div>
          </div>
          <Input label="Max Tokens" field="max_tokens" placeholder="4096" />
          <div style={{ marginBottom: 14 }}>
            <label style={formLabelStyle}>Top P · {formData.top_p || '1.0'}</label>
            <input
              type="range" min="0" max="1" step="0.05"
              value={formData.top_p || '1.0'}
              onChange={(e) => updateField('top_p', e.target.value)}
              style={{ width: '100%', marginTop: 4, accentColor: 'var(--gold-400)' }}
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: 'var(--text-dim)' }}>
              <span>0 — 窄</span><span>1 — 宽</span>
            </div>
          </div>
        </>
      );
    case 'tools':
      return (
        <>
          <SectionTitle>工具配置</SectionTitle>
          <Input label="名称" field="name" />
          <Select label="类型" field="tool_type" options={['MCP Server', 'REST API', '内置函数']} />
          <Input label="连接地址" field="connection_url" placeholder="mcp://localhost:3000/tool" />
          <SectionTitle>权限</SectionTitle>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            {['读', '写', '执行', '网络'].map((perm) => (
              <div key={perm} style={capItemStyle}>
                <span style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-secondary)' }}>{perm}</span>
                <div style={{ ...toggleStyle, background: perm !== '网络' ? 'var(--green-400)' : 'var(--border-medium)' }}>
                  <div style={{ ...toggleDotStyle, left: perm !== '网络' ? 18 : 2 }} />
                </div>
              </div>
            ))}
          </div>
        </>
      );
    case 'agents':
      return (
        <>
          <SectionTitle>Agent 组合 · Persona + Model + Tools</SectionTitle>
          <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', borderRadius: 10, padding: 14, marginBottom: 14 }}>
            <div style={{ fontSize: 11, color: 'var(--text-dim)', marginBottom: 10 }}>
              组合公式：Agent = Persona + 默认 Model + Tools（运行时可覆盖模型）
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <span style={compChipStyle('purple')}>🎭 Persona</span>
              <span style={{ color: 'var(--text-dim)' }}>+</span>
              <span style={compChipStyle('gold')}>🧠 Model</span>
              <span style={{ color: 'var(--text-dim)' }}>+</span>
              <span style={compChipStyle('green')}>🔧 Tools</span>
              <span style={{ color: 'var(--text-dim)' }}>=</span>
              <span style={{ ...compChipStyle('green'), fontWeight: 600 }}>🤖 Agent</span>
            </div>
          </div>
          <Input label="Agent 名称" field="name" />
          <Select label="绑定 Persona" field="persona_id" options={['🏗 架构师', '💻 编码工程师', '🔍 审查员', '🚀 集成工程师', '🔬 研究员', '📖 内容写手']} />
          <Select label="默认模型" field="default_model_id" options={['Gemini 2.5 Pro', 'GLM 5.1', 'Claude Sonnet 4.6']} />
          <div style={{ fontSize: 10, color: 'var(--text-dim)', marginTop: -8, marginBottom: 14 }}>
            运行时可在团队 SOP / 任务节点中覆盖此模型，按复杂度路由不同模型
          </div>
          <Input label="绑定工具" field="tools" placeholder="Filesystem, Git" />
          <SectionTitle>系统提示词（继承 Persona，可覆盖）</SectionTitle>
          <Input label="提示词" field="system_prompt" isTextarea placeholder="你是一个资深的软件架构师 Agent..." />
          <SectionTitle>分配团队</SectionTitle>
          <Select label="团队" field="team_id" options={['核心开发团队', '研究分析团队', '内容创作团队', '暂不分配']} />
          <div style={{ background: 'var(--blue-bg)', border: '1px solid var(--blue-border)', borderRadius: 8, padding: '10px 14px', fontSize: 11, color: 'var(--blue-400)', marginTop: 8 }}>
            模型路由：此处设置的默认模型可在执行时被覆盖。SOP 工作流节点、团队编排均可按任务复杂度动态切换模型
          </div>
        </>
      );
    case 'skills':
      const slug = (formData.name || 'skill').toLowerCase().replace(/ /g, '-');
      return (
        <>
          <SectionTitle>上传 Skill 文件</SectionTitle>
          <div style={{ fontSize: 10, color: 'var(--text-dim)', marginBottom: 10 }}>
            上传 SKILL.md 文件或包含 SKILL.md 的 .zip 目录。系统会自动解析并填充下方表单。
          </div>
          <div style={{ border: '2px dashed var(--border-medium)', borderRadius: 10, padding: 24, textAlign: 'center', marginBottom: 16, cursor: 'pointer', background: 'var(--bg-card)' }}>
            <div style={{ fontSize: 28, marginBottom: 8, opacity: 0.4 }}>📁</div>
            <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 4 }}>拖放文件到此处，或点击选择</div>
            <div style={{ fontSize: 11, color: 'var(--text-dim)' }}>支持 SKILL.md · config.yaml · .zip 目录包 · templates/*</div>
          </div>
          <SectionTitle>Skill 基本信息</SectionTitle>
          <div style={{ fontSize: 10, color: 'var(--text-dim)', marginBottom: 10 }}>
            Skill 是一个自包含的文件目录。不绑定 Agent 或策略——由 SOP 工作流按需加载。
          </div>
          <Input label="名称" field="name" />
          <Input label="目录路径" field="file_path" placeholder={`skills/${slug}/`} />
          <SectionTitle>目录结构</SectionTitle>
          <div style={{ background: '#0d1117', border: '1px solid rgba(148,163,184,0.1)', borderRadius: 8, padding: 12, fontFamily: 'var(--font-mono)', fontSize: 11, color: '#c9d1d9', lineHeight: 1.8, marginBottom: 16 }}>
            <div>skills/{slug}/</div>
            <div style={{ paddingLeft: 16 }}>├── SKILL.md <span style={{ color: 'var(--text-dim)' }}># 主定义文件</span></div>
            <div style={{ paddingLeft: 16 }}>├── config.yaml <span style={{ color: 'var(--text-dim)' }}># 触发条件 + 参数</span></div>
            <div style={{ paddingLeft: 16 }}>└── templates/ <span style={{ color: 'var(--text-dim)' }}># 提示词模板</span></div>
          </div>
          <SectionTitle>SKILL.md（主定义文件）</SectionTitle>
          <Input label="定义文件" field="skill_md" isTextarea placeholder={`---\nname: ${formData.name || 'skill-name'}\ndescription: ${formData.description || ''}\nversion: "1.0"\n---`} />
          <SectionTitle>触发配置 (config.yaml)</SectionTitle>
          <Input label="触发器" field="trigger_config" isTextarea placeholder={`name: ${formData.name || 'skill-name'}\ntrigger:\n  type: auto\n  condition: "node.status === 'completed'"`} />
          <div style={{ background: 'var(--blue-bg)', border: '1px solid var(--blue-border)', borderRadius: 8, padding: '10px 14px', fontSize: 11, color: 'var(--blue-400)' }}>
            Skill 不预绑 Agent。SOP 工作流节点触发时，由编排层决定加载哪个 Skill 并分配给当前步骤的执行 Agent
          </div>
        </>
      );
    default:
      return null;
  }
}

// ── Utility ──

function formatContextWindow(n?: number): string {
  if (!n) return '-';
  if (n >= 1000000) return `${(n / 1000000).toFixed(0)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(0)}K`;
  return String(n);
}

function compChipStyle(color: string): React.CSSProperties {
  const colors: Record<string, { bg: string; color: string; border: string }> = {
    purple: { bg: 'var(--purple-bg)', color: 'var(--purple-400)', border: 'var(--purple-border)' },
    gold: { bg: 'var(--gold-bg)', color: 'var(--gold-400)', border: 'var(--gold-border)' },
    green: { bg: 'var(--green-bg)', color: 'var(--green-400)', border: 'var(--green-border)' },
  };
  const c = colors[color] || colors.green;
  return {
    fontSize: 10, padding: '3px 8px', borderRadius: 4, fontWeight: 500,
    display: 'flex', alignItems: 'center', gap: 3,
    background: c.bg, color: c.color, border: `1px solid ${c.border}`,
  };
}

// ── Style constants ──

const btnPrimaryStyle: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 6, padding: '8px 16px',
  borderRadius: 8, fontFamily: 'var(--font-body)', fontSize: 13, fontWeight: 500,
  border: 'none', cursor: 'pointer', transition: 'all 0.15s',
  background: 'linear-gradient(135deg, var(--green-400), #059669)', color: '#0a0f1e',
};

const btnSecondaryStyle: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 6, padding: '8px 16px',
  borderRadius: 8, fontFamily: 'var(--font-body)', fontSize: 13, fontWeight: 500,
  cursor: 'pointer', transition: 'all 0.15s',
  background: 'var(--bg-card)', color: 'var(--text-secondary)',
  border: '1px solid var(--border-medium)',
};

const relationBarStyle: React.CSSProperties = {
  display: 'flex', alignItems: 'center', gap: 0, marginBottom: 20,
  background: 'var(--bg-card)', border: '1px solid var(--border-subtle)',
  borderRadius: 10, padding: '10px 16px', overflowX: 'auto',
};

const relationItemStyle: React.CSSProperties = {
  display: 'flex', alignItems: 'center', gap: 6, padding: '4px 10px',
  borderRadius: 6, fontSize: 11, fontWeight: 500, whiteSpace: 'nowrap',
  cursor: 'pointer', transition: 'all 0.15s',
};

const searchInputStyle: React.CSSProperties = {
  flex: 1, maxWidth: 320, background: 'var(--bg-card)', border: '1px solid var(--border-medium)',
  borderRadius: 8, padding: '7px 14px', fontSize: 12, color: 'var(--text-primary)',
  fontFamily: 'var(--font-body)', outline: 'none',
};

const filterSelectStyle: React.CSSProperties = {
  background: 'var(--bg-card)', border: '1px solid var(--border-medium)',
  borderRadius: 8, padding: '7px 14px', fontSize: 12, color: 'var(--text-secondary)',
  fontFamily: 'var(--font-body)', cursor: 'pointer',
};

const gridStyle: React.CSSProperties = {
  display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 14,
};

const cardStyle: React.CSSProperties = {
  background: 'var(--bg-card)', border: '1px solid var(--border-subtle)',
  borderRadius: 12, padding: '18px 20px', transition: 'all 0.2s', cursor: 'pointer',
};

const dashedCardStyle: React.CSSProperties = {
  border: '1px dashed var(--border-medium)', borderRadius: 12,
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  cursor: 'pointer', transition: 'all 0.15s',
};

const cardHeaderStyle: React.CSSProperties = {
  display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12,
};

const iconStyle: React.CSSProperties = {
  width: 40, height: 40, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18, fontWeight: 700,
};

const statusBadgeStyle: React.CSSProperties = {
  fontSize: 10, padding: '2px 8px', borderRadius: 4, fontWeight: 500,
};

const cardNameStyle: React.CSSProperties = { fontSize: 14, fontWeight: 600, marginBottom: 3 };
const cardDescStyle: React.CSSProperties = { fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.4, marginBottom: 12 };

const modelStatsStyle: React.CSSProperties = {
  display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, marginBottom: 12,
};

const modelStatStyle: React.CSSProperties = {
  background: 'var(--bg-elevated)', borderRadius: 6, padding: '6px 8px', textAlign: 'center',
};

const modelStatLabelStyle: React.CSSProperties = {
  fontSize: 9, color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: 0.3,
};

const modelStatValueStyle: React.CSSProperties = {
  fontSize: 12, fontWeight: 600, fontFamily: 'var(--font-mono)', marginTop: 2,
};

const tagsStyle: React.CSSProperties = { display: 'flex', gap: 4, flexWrap: 'wrap', marginBottom: 12 };
const tagStyle: React.CSSProperties = {
  fontSize: 10, padding: '2px 7px', borderRadius: 4, fontWeight: 500, fontFamily: 'var(--font-mono)',
};

const cardFooterStyle: React.CSSProperties = {
  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
  paddingTop: 12, borderTop: '1px solid var(--border-subtle)',
};

const cardMetaStyle: React.CSSProperties = {
  fontSize: 11, color: 'var(--text-dim)', display: 'flex', gap: 12,
};

const actionBtnStyle: React.CSSProperties = {
  width: 28, height: 28, borderRadius: 6, background: 'var(--bg-elevated)',
  border: '1px solid var(--border-subtle)', color: 'var(--text-muted)',
  display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', fontSize: 12,
};

const overlayStyle: React.CSSProperties = {
  position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 99,
  backdropFilter: 'blur(4px)',
};

const panelStyle: React.CSSProperties = {
  position: 'fixed', top: 0, right: 0, width: 580, height: '100vh',
  background: 'var(--bg-base)', borderLeft: '1px solid var(--border-subtle)',
  zIndex: 100, display: 'flex', flexDirection: 'column',
  transition: 'right 0.3s ease', boxShadow: '0 24px 48px rgba(0,0,0,0.4)',
};

const panelHeaderStyle: React.CSSProperties = {
  padding: '20px 24px', borderBottom: '1px solid var(--border-subtle)',
  display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
};

const closeBtnStyle: React.CSSProperties = {
  width: 32, height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center',
  borderRadius: 8, background: 'var(--bg-card)', border: '1px solid var(--border-medium)',
  color: 'var(--text-muted)', cursor: 'pointer', fontSize: 16,
};

const panelFooterStyle: React.CSSProperties = {
  padding: '14px 24px', borderTop: '1px solid var(--border-subtle)',
  display: 'flex', gap: 8, background: 'var(--bg-base)',
};

const formLabelStyle: React.CSSProperties = {
  display: 'block', fontSize: 12, color: 'var(--text-muted)', marginBottom: 5, fontWeight: 500,
};

const formInputStyle: React.CSSProperties = {
  width: '100%', background: 'var(--bg-card)', border: '1px solid var(--border-medium)',
  borderRadius: 8, padding: '8px 12px', fontSize: 13, color: 'var(--text-primary)',
  fontFamily: 'var(--font-body)', outline: 'none',
};

const capItemStyle: React.CSSProperties = {
  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
  background: 'var(--bg-card)', border: '1px solid var(--border-subtle)',
  borderRadius: 8, padding: '8px 12px',
};

const toggleStyle: React.CSSProperties = {
  width: 36, height: 20, borderRadius: 10, cursor: 'pointer', position: 'relative', transition: 'all 0.2s',
};

const toggleDotStyle: React.CSSProperties = {
  position: 'absolute', top: 2, width: 16, height: 16, borderRadius: 8, background: 'white', transition: 'all 0.2s',
};

export default Resources;

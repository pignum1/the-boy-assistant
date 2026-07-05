import { Pagination } from './shared/Pagination';
import { useState, useEffect, useCallback, useMemo } from 'react';
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
  statusBadgeStyle,
  tagsStyle,
  tagStyle,
  searchInputStyle,
  overlayStyle,
  panelStyle,
  panelHeaderStyle,
  panelFooterStyle,
  closeBtnStyle,
  formLabelStyle,
  formInputStyle,
  capItemStyle,
  toggleStyle,
  toggleDotStyle,
  getProviderColorKey,
} from './shared/styles';

// ── Types ──

interface ModelResource {
  id: string; name: string; provider: string; context_window: number;
  capabilities?: string[]; status?: string; api_key_masked?: string;
  agent_count?: number;
}

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

const STATUS_STYLE: Record<string, { bg: string; color: string }> = {
  online: { bg: 'var(--green-bg)', color: 'var(--green-400)' },
  busy: { bg: 'var(--gold-bg)', color: 'var(--gold-400)' },
  idle: { bg: 'rgba(148,163,184,0.06)', color: 'var(--text-muted)' },
  offline: { bg: 'rgba(148,163,184,0.04)', color: 'var(--text-dim)' },
};

const STATUS_LABEL: Record<string, string> = {
  online: '在线', busy: '使用中', idle: '空闲', offline: '离线',
};

// ── Local styles ──

const gridStyle: React.CSSProperties = {
  display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 14,
};

const dashedCardStyle: React.CSSProperties = {
  border: '1px dashed var(--border-medium)', borderRadius: 12,
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  cursor: 'pointer', transition: 'all 0.15s',
};

// ── Utility ──

function formatContextWindow(n?: number): string {
  if (!n) return '-';
  if (n >= 1000000) return `${(n / 1000000).toFixed(0)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(0)}K`;
  return String(n);
}

// ── Main Component ──

export function ModelsPage() {
  const [searchQuery, setSearchQuery] = useState('');

  // Data
  const [models, setModels] = useState<ModelResource[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(20);
  const [total, setTotal] = useState(0);

  // Provider panel
  const [providerPanelOpen, setProviderPanelOpen] = useState(false);
  const [providerPanelKey, setProviderPanelKey] = useState<string | null>(null);

  const fetchModels = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.get<{ items: ModelResource[]; total: number }>(
        '/api/v1/models',
        { skip: page * pageSize, limit: pageSize }
      );
      setModels(Array.isArray(data) ? data : (data as any).items || []);
      if (!Array.isArray(data) && (data as any).total !== undefined) {
        setTotal((data as any).total);
      }
    } catch { /* use defaults */ }
    setLoading(false);
  }, [page, pageSize]);

  useEffect(() => { fetchModels(); }, [fetchModels]);

  // Group models by provider
  const providerSummaries = useMemo(() => {
    const map = new Map<string, ModelResource[]>();
    for (const m of models) {
      if (!map.has(m.provider)) map.set(m.provider, []);
      map.get(m.provider)!.push(m);
    }
    return Object.entries(PROVIDER_CONFIG)
      .map(([key, config]) => ({
        key,
        config,
        models: map.get(key) || [],
        apiKeyConfigured: (map.get(key) || []).some((m) => m.api_key_masked !== null),
      }));
  }, [models]);

  if (loading) {
    return (
      <div style={{ padding: '40px 32px', position: 'relative', zIndex: 1 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, letterSpacing: -0.5 }}>模型管理</h1>
        <p style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 8 }}>加载中...</p>
      </div>
    );
  }

  return (
    <div style={{ padding: '28px 32px', maxWidth: 1400, position: 'relative', zIndex: 1 }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 700, letterSpacing: -0.5 }}>模型管理</h1>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>以供应商为中心管理 AI 模型</div>
        </div>
        <button
          style={btnPrimaryStyle}
          onClick={() => {
            setProviderPanelKey(null);
            setProviderPanelOpen(true);
          }}
        >
          + 添加模型
        </button>
      </div>

      {/* Search */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 20, alignItems: 'center' }}>
        <input
          style={searchInputStyle}
          placeholder="搜索模型名称..."
          value={searchQuery}
          onChange={(e) => { setSearchQuery(e.target.value); setPage(0); }}
        />
      </div>

      {/* Card Grid */}
      <div style={gridStyle}>
        {providerSummaries
          .filter((ps) => {
            if (!searchQuery) return true;
            const q = searchQuery.toLowerCase();
            return ps.config.label.toLowerCase().includes(q) ||
              ps.models.some((m) => String(m.name || '').toLowerCase().includes(q) ||
                String((m as any).model_name || '').toLowerCase().includes(q));
          })
          .map((ps) => (
            <ProviderCard
              key={ps.key}
              summary={ps}
              onClick={() => { setProviderPanelKey(ps.key); setProviderPanelOpen(true); }}
            />
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
      </div>

      {/* Provider Panel */}
      {providerPanelOpen && (
        <ProviderPanel
          providerKey={providerPanelKey}
          models={models}
          onSelectProvider={(key) => setProviderPanelKey(key)}
          onClose={() => { setProviderPanelOpen(false); setProviderPanelKey(null); }}
          onRefresh={fetchModels}
        />
      )}
      <Pagination skip={page * pageSize} limit={pageSize} total={total} onPageChange={(skip) => setPage(Math.floor(skip / pageSize))} />
    </div>
  );
}

// ── Sub-components ──

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
      <div style={cardDescStyle}>{models.length} 个模型{models.length > 0 ? ` · ${models.map((m) => m.name || (m as any).model_name || (m as any).display_name || '').join(', ')}` : ''}</div>
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

// ── Provider Panel ──

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
      // 已配置 Key 的掩码展示由 existingMaskedKey 提供（来自模型列表 api_key_masked），
      // 无需再请求 /provider/{provider}/key：该端点未配 Key 时返回 404 会刷红控制台，
      // 且返回字段为 api_key_masked 而非 api_key（旧代码读取无效）。
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
              {Object.entries(PROVIDER_CONFIG).map(([key, cfg]) => {
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
                <button style={btnSecondaryStyle} onClick={() => setShowFetchModal(false)}>取消</button>
                <button
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
                            {(m as any).model_name || m.name} · {formatContextWindow(m.context_window)}
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
                          <button style={{ ...btnSecondaryStyle, fontSize: 11 }}
                            onClick={(e) => { e.stopPropagation(); setEditingModelId(null); }}
                          >取消</button>
                          <button style={{ ...btnPrimaryStyle, fontSize: 11 }}
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
              <button style={{ ...btnSecondaryStyle, fontSize: 12 }} onClick={() => setShowAddForm(!showAddForm)}>
                {showAddForm ? '取消' : '+ 手动添加'}
              </button>
              <button
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
                    const registeredNames = new Set(providerModels.map((m) => (m as any).model_name || m.name));
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
                  <button style={{ ...btnSecondaryStyle, fontSize: 11 }} onClick={() => setShowAddForm(false)}>取消</button>
                  <button style={{ ...btnPrimaryStyle, fontSize: 11 }}
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

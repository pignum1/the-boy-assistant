import { Pagination } from './shared/Pagination';
import { useState, useEffect, useCallback } from 'react';
import { api } from '../../shared/api/client';
import {
  btnPrimaryStyle,
  btnSecondaryStyle,
  cardStyle,
  cardHeaderStyle,
  iconStyle,
  cardNameStyle,
  cardDescStyle,
  tagsStyle,
  tagStyle,
  searchInputStyle,
  overlayStyle,
  panelStyle,
  panelHeaderStyle,
  closeBtnStyle,
  formLabelStyle,
  formInputStyle,
} from './shared/styles';

// ── Types ──

interface MCPServerResource {
  id: string;
  name: string;
  transport: string; // "sse" | "stdio" | "http"
  url?: string;
  command?: string;
  args?: string[];
  env?: Record<string, any>;
  api_key_ref?: string;
  status: string; // "disconnected" | "connected" | "error"
  config?: Record<string, any>;
  tool_count: number;
  created_at: string;
  updated_at: string;
}

interface ToolResource {
  id: string;
  name: string;
  description?: string;
  param_schema?: Record<string, any>;
  server_id: string;
  is_stateful: boolean;
  is_enabled: boolean;
  requires_approval: boolean;
  config?: Record<string, any>;
  created_at: string;
  updated_at: string;
}

// ── Transport Config ──

const TRANSPORT_CONFIG: Record<
  string,
  { label: string; color: string; icon: string; colorKey: string }
> = {
  sse: {
    label: 'SSE',
    color: 'var(--green-400)',
    icon: '📡',
    colorKey: 'green',
  },
  stdio: {
    label: 'STDIO',
    color: 'var(--blue-400)',
    icon: '💻',
    colorKey: 'blue',
  },
  http: {
    label: 'HTTP',
    color: 'var(--purple-400)',
    icon: '🌐',
    colorKey: 'purple',
  },
};

const TRANSPORT_OPTIONS = [
  { value: 'sse', label: 'SSE (Server-Sent Events)' },
  { value: 'stdio', label: 'STDIO (Standard I/O)' },
  { value: 'http', label: 'HTTP (Streamable HTTP)' },
];

// ── Status helpers ──

const STATUS_DOT_COLOR: Record<string, string> = {
  connected: 'var(--green-400)',
  error: 'var(--red-400)',
  disconnected: 'var(--text-dim)',
};

const STATUS_LABEL: Record<string, string> = {
  connected: '已连接',
  error: '连接错误',
  disconnected: '未连接',
};

// ── Local styles ──

const gridStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
  gap: 14,
};

const dashedCardStyle: React.CSSProperties = {
  border: '1px dashed var(--border-medium)',
  borderRadius: 12,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  cursor: 'pointer',
  transition: 'all 0.15s',
};

// ── Main Component ──

export function MCPServersPage() {
  const [searchQuery, setSearchQuery] = useState('');

  // Data
  const [servers, setServers] = useState<MCPServerResource[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(20);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);

  // Panel
  const [panelOpen, setPanelOpen] = useState(false);
  const [selectedServerId, setSelectedServerId] = useState<string | null>(null);

  const fetchServers = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.get<{ items: MCPServerResource[]; total: number }>(
        '/api/v1/mcp-servers',
        { skip: page * pageSize, limit: pageSize }
      );
      setServers(Array.isArray(data) ? data : (data as any).items || []);
      if (!Array.isArray(data) && (data as any).total !== undefined) {
        setTotal((data as any).total);
      }
    } catch {
      setError("加载失败，请重试");
    }
    setLoading(false);
  }, [page, pageSize]);

  useEffect(() => {
    fetchServers();
  }, [fetchServers]);

  if (loading) {
    return (
      <div style={{ padding: '40px 32px', position: 'relative', zIndex: 1 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, letterSpacing: -0.5 }}>
          MCP 服务器
        </h1>
        <p style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 8 }}>
          加载中...
        </p>
      </div>
    );
  }

  return (
    <div
      style={{
        padding: '28px 32px',
        maxWidth: 1400,
        position: 'relative',
        zIndex: 1,
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 24,
        }}
      >
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 700, letterSpacing: -0.5 }}>
            MCP 服务器
          </h1>
          <div
            style={{
              fontSize: 12,
              color: 'var(--text-muted)',
              marginTop: 4,
            }}
          >
            管理 MCP 协议服务器，自动发现工具
          </div>
        </div>
        <button
          style={btnPrimaryStyle}
          onClick={() => {
            setSelectedServerId(null);
            setPanelOpen(true);
          }}
        >
          + 注册服务器
        </button>
      </div>

      {/* Search */}
      <div
        style={{
          display: 'flex',
          gap: 10,
          marginBottom: 20,
          alignItems: 'center',
        }}
      >
        <input
          style={searchInputStyle}
          placeholder="搜索服务器名称..."
          value={searchQuery}
          onChange={(e) => { setSearchQuery(e.target.value); setPage(0); }}
        />
      </div>

      {/* Card Grid */}
      <div style={gridStyle}>
        {servers
          .filter((s) => {
            if (!searchQuery) return true;
            const q = searchQuery.toLowerCase();
            return (
              (s.name || '').toLowerCase().includes(q) ||
              (s.transport || '').toLowerCase().includes(q) ||
              (s.url || '').toLowerCase().includes(q) ||
              (s.command || '').toLowerCase().includes(q)
            );
          })
          .map((server) => (
            <MCPServerCard
              key={server.id}
              server={server}
              onClick={() => {
                setSelectedServerId(server.id);
                setPanelOpen(true);
              }}
            />
          ))}
        <div
          style={{ ...dashedCardStyle, minHeight: 180 }}
          onClick={() => {
            setSelectedServerId(null);
            setPanelOpen(true);
          }}
        >
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 24, marginBottom: 6, opacity: 0.3 }}>
              +
            </div>
            <div style={{ fontSize: 13, color: 'var(--text-dim)' }}>
              {servers.length === 0
                ? '注册第一个服务器'
                : '注册服务器'}
            </div>
            <div
              style={{
                fontSize: 11,
                color: 'var(--text-dim)',
                marginTop: 4,
              }}
            >
              添加 MCP 服务器 · 自动发现工具
            </div>
          </div>
        </div>
      </div>

      <Pagination skip={page * pageSize} limit={pageSize} total={total} onPageChange={(skip) => setPage(Math.floor(skip / pageSize))} />

      {/* Server Panel */}
      {panelOpen && (
        <MCPServerPanel
          serverId={selectedServerId}
          onClose={() => {
            setPanelOpen(false);
            setSelectedServerId(null);
          }}
          onRefresh={fetchServers}
        />
      )}
    </div>
  );
}

// ── MCPServerCard ──

function MCPServerCard({
  server,
  onClick,
}: {
  server: MCPServerResource;
  onClick: () => void;
}) {
  const tc = TRANSPORT_CONFIG[server.transport] || {
    label: server.transport.toUpperCase(),
    color: 'var(--text-muted)',
    icon: '🔌',
    colorKey: 'gold',
  };

  return (
    <div style={cardStyle} onClick={onClick}>
      <div style={cardHeaderStyle}>
        <div
          style={{
            ...iconStyle,
            background: `var(--${tc.colorKey}-bg)`,
            border: `1px solid var(--${tc.colorKey}-border)`,
            fontSize: 20,
          }}
        >
          {tc.icon}
        </div>
        <span
          style={{
            fontSize: 10,
            fontWeight: 600,
            padding: '2px 8px',
            borderRadius: 10,
            background: `var(--${tc.colorKey}-bg)`,
            color: tc.color,
            border: `1px solid var(--${tc.colorKey}-border)`,
          }}
        >
          {tc.label}
        </span>
      </div>
      <div style={cardNameStyle}>{server.name}</div>
      <div style={cardDescStyle}>
        {server.tool_count} 个工具
        {server.url && ` · ${server.url}`}
        {server.command && ` · ${server.command}`}
      </div>
      <div
        style={{
          ...cardDescStyle,
          marginTop: 6,
          display: 'flex',
          alignItems: 'center',
          gap: 4,
        }}
      >
        <span
          style={{
            width: 6,
            height: 6,
            borderRadius: '50%',
            background:
              STATUS_DOT_COLOR[server.status] || 'var(--text-dim)',
            display: 'inline-block',
          }}
        />
        {STATUS_LABEL[server.status] || server.status}
      </div>
      <div style={tagsStyle}>
        <span
          style={{
            ...tagStyle,
            background: `var(--${tc.colorKey}-bg)`,
            color: tc.color,
            border: `1px solid var(--${tc.colorKey}-border)`,
          }}
        >
          {tc.label}
        </span>
        {server.tool_count > 0 && (
          <span
            style={{
              ...tagStyle,
              background: 'var(--bg-elevated)',
              color: 'var(--text-muted)',
              border: '1px solid var(--border-medium)',
            }}
          >
            {server.tool_count} tools
          </span>
        )}
      </div>
    </div>
  );
}

// ── MCPServerPanel ──

function MCPServerPanel({
  serverId,
  onClose,
  onRefresh,
}: {
  serverId: string | null;
  onClose: () => void;
  onRefresh: () => void;
}) {
  // ── Form state ──
  const [name, setName] = useState('');
  const [transport, setTransport] = useState('sse');
  const [url, setUrl] = useState('');
  const [command, setCommand] = useState('');
  const [args, setArgs] = useState('');
  const [env, setEnv] = useState('');
  const [apiKeyRef, setApiKeyRef] = useState('');

  // ── Action state ──
  const [saving, setSaving] = useState(false);
  const [testResult, setTestResult] = useState<{
    open: boolean;
    loading: boolean;
    result: { success: boolean; message: string } | null;
  }>({ open: false, loading: false, result: null });

  // ── Tools state ──
  const [tools, setTools] = useState<ToolResource[]>([]);
  const [toolsLoading, setToolsLoading] = useState(false);
  const [expandedToolId, setExpandedToolId] = useState<string | null>(null);
  const [discoverResult, setDiscoverResult] = useState<{
    open: boolean;
    loading: boolean;
    result: {
      added: number;
      removed: number;
      unchanged: number;
      tools: string[];
    } | null;
  }>({ open: false, loading: false, result: null });
  // ── Toast & confirm ──
  const [toast, setToast] = useState<{
    message: string;
    type: 'success' | 'error' | 'info';
  } | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<{
    type: 'server' | 'tool';
    id: string;
    label: string;
  } | null>(null);
  const [deleting, setDeleting] = useState(false);

  const showToast = (
    message: string,
    type: 'success' | 'error' | 'info' = 'info',
  ) => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  };

  // ── Load server data ──
  useEffect(() => {
    if (serverId) {
      api
        .get<MCPServerResource>(`/api/v1/mcp-servers/${serverId}`)
        .then((data) => {
          setName(data.name || '');
          setTransport(data.transport || 'sse');
          setUrl(data.url || '');
          setCommand(data.command || '');
          setArgs((data.args || []).join('\n'));
          setEnv(data.env ? JSON.stringify(data.env, null, 2) : '');
          setApiKeyRef(data.api_key_ref || '');
          fetchTools(serverId);
        })
        .catch(() => {
          showToast('加载服务器信息失败', 'error');
        });
    } else {
      // Reset form for new server
      setName('');
      setTransport('sse');
      setUrl('');
      setCommand('');
      setArgs('');
      setEnv('');
      setApiKeyRef('');
      setTools([]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serverId]);

  const fetchTools = async (sid: string) => {
    setToolsLoading(true);
    try {
      const data = await api.get<ToolResource[]>(
        `/api/v1/mcp-servers/${sid}/tools`,
      );
      setTools(data);
    } catch {
      setTools([]);
    }
    setToolsLoading(false);
  };

  // ── Save server ──
  const handleSave = async () => {
    if (!name.trim()) {
      showToast('请输入服务器名称', 'error');
      return;
    }
    setSaving(true);
    try {
      const body: Record<string, any> = {
        name: name.trim(),
        transport,
        api_key_ref: apiKeyRef.trim() || undefined,
      };

      if (transport === 'sse' || transport === 'http') {
        body.url = url.trim() || undefined;
      } else if (transport === 'stdio') {
        body.command = command.trim() || undefined;
        body.args = args
          .split('\n')
          .map((l) => l.trim())
          .filter(Boolean);
        if (env.trim()) {
          try {
            body.env = JSON.parse(env);
          } catch {
            showToast('Env JSON 格式无效', 'error');
            setSaving(false);
            return;
          }
        }
      }

      if (serverId) {
        await api.put<MCPServerResource>(
          `/api/v1/mcp-servers/${serverId}`,
          body,
        );
        showToast('服务器已更新', 'success');
      } else {
        await api.post<MCPServerResource>('/api/v1/mcp-servers', body);
        showToast('服务器已创建', 'success');
        onRefresh();
        onClose();
        return;
      }
      onRefresh();
    } catch (e: any) {
      showToast(
        `保存失败: ${
          typeof e === 'string'
            ? e
            : e?.detail || e?.message || String(e)
        }`,
        'error',
      );
    } finally {
      setSaving(false);
    }
  };

  // ── Test connection ──
  const handleTestConnection = async () => {
    if (!serverId) {
      showToast('请先保存服务器', 'error');
      return;
    }
    setTestResult({ open: true, loading: true, result: null });
    try {
      const result = await api.post<{ success: boolean; message: string }>(
        `/api/v1/mcp-servers/${serverId}/test`,
      );
      setTestResult({
        open: true,
        loading: false,
        result: { success: result.success, message: result.message },
      });
    } catch (e: any) {
      setTestResult({
        open: true,
        loading: false,
        result: {
          success: false,
          message: `测试失败 — ${
            typeof e === 'string'
              ? e
              : e?.detail || e?.message || String(e)
          }`,
        },
      });
    }
  };

  // ── Discover tools ──
  const handleDiscover = async () => {
    if (!serverId) return;
    setDiscoverResult({ open: true, loading: true, result: null });
    try {
      const result = await api.post<{
        added: number;
        removed: number;
        unchanged: number;
        tools: string[];
      }>(`/api/v1/mcp-servers/${serverId}/discover`);
      setDiscoverResult({ open: true, loading: false, result });
      fetchTools(serverId);
      onRefresh();
    } catch (e: any) {
      setDiscoverResult({
        open: true,
        loading: false,
        result: null,
      });
      showToast(
        `发现工具失败: ${
          typeof e === 'string'
            ? e
            : e?.detail || e?.message || String(e)
        }`,
        'error',
      );
    }
  };

  // ── Toggle tool enabled / requires_approval ──
  const handleToggleTool = async (toolId: string, field: 'is_enabled' | 'requires_approval') => {
    const suffix = field === 'is_enabled' ? 'toggle' : 'approval';
    try {
      const updated = await api.put<ToolResource>(
        `/api/v1/mcp-servers/${serverId}/tools/${toolId}/${suffix}`
      );
      setTools((prev) => prev.map((t) => (t.id === toolId ? updated : t)));
    } catch {
      showToast('操作失败', 'error');
    }
  };

  // ── Delete server ──
  const handleDeleteServer = async () => {
    if (!serverId) return;
    setDeleting(true);
    try {
      await api.del(`/api/v1/mcp-servers/${serverId}`);
      setConfirmDelete(null);
      showToast('服务器已删除', 'success');
      onRefresh();
      onClose();
    } catch (e: any) {
      setConfirmDelete(null);
      showToast(
        `删除失败: ${
          typeof e === 'string'
            ? e
            : e?.detail || e?.message || String(e)
        }`,
        'error',
      );
    } finally {
      setDeleting(false);
    }
  };

  // ── Derived ──
  const isNew = !serverId;
  const tc = TRANSPORT_CONFIG[transport] || {
    label: transport.toUpperCase(),
    color: 'var(--text-muted)',
    icon: '🔌',
    colorKey: 'gold',
  };

  return (
    <>
      {/* Overlay */}
      <div onClick={onClose} style={overlayStyle} />

      {/* Panel — centered modal */}
      <div
        style={{
          position: 'fixed' as const,
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          width: 680,
          maxHeight: '90vh',
          background: 'var(--bg-base)',
          borderRadius: 16,
          border: '1px solid var(--border-subtle)',
          zIndex: 101,
          display: 'flex',
          flexDirection: 'column',
          boxShadow: '0 24px 64px rgba(0,0,0,0.55)',
        }}
      >
        {/* ── Test Connection Modal ── */}
        {testResult.open && (
          <>
            <div
              onClick={() =>
                setTestResult({
                  open: false,
                  loading: false,
                  result: null,
                })
              }
              style={{
                position: 'fixed',
                inset: 0,
                background: 'rgba(0,0,0,0.5)',
                zIndex: 200,
                backdropFilter: 'blur(4px)',
              }}
            />
            <div
              style={{
                position: 'fixed',
                top: '50%',
                left: '50%',
                transform: 'translate(-50%,-50%)',
                zIndex: 201,
                width: 400,
                background: 'var(--bg-base)',
                borderRadius: 16,
                border: '1px solid var(--border-subtle)',
                padding: 32,
                boxShadow: '0 24px 48px rgba(0,0,0,0.5)',
                textAlign: 'center',
              }}
            >
              <button
                onClick={() =>
                  setTestResult({
                    open: false,
                    loading: false,
                    result: null,
                  })
                }
                style={{
                  position: 'absolute',
                  top: 16,
                  right: 16,
                  width: 28,
                  height: 28,
                  borderRadius: 6,
                  border: '1px solid var(--border-medium)',
                  background: 'var(--bg-card)',
                  color: 'var(--text-muted)',
                  cursor: 'pointer',
                  fontSize: 14,
                }}
              >
                ✕
              </button>
              {testResult.loading ? (
                <>
                  <div style={{ fontSize: 36, marginBottom: 12 }}>
                    ⏳
                  </div>
                  <div
                    style={{
                      fontSize: 16,
                      fontWeight: 600,
                      color: 'var(--text-primary)',
                    }}
                  >
                    正在测试连接...
                  </div>
                  <div
                    style={{
                      fontSize: 12,
                      color: 'var(--text-muted)',
                      marginTop: 6,
                    }}
                  >
                    正在连接 {name || 'MCP 服务器'}
                  </div>
                </>
              ) : testResult.result?.success ? (
                <>
                  <div style={{ fontSize: 48, marginBottom: 12 }}>
                    ✅
                  </div>
                  <div
                    style={{
                      fontSize: 16,
                      fontWeight: 600,
                      color: 'var(--green-400)',
                    }}
                  >
                    连接成功
                  </div>
                  <div
                    style={{
                      fontSize: 13,
                      color: 'var(--text-secondary)',
                      marginTop: 8,
                      lineHeight: 1.5,
                    }}
                  >
                    {testResult.result.message}
                  </div>
                </>
              ) : (
                <>
                  <div style={{ fontSize: 48, marginBottom: 12 }}>
                    ❌
                  </div>
                  <div
                    style={{
                      fontSize: 16,
                      fontWeight: 600,
                      color: 'var(--red-400)',
                    }}
                  >
                    连接失败
                  </div>
                  <div
                    style={{
                      fontSize: 13,
                      color: 'var(--text-secondary)',
                      marginTop: 8,
                      lineHeight: 1.5,
                      wordBreak: 'break-all',
                    }}
                  >
                    {testResult.result?.message}
                  </div>
                </>
              )}
            </div>
          </>
        )}

        {/* ── Discover Result Modal ── */}
        {discoverResult.open && (
          <>
            <div
              onClick={() =>
                setDiscoverResult({
                  open: false,
                  loading: false,
                  result: null,
                })
              }
              style={{
                position: 'fixed',
                inset: 0,
                background: 'rgba(0,0,0,0.5)',
                zIndex: 200,
                backdropFilter: 'blur(4px)',
              }}
            />
            <div
              style={{
                position: 'fixed',
                top: '50%',
                left: '50%',
                transform: 'translate(-50%,-50%)',
                zIndex: 201,
                width: 400,
                background: 'var(--bg-base)',
                borderRadius: 16,
                border: '1px solid var(--border-subtle)',
                padding: 32,
                boxShadow: '0 24px 48px rgba(0,0,0,0.5)',
                textAlign: 'center',
              }}
            >
              <button
                onClick={() =>
                  setDiscoverResult({
                    open: false,
                    loading: false,
                    result: null,
                  })
                }
                style={{
                  position: 'absolute',
                  top: 16,
                  right: 16,
                  width: 28,
                  height: 28,
                  borderRadius: 6,
                  border: '1px solid var(--border-medium)',
                  background: 'var(--bg-card)',
                  color: 'var(--text-muted)',
                  cursor: 'pointer',
                  fontSize: 14,
                }}
              >
                ✕
              </button>
              {discoverResult.loading ? (
                <>
                  <div style={{ fontSize: 36, marginBottom: 12 }}>
                    ⏳
                  </div>
                  <div
                    style={{
                      fontSize: 16,
                      fontWeight: 600,
                      color: 'var(--text-primary)',
                    }}
                  >
                    正在发现工具...
                  </div>
                  <div
                    style={{
                      fontSize: 12,
                      color: 'var(--text-muted)',
                      marginTop: 6,
                    }}
                  >
                    正在从 {name || 'MCP 服务器'} 获取工具列表
                  </div>
                </>
              ) : discoverResult.result ? (
                <>
                  <div style={{ fontSize: 48, marginBottom: 12 }}>
                    ✅
                  </div>
                  <div
                    style={{
                      fontSize: 16,
                      fontWeight: 600,
                      color: 'var(--green-400)',
                    }}
                  >
                    发现完成
                  </div>
                  <div
                    style={{
                      fontSize: 13,
                      color: 'var(--text-secondary)',
                      marginTop: 8,
                      lineHeight: 1.6,
                    }}
                  >
                    新增 {discoverResult.result.added} 个工具 · 移除{' '}
                    {discoverResult.result.removed} 个 · 未变{' '}
                    {discoverResult.result.unchanged} 个
                  </div>
                  {discoverResult.result.tools.length > 0 && (
                    <div
                      style={{
                        marginTop: 12,
                        textAlign: 'left',
                        maxHeight: 200,
                        overflowY: 'auto',
                        background: 'var(--bg-card)',
                        borderRadius: 8,
                        padding: '8px 12px',
                      }}
                    >
                      {discoverResult.result.tools.map((t, i) => (
                        <div
                          key={i}
                          style={{
                            fontSize: 11,
                            color: 'var(--text-muted)',
                            fontFamily: 'var(--font-mono)',
                            padding: '2px 0',
                          }}
                        >
                          {t}
                        </div>
                      ))}
                    </div>
                  )}
                </>
              ) : (
                <>
                  <div style={{ fontSize: 48, marginBottom: 12 }}>
                    ❌
                  </div>
                  <div
                    style={{
                      fontSize: 16,
                      fontWeight: 600,
                      color: 'var(--red-400)',
                    }}
                  >
                    发现失败
                  </div>
                  <div
                    style={{
                      fontSize: 13,
                      color: 'var(--text-secondary)',
                      marginTop: 8,
                      lineHeight: 1.5,
                    }}
                  >
                    无法从服务器获取工具信息
                  </div>
                </>
              )}
            </div>
          </>
        )}

        {/* ── Panel Header ── */}
        <div style={panelHeaderStyle}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div
              style={{
                ...iconStyle,
                background: `var(--${tc.colorKey}-bg)`,
                border: `1px solid var(--${tc.colorKey}-border)`,
                fontSize: 20,
              }}
            >
              {tc.icon}
            </div>
            <div>
              <div style={{ fontSize: 18, fontWeight: 700 }}>
                {isNew ? '注册服务器' : name}
              </div>
              <div
                style={{
                  fontSize: 12,
                  color: 'var(--text-muted)',
                  marginTop: 3,
                }}
              >
                {isNew
                  ? '配置新的 MCP 协议服务器'
                  : `${tools.length} 个工具已发现`}
              </div>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {serverId && (
              <button
                onClick={() =>
                  setConfirmDelete({
                    type: 'server',
                    id: serverId,
                    label: name,
                  })
                }
                style={{
                  width: 32,
                  height: 32,
                  borderRadius: 8,
                  border: '1px solid var(--red-border)',
                  background: 'var(--red-bg)',
                  color: 'var(--red-400)',
                  cursor: 'pointer',
                  fontSize: 14,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
                title="删除服务器"
              >
                🗑
              </button>
            )}
            <button onClick={onClose} style={closeBtnStyle}>
              ✕
            </button>
          </div>
        </div>

        {/* ── Panel Body ── */}
        <div
          style={{
            flex: 1,
            overflowY: 'auto',
            padding: '20px 24px',
          }}
        >
          {/* Config Section */}
          <div style={{ marginBottom: 24 }}>
            <div
              style={{
                fontSize: 11,
                fontWeight: 600,
                color: 'var(--text-dim)',
                textTransform: 'uppercase',
                letterSpacing: 0.5,
                marginBottom: 10,
              }}
            >
              服务器配置
            </div>

            {/* Name */}
            <div style={{ marginBottom: 10 }}>
              <label style={formLabelStyle}>名称</label>
              <input
                style={formInputStyle}
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="服务器名称"
              />
            </div>

            {/* Transport */}
            <div style={{ marginBottom: 10 }}>
              <label style={formLabelStyle}>传输协议</label>
              <select
                style={{
                  ...formInputStyle,
                  width: '100%',
                  cursor: 'pointer',
                  boxSizing: 'border-box' as const,
                }}
                value={transport}
                onChange={(e) => setTransport(e.target.value)}
              >
                {TRANSPORT_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>

            {/* URL (sse / http) */}
            {(transport === 'sse' || transport === 'http') && (
              <div style={{ marginBottom: 10 }}>
                <label style={formLabelStyle}>URL</label>
                <input
                  style={formInputStyle}
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder={
                    transport === 'sse'
                      ? '/sse'
                      : '/mcp'
                  }
                />
              </div>
            )}

            {/* Command + Args + Env (stdio) */}
            {transport === 'stdio' && (
              <>
                <div style={{ marginBottom: 10 }}>
                  <label style={formLabelStyle}>Command</label>
                  <input
                    style={formInputStyle}
                    value={command}
                    onChange={(e) => setCommand(e.target.value)}
                    placeholder="例如: npx"
                  />
                </div>
                <div style={{ marginBottom: 10 }}>
                  <label style={formLabelStyle}>
                    Args (每行一个)
                  </label>
                  <textarea
                    style={{
                      ...formInputStyle,
                      minHeight: 60,
                      resize: 'vertical',
                      fontFamily: 'var(--font-mono)',
                    }}
                    value={args}
                    onChange={(e) => setArgs(e.target.value)}
                    placeholder={
                      '-y\n@anthropic-ai/mcp-server'
                    }
                  />
                </div>
                <div style={{ marginBottom: 10 }}>
                  <label style={formLabelStyle}>
                    Env (JSON 格式, 可选)
                  </label>
                  <textarea
                    style={{
                      ...formInputStyle,
                      minHeight: 60,
                      resize: 'vertical',
                      fontFamily: 'var(--font-mono)',
                    }}
                    value={env}
                    onChange={(e) => setEnv(e.target.value)}
                    placeholder={
                      '{\n  "API_KEY": "xxx",\n  "DEBUG": "true"\n}'
                    }
                  />
                </div>
              </>
            )}

            {/* API Key Ref (optional, all transports) */}
            <div style={{ marginBottom: 10 }}>
              <label style={formLabelStyle}>
                API Key 引用 (可选)
              </label>
              <input
                style={formInputStyle}
                value={apiKeyRef}
                onChange={(e) => setApiKeyRef(e.target.value)}
                placeholder="例如: my-openai-key"
              />
            </div>

            {/* Action buttons */}
            <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
              <button
                style={{ ...btnPrimaryStyle, fontSize: 12 }}
                onClick={handleSave}
                disabled={saving}
              >
                {saving
                  ? '保存中...'
                  : isNew
                    ? '创建服务器'
                    : '保存'}
              </button>
              {serverId && (
                <button
                  style={{ ...btnSecondaryStyle, fontSize: 12 }}
                  onClick={handleTestConnection}
                  disabled={testResult.loading}
                >
                  {testResult.loading
                    ? '测试中...'
                    : '测试连接'}
                </button>
              )}
            </div>
          </div>

          {/* Tools Section (only for existing servers) */}
          {serverId && (
            <div>
              <div
                style={{
                  fontSize: 11,
                  fontWeight: 600,
                  color: 'var(--text-dim)',
                  textTransform: 'uppercase',
                  letterSpacing: 0.5,
                  marginBottom: 10,
                }}
              >
                {`已发现工具 (${tools.length})`}
              </div>

              {/* Discover button */}
              <div style={{ marginBottom: 10 }}>
                <button
                  style={{ ...btnSecondaryStyle, fontSize: 12 }}
                  onClick={handleDiscover}
                  disabled={discoverResult.loading}
                >
                  {discoverResult.loading
                    ? '发现中...'
                    : '发现工具'}
                </button>
              </div>

              {/* Tool list */}
              {toolsLoading ? (
                <div
                  style={{
                    padding: 24,
                    textAlign: 'center',
                    color: 'var(--text-dim)',
                    fontSize: 13,
                  }}
                >
                  加载中...
                </div>
              ) : tools.length === 0 ? (
                <div
                  style={{
                    padding: 24,
                    textAlign: 'center',
                    color: 'var(--text-dim)',
                    fontSize: 13,
                    background: 'var(--bg-card)',
                    borderRadius: 10,
                    border: '1px dashed var(--border-medium)',
                  }}
                >
                  暂无工具，点击“发现工具”自动扫描
                </div>
              ) : (
                <div
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 4,
                    marginBottom: 12,
                  }}
                >
                  {tools.map((tool) => {
                    const isExpanded = expandedToolId === tool.id;
                    const isDisabled = !tool.is_enabled;
                    return (
                    <div
                      key={tool.id}
                      style={{
                        padding: '10px 12px',
                        borderRadius: 8,
                        background: isDisabled ? 'rgba(255,255,255,0.02)' : 'var(--bg-card)',
                        border: '1px solid var(--border-subtle)',
                        opacity: isDisabled ? 0.5 : 1,
                      }}
                    >
                      <div
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                        }}
                      >
                        <div
                          style={{ flex: 1, minWidth: 0, cursor: 'pointer' }}
                          onClick={() => setExpandedToolId(isExpanded ? null : tool.id)}
                        >
                          <div
                            style={{
                              fontSize: 13,
                              fontWeight: 500,
                              color: 'var(--text-primary)',
                              fontFamily: 'var(--font-mono)',
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                            }}
                          >
                            {isExpanded ? '▾ ' : '▸ '}{tool.name}
                          </div>
                          {tool.description && (
                            <div
                              style={{
                                fontSize: 11,
                                color: 'var(--text-dim)',
                                marginTop: 2,
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                                whiteSpace: 'nowrap',
                              }}
                            >
                              {tool.description}
                            </div>
                          )}
                        </div>
                        <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexShrink: 0, marginLeft: 8 }}>
                          {/* requires_approval toggle */}
                          <button
                            onClick={() => handleToggleTool(tool.id, 'requires_approval')}
                            title={tool.requires_approval ? '需要审批 (点击关闭)' : '无需审批 (点击开启)'}
                            style={{
                              padding: '2px 8px',
                              borderRadius: 4,
                              border: '1px solid',
                              borderColor: tool.requires_approval ? 'var(--gold-400)' : 'var(--border-medium)',
                              background: tool.requires_approval ? 'rgba(255,193,7,0.12)' : 'transparent',
                              color: tool.requires_approval ? 'var(--gold-400)' : 'var(--text-dim)',
                              cursor: 'pointer',
                              fontSize: 10,
                              fontWeight: 500,
                              whiteSpace: 'nowrap',
                            }}
                          >
                            {tool.requires_approval ? '需审批' : '免审批'}
                          </button>
                          {/* enable/disable toggle */}
                          <button
                            onClick={() => handleToggleTool(tool.id, 'is_enabled')}
                            title={tool.is_enabled ? '已启用 (点击禁用)' : '已禁用 (点击启用)'}
                            style={{
                              width: 32,
                              height: 18,
                              borderRadius: 9,
                              border: 'none',
                              background: tool.is_enabled ? 'var(--green-400)' : 'var(--border-medium)',
                              cursor: 'pointer',
                              position: 'relative' as const,
                              flexShrink: 0,
                            }}
                          >
                            <div
                              style={{
                                position: 'absolute',
                                top: 2,
                                left: tool.is_enabled ? 16 : 2,
                                width: 14,
                                height: 14,
                                borderRadius: '50%',
                                background: '#fff',
                                transition: 'left 0.15s',
                              }}
                            />
                          </button>
                        </div>
                      </div>
                      {/* Expanded detail: param_schema */}
                      {isExpanded && tool.param_schema && (
                        <div
                          style={{
                            marginTop: 10,
                            padding: 10,
                            borderRadius: 6,
                            background: 'var(--bg-elevated)',
                            border: '1px solid var(--border-subtle)',
                            fontSize: 11,
                            fontFamily: 'var(--font-mono)',
                          }}
                        >
                          <div style={{ fontWeight: 600, marginBottom: 8, color: 'var(--text-dim)', fontSize: 10, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                            参数 Schema
                          </div>
                          {tool.param_schema.required && (
                            <div style={{ marginBottom: 8 }}>
                              <span style={{ color: 'var(--text-dim)' }}>必填: </span>
                              {(tool.param_schema.required as string[]).map((r: string) => (
                                <span key={r} style={{ color: 'var(--red-400)', marginRight: 6, fontSize: 10, background: 'rgba(255,82,82,0.1)', padding: '1px 5px', borderRadius: 3 }}>{r}</span>
                              ))}
                            </div>
                          )}
                          {tool.param_schema.properties && Object.entries(tool.param_schema.properties as Record<string, any>).map(([key, prop]) => (
                            <div key={key} style={{ marginBottom: 6, paddingBottom: 6, borderBottom: '1px solid var(--border-subtle)' }}>
                              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                                <span style={{ color: 'var(--text-primary)', fontWeight: 500 }}>{key}</span>
                                <span style={{ color: 'var(--cyan-400)', fontSize: 10, background: 'rgba(0,229,255,0.1)', padding: '1px 5px', borderRadius: 3 }}>{prop.type}</span>
                              </div>
                              {prop.description && (
                                <div style={{ color: 'var(--text-dim)', marginTop: 2, fontSize: 10 }}>{prop.description}</div>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                  })}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* ── Confirm Delete Modal ── */}
      {confirmDelete && (
        <>
          <div
            onClick={() => setConfirmDelete(null)}
            style={{
              position: 'fixed',
              inset: 0,
              background: 'rgba(0,0,0,0.5)',
              zIndex: 200,
              backdropFilter: 'blur(4px)',
            }}
          />
          <div
            style={{
              position: 'fixed',
              top: '50%',
              left: '50%',
              transform: 'translate(-50%,-50%)',
              zIndex: 201,
              width: 380,
              background: 'var(--bg-base)',
              borderRadius: 16,
              border: '1px solid var(--border-subtle)',
              padding: 28,
              boxShadow: '0 24px 48px rgba(0,0,0,0.5)',
              textAlign: 'center',
            }}
          >
            <div style={{ fontSize: 40, marginBottom: 12 }}>
              ⚠️
            </div>
            <div
              style={{
                fontSize: 15,
                fontWeight: 600,
                color: 'var(--text-primary)',
                marginBottom: 6,
              }}
            >
              确认删除
            </div>
            <div
              style={{
                fontSize: 13,
                color: 'var(--text-secondary)',
                lineHeight: 1.6,
                marginBottom: 24,
              }}
            >
              {confirmDelete.type === 'server'
                ? `确定要删除 MCP 服务器「${confirmDelete.label}」吗？所有已发现的工具也会被删除。此操作不可撤销。`
                : `确定要删除工具「${confirmDelete.label}」吗？此操作不可撤销。`}
            </div>
            <div
              style={{
                display: 'flex',
                gap: 10,
                justifyContent: 'center',
              }}
            >
              <button
                onClick={() => setConfirmDelete(null)}
                style={{
                  padding: '8px 24px',
                  borderRadius: 8,
                  border: '1px solid var(--border-medium)',
                  background: 'var(--bg-card)',
                  color: 'var(--text-secondary)',
                  cursor: 'pointer',
                  fontSize: 13,
                }}
              >
                取消
              </button>
              <button
                disabled={deleting}
                onClick={() => {
                  if (confirmDelete.type === 'server') {
                    handleDeleteServer();
                  } else {
                    handleDeleteTool(confirmDelete.id);
                  }
                }}
                style={{
                  padding: '8px 24px',
                  borderRadius: 8,
                  border: 'none',
                  background: 'var(--red-400)',
                  color: '#fff',
                  cursor: 'pointer',
                  fontSize: 13,
                  fontWeight: 600,
                }}
              >
                {deleting
                  ? '删除中...'
                  : '确认删除'}
              </button>
            </div>
          </div>
        </>
      )}

      {/* ── Toast ── */}
      {toast && (
        <div
          style={{
            position: 'fixed',
            bottom: 32,
            left: '50%',
            transform: 'translateX(-50%)',
            zIndex: 300,
            padding: '10px 24px',
            borderRadius: 10,
            background:
              toast.type === 'success'
                ? 'var(--green-bg)'
                : toast.type === 'error'
                  ? 'var(--red-bg)'
                  : 'var(--blue-bg)',
            border: `1px solid ${
              toast.type === 'success'
                ? 'var(--green-border)'
                : toast.type === 'error'
                  ? 'var(--red-border)'
                  : 'var(--blue-border)'
            }`,
            color:
              toast.type === 'success'
                ? 'var(--green-400)'
                : toast.type === 'error'
                  ? 'var(--red-400)'
                  : 'var(--blue-400)',
            fontSize: 13,
            fontWeight: 500,
            boxShadow: '0 8px 24px rgba(0,0,0,0.3)',
          }}
        >
          <span style={{ marginRight: 8 }}>
            {toast.type === 'success'
              ? '✓'
              : toast.type === 'error'
                ? '✗'
                : 'ℹ'}
          </span>
          {toast.message}
        </div>
      )}
    </>
  );
}

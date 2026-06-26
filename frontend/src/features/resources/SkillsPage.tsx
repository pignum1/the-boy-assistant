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
} from './shared/styles';

// ── Types ──

interface SkillResource {
  id: string;
  name: string;
  description?: string;
  version: string;
  path: string;
  source: string; // "git" | "upload" | "manual"
  git_url?: string;
  skill_md?: string;
  config_yaml?: string;
  created_at: string;
  updated_at: string;
}

const SOURCE_CONFIG: Record<string, { label: string; color: string; colorKey: string }> = {
  git: { label: 'Git', color: 'var(--green-400)', colorKey: 'green' },
  upload: { label: '上传', color: 'var(--blue-400)', colorKey: 'blue' },
  manual: { label: '手动', color: 'var(--text-dim)', colorKey: 'gold' },
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

const installOptionStyle: React.CSSProperties = {
  border: '1px solid var(--border-medium)',
  borderRadius: 10,
  padding: '20px 16px',
  cursor: 'pointer',
  transition: 'all 0.15s',
  textAlign: 'center',
  flex: 1,
};

const formLabelStyle: React.CSSProperties = {
  display: 'block',
  fontSize: 11,
  fontWeight: 600,
  color: 'var(--text-dim)',
  marginBottom: 4,
};

const formInputStyle: React.CSSProperties = {
  width: '100%',
  padding: '8px 12px',
  borderRadius: 8,
  border: '1px solid var(--border-medium)',
  background: 'var(--bg-card)',
  color: 'var(--text-primary)',
  fontSize: 13,
  boxSizing: 'border-box',
  outline: 'none',
};

// ── Main Component ──

export function SkillsPage() {
  const [searchQuery, setSearchQuery] = useState('');
  const [skills, setSkills] = useState<SkillResource[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(20);
  const [total, setTotal] = useState(0);

  // Detail modal
  const [detailOpen, setDetailOpen] = useState(false);
  const [selectedSkill, setSelectedSkill] = useState<SkillResource | null>(null);

  // Install modal
  const [installOpen, setInstallOpen] = useState(false);

  const fetchSkills = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.get<{ items: SkillResource[]; total: number }>(
        '/api/v1/skills',
        { skip: page * pageSize, limit: pageSize }
      );
      setSkills(Array.isArray(data) ? data : (data as any).items || []);
      if (!Array.isArray(data) && (data as any).total !== undefined) {
        setTotal((data as any).total);
      }
    } catch {
      /* keep current state */
    }
    setLoading(false);
  }, [page, pageSize]);

  useEffect(() => {
    fetchSkills();
  }, [fetchSkills]);

  const filteredSkills = skills.filter((s) => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return (
      (s.name || '').toLowerCase().includes(q) ||
      (s.description || '').toLowerCase().includes(q)
    );
  });

  if (loading) {
    return (
      <div style={{ padding: '40px 32px', position: 'relative', zIndex: 1 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, letterSpacing: -0.5 }}>
          Skill 管理
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
            Skill 管理
          </h1>
          <div
            style={{
              fontSize: 12,
              color: 'var(--text-muted)',
              marginTop: 4,
            }}
          >
            管理可复用的原子能力模块 · 支持 Git 安装和 Zip 上传
          </div>
        </div>
        <button
          style={btnPrimaryStyle}
          onClick={() => setInstallOpen(true)}
        >
          + 安装 Skill
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
          placeholder="搜索 Skill 名称..."
          value={searchQuery}
          onChange={(e) => { setSearchQuery(e.target.value); setPage(0); }}
        />
      </div>

      {/* Card Grid */}
      <div style={gridStyle}>
        {filteredSkills.map((s) => (
          <SkillCard
            key={s.id}
            skill={s}
            onClick={async () => {
              try {
                const detail = await api.get<SkillResource>(
                  `/api/v1/skills/${s.id}`,
                );
                setSelectedSkill(detail);
                setDetailOpen(true);
              } catch {
                // fallback to list data
                setSelectedSkill(s);
                setDetailOpen(true);
              }
            }}
          />
        ))}
        <div
          style={{ ...dashedCardStyle, minHeight: 180 }}
          onClick={() => setInstallOpen(true)}
        >
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 24, marginBottom: 6, opacity: 0.3 }}>
              +
            </div>
            <div style={{ fontSize: 13, color: 'var(--text-dim)' }}>
              {skills.length === 0
                ? '安装第一个 Skill'
                : '安装 Skill'}
            </div>
            <div
              style={{
                fontSize: 11,
                color: 'var(--text-dim)',
                marginTop: 4,
              }}
            >
              Git Clone · Zip 上传
            </div>
          </div>
        </div>
      </div>

      {/* Detail Modal */}
      {detailOpen && selectedSkill && (
        <SkillDetailModal
          skill={selectedSkill}
          onClose={() => {
            setDetailOpen(false);
            setSelectedSkill(null);
          }}
          onRefresh={fetchSkills}
        />
      )}

      {/* Install Modal */}
      {installOpen && (
        <InstallModal
          onClose={() => setInstallOpen(false)}
          onInstalled={() => {
            setInstallOpen(false);
            fetchSkills();
          }}
        />
      )}
      <Pagination skip={page * pageSize} limit={pageSize} total={total} onPageChange={(skip) => setPage(Math.floor(skip / pageSize))} />
    </div>
  );
}

// ── SkillCard ──

function SkillCard({
  skill,
  onClick,
}: {
  skill: SkillResource;
  onClick: () => void;
}) {
  const sc = SOURCE_CONFIG[skill.source] || SOURCE_CONFIG.manual;

  return (
    <div style={cardStyle} onClick={onClick}>
      <div style={cardHeaderStyle}>
        <div
          style={{
            ...iconStyle,
            background: 'var(--gold-bg)',
            border: '1px solid var(--gold-border)',
            fontSize: 20,
          }}
        >
          📐
        </div>
        <span
          style={{
            fontSize: 10,
            fontWeight: 600,
            padding: '2px 8px',
            borderRadius: 10,
            background: `var(--${sc.colorKey}-bg)`,
            color: sc.color,
            border: `1px solid var(--${sc.colorKey}-border)`,
          }}
        >
          {sc.label}
        </span>
      </div>
      <div style={cardNameStyle}>{skill.name}</div>
      <div style={cardDescStyle}>
        {skill.description || '—'}
      </div>
      <div style={tagsStyle}>
        <span
          style={{
            ...tagStyle,
            background: `var(--${sc.colorKey}-bg)`,
            color: sc.color,
            border: `1px solid var(--${sc.colorKey}-border)`,
          }}
        >
          {sc.label}
        </span>
        <span
          style={{
            ...tagStyle,
            background: 'var(--bg-elevated)',
            color: 'var(--text-muted)',
            border: '1px solid var(--border-medium)',
          }}
        >
          v{skill.version}
        </span>
        {skill.git_url && (
          <span
            style={{
              ...tagStyle,
              background: 'var(--bg-elevated)',
              color: 'var(--text-muted)',
              border: '1px solid var(--border-medium)',
              maxWidth: 120,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {skill.git_url.replace('file://', '').split('/').pop()}
          </span>
        )}
      </div>
      
    </div>
  );
}

// ── InstallModal ──

function InstallModal({
  onClose,
  onInstalled,
}: {
  onClose: () => void;
  onInstalled: () => void;
}) {
  const [method, setMethod] = useState<'git' | 'upload'>('git');
  const [gitUrl, setGitUrl] = useState('');
  const [name, setName] = useState('');
  const [branch, setBranch] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [installing, setInstalling] = useState(false);
  const [toast, setToast] = useState<{
    message: string;
    type: 'success' | 'error' | 'info';
  } | null>(null);

  const showToast = (
    message: string,
    type: 'success' | 'error' | 'info' = 'info',
  ) => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  };

  const handleInstall = async () => {
    if (method === 'git' && !gitUrl.trim()) {
      showToast('请输入 Git 仓库地址', 'error');
      return;
    }
    if (method === 'upload' && !file) {
      showToast('请选择 .zip 文件', 'error');
      return;
    }

    setInstalling(true);
    try {
      const formData = new FormData();
      formData.append('method', method);
      if (method === 'git') {
        formData.append('git_url', gitUrl.trim());
        if (name.trim()) formData.append('name', name.trim());
        if (branch.trim()) formData.append('branch', branch.trim());
      } else if (method === 'upload' && file) {
        formData.append('file', file);
      }

      await api.post('/api/v1/skills/install', formData);
      showToast('Skill 安装成功', 'success');
      onInstalled();
    } catch (e: any) {
      showToast(
        `安装失败: ${
          typeof e === 'string'
            ? e
            : e?.detail || e?.message || String(e)
        }`,
        'error',
      );
    } finally {
      setInstalling(false);
    }
  };

  return (
    <>
      {/* Overlay */}
      <div
        onClick={onClose}
        style={{
          position: 'fixed',
          inset: 0,
          background: 'rgba(0,0,0,0.5)',
          zIndex: 100,
          backdropFilter: 'blur(4px)',
        }}
      />

      {/* Modal */}
      <div
        style={{
          position: 'fixed',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          zIndex: 101,
          width: 520,
          maxHeight: '90vh',
          background: 'var(--bg-base)',
          borderRadius: 16,
          border: '1px solid var(--border-subtle)',
          boxShadow: '0 24px 64px rgba(0,0,0,0.55)',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {/* Header */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            padding: '20px 24px',
            borderBottom: '1px solid var(--border-subtle)',
            flexShrink: 0,
          }}
        >
          <div>
            <div style={{ fontSize: 18, fontWeight: 700 }}>安装 Skill</div>
            <div
              style={{
                fontSize: 12,
                color: 'var(--text-muted)',
                marginTop: 3,
              }}
            >
              支持 Git 仓库克隆或本地上传 Zip 压缩包
            </div>
          </div>
          <button
            onClick={onClose}
            style={{
              width: 32,
              height: 32,
              borderRadius: 8,
              border: '1px solid var(--border-medium)',
              background: 'var(--bg-card)',
              color: 'var(--text-muted)',
              cursor: 'pointer',
              fontSize: 14,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            ✕
          </button>
        </div>

        {/* Body */}
        <div
          style={{
            flex: 1,
            overflowY: 'auto',
            padding: '20px 24px',
          }}
        >
          {/* Method selector */}
          <div
            style={{
              display: 'flex',
              gap: 12,
              marginBottom: 24,
            }}
          >
            <div
              style={{
                ...installOptionStyle,
                borderColor:
                  method === 'git'
                    ? 'var(--green-400)'
                    : 'var(--border-medium)',
                background:
                  method === 'git'
                    ? 'var(--green-bg)'
                    : 'var(--bg-card)',
              }}
              onClick={() => setMethod('git')}
            >
              <div style={{ fontSize: 28, marginBottom: 8 }}>🔀</div>
              <div
                style={{
                  fontSize: 14,
                  fontWeight: 600,
                  color: 'var(--text-primary)',
                }}
              >
                Git 安装
              </div>
              <div
                style={{
                  fontSize: 11,
                  color: 'var(--text-dim)',
                  marginTop: 4,
                }}
              >
                git clone 到 skills 目录
              </div>
            </div>
            <div
              style={{
                ...installOptionStyle,
                borderColor:
                  method === 'upload'
                    ? 'var(--blue-400)'
                    : 'var(--border-medium)',
                background:
                  method === 'upload'
                    ? 'var(--blue-bg)'
                    : 'var(--bg-card)',
              }}
              onClick={() => setMethod('upload')}
            >
              <div style={{ fontSize: 28, marginBottom: 8 }}>📦</div>
              <div
                style={{
                  fontSize: 14,
                  fontWeight: 600,
                  color: 'var(--text-primary)',
                }}
              >
                Zip 上传
              </div>
              <div
                style={{
                  fontSize: 11,
                  color: 'var(--text-dim)',
                  marginTop: 4,
                }}
              >
                上传 .zip 自动解压
              </div>
            </div>
          </div>

          {/* Git form */}
          {method === 'git' && (
            <>
              <div style={{ marginBottom: 12 }}>
                <label style={formLabelStyle}>Git 仓库地址 *</label>
                <input
                  style={formInputStyle}
                  value={gitUrl}
                  onChange={(e) => setGitUrl(e.target.value)}
                  placeholder="https://github.com/user/skill-repo.git"
                />
              </div>
              <div style={{ marginBottom: 12 }}>
                <label style={formLabelStyle}>名称 (可选, 自定义目录名)</label>
                <input
                  style={formInputStyle}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="默认从 URL 推断"
                />
              </div>
              <div style={{ marginBottom: 12 }}>
                <label style={formLabelStyle}>分支 (可选)</label>
                <input
                  style={formInputStyle}
                  value={branch}
                  onChange={(e) => setBranch(e.target.value)}
                  placeholder="默认: 默认分支"
                />
              </div>
            </>
          )}

          {/* Upload form */}
          {method === 'upload' && (
            <div style={{ marginBottom: 12 }}>
              <label style={formLabelStyle}>Skill Zip 文件 *</label>
              <div
                style={{
                  border: '2px dashed var(--border-medium)',
                  borderRadius: 10,
                  padding: 32,
                  textAlign: 'center',
                  cursor: 'pointer',
                  background: 'var(--bg-card)',
                }}
                onClick={() => document.getElementById('skill-file-input')?.click()}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  const f = e.dataTransfer.files?.[0];
                  if (f?.name.endsWith('.zip')) setFile(f);
                }}
              >
                <input
                  id="skill-file-input"
                  type="file"
                  accept=".zip"
                  style={{ display: 'none' }}
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) setFile(f);
                  }}
                />
                {file ? (
                  <div>
                    <div style={{ fontSize: 24, marginBottom: 4 }}>📄</div>
                    <div style={{ fontSize: 13, color: 'var(--text-primary)', fontWeight: 500 }}>
                      {file.name}
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 2 }}>
                      {(file.size / 1024).toFixed(1)} KB
                    </div>
                  </div>
                ) : (
                  <div>
                    <div style={{ fontSize: 28, marginBottom: 8 }}>📁</div>
                    <div style={{ fontSize: 13, color: 'var(--text-dim)' }}>
                      点击选择或拖拽 .zip 文件到此处
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 4 }}>
                      需包含 SKILL.md 文件
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'flex-end',
            gap: 8,
            padding: '16px 24px',
            borderTop: '1px solid var(--border-subtle)',
            flexShrink: 0,
          }}
        >
          <button style={btnSecondaryStyle} onClick={onClose}>
            取消
          </button>
          <button
            style={btnPrimaryStyle}
            onClick={handleInstall}
            disabled={installing}
          >
            {installing ? '安装中...' : '安装'}
          </button>
        </div>
      </div>

      {/* Toast */}
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
          {toast.message}
        </div>
      )}
    </>
  );
}

// ── SkillDetailModal ──

function SkillDetailModal({
  skill,
  onClose,
  onRefresh,
}: {
  skill: SkillResource;
  onClose: () => void;
  onRefresh: () => void;
}) {
  const [deleting, setDeleting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [toast, setToast] = useState<{
    message: string;
    type: 'success' | 'error' | 'info';
  } | null>(null);

  const showToast = (
    message: string,
    type: 'success' | 'error' | 'info' = 'info',
  ) => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  };

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await api.del(`/api/v1/skills/${skill.id}`);
      setConfirmDelete(false);
      showToast('Skill 已删除', 'success');
      onRefresh();
      onClose();
    } catch (e: any) {
      setConfirmDelete(false);
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

  const sc = SOURCE_CONFIG[skill.source] || SOURCE_CONFIG.manual;

  // ── File tree state ──
  interface FileNode {
    name: string;
    type: 'dir' | 'file';
    children?: FileNode[];
    content?: string;
  }
  const [fileTree, setFileTree] = useState<FileNode | null>(null);
  const [fileTreeLoading, setFileTreeLoading] = useState(false);
  const [selectedFile, setSelectedFile] = useState<{ name: string; content: string } | null>(null);
  const [expandedDirs, setExpandedDirs] = useState<Set<string>>(new Set());

  useEffect(() => {
    let cancelled = false;
    setFileTreeLoading(true);
    api.get<FileNode>(`/api/v1/skills/${skill.id}/files`)
      .then((tree) => {
        if (!cancelled) {
          setFileTree(tree);
          const allDirs = new Set<string>();
          const collectDirs = (node: FileNode, path: string) => {
            if (node.type === 'dir') {
              const fullPath = path + '/' + node.name;
              allDirs.add(fullPath);
              (node.children || []).forEach((c) => collectDirs(c, fullPath));
            }
          };
          collectDirs(tree, '');
          setExpandedDirs(allDirs);
        }
      })
      .catch(() => {})
      .finally(() => { if (!cancelled) setFileTreeLoading(false); });
    return () => { cancelled = true; };
  }, [skill.id]);

  const toggleDir = (path: string) => {
    setExpandedDirs((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  const renderFileTree = (node: FileNode, depth: number, parentPath: string): JSX.Element => {
    const nodePath = parentPath + '/' + node.name;
    const isSelected = selectedFile?.name === node.name && node.type === 'file';

    if (node.type === 'dir') {
      const isOpen = expandedDirs.has(nodePath);
      return (
        <div key={nodePath}>
          <div
            onClick={() => toggleDir(nodePath)}
            style={{
              display: 'flex',
              alignItems: 'center',
              padding: '2px 0',
              paddingLeft: depth * 16,
              cursor: 'pointer',
              fontSize: 12,
              color: isOpen ? 'var(--text-primary)' : 'var(--text-secondary)',
              background: isOpen ? 'rgba(255,255,255,0.06)' : 'transparent',
              borderRadius: 4,
              userSelect: 'none',
              lineHeight: '22px',
              marginLeft: 4,
              transition: 'background 0.1s, color 0.1s',
              fontWeight: isOpen ? 500 : 400,
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = isOpen ? 'rgba(255,255,255,0.08)' : 'rgba(255,255,255,0.04)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = isOpen ? 'rgba(255,255,255,0.06)' : 'transparent';
            }}
          >
            <span style={{ width: 16, textAlign: 'center', flexShrink: 0, fontSize: 10, color: isOpen ? 'var(--text-primary)' : 'var(--text-dim)', fontWeight: 600 }}>
              {isOpen ? '▾' : '▸'}
            </span>
            <span style={{
              width: 16,
              textAlign: 'center',
              flexShrink: 0,
              fontSize: 12,
            }}>
              {isOpen ? '📂' : '📁'}
            </span>
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {node.name}
            </span>
          </div>
          {isOpen &&
            (node.children || []).map((child) =>
              renderFileTree(child, depth + 1, nodePath),
            )}
        </div>
      );
    }

    return (
      <div
        key={nodePath}
        onClick={() => setSelectedFile({ name: node.name, content: node.content || '' })}
        style={{
          display: 'flex',
          alignItems: 'center',
          padding: '2px 0',
          paddingLeft: depth * 16,
          cursor: 'pointer',
          fontSize: 12,
          color: isSelected ? 'var(--text-primary)' : 'var(--text-secondary)',
          background: isSelected ? 'rgba(255,255,255,0.08)' : 'transparent',
          borderRadius: 4,
          userSelect: 'none',
          lineHeight: '22px',
          marginLeft: 4,
          transition: 'background 0.1s',
        }}
        onMouseEnter={(e) => {
          if (!isSelected) e.currentTarget.style.background = 'rgba(255,255,255,0.04)';
        }}
        onMouseLeave={(e) => {
          if (!isSelected) e.currentTarget.style.background = 'transparent';
        }}
      >
        <span style={{ width: 32, flexShrink: 0 }} />
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {node.name}
        </span>
      </div>
    );
  };

  return (
    <>
      {/* Overlay */}
      <div
        onClick={onClose}
        style={{
          position: 'fixed',
          inset: 0,
          background: 'rgba(0,0,0,0.5)',
          zIndex: 100,
          backdropFilter: 'blur(4px)',
        }}
      />

      {/* Modal — fixed size, wider for file tree */}
      <div
        style={{
          position: 'fixed',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          zIndex: 101,
          width: 860,
          height: 560,
          background: 'var(--bg-base)',
          borderRadius: 16,
          border: '1px solid var(--border-subtle)',
          boxShadow: '0 24px 64px rgba(0,0,0,0.55)',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {/* Header */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            padding: '20px 24px',
            borderBottom: '1px solid var(--border-subtle)',
            flexShrink: 0,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div
              style={{
                ...iconStyle,
                background: 'var(--gold-bg)',
                border: '1px solid var(--gold-border)',
                fontSize: 20,
              }}
            >
              📐
            </div>
            <div>
              <div style={{ fontSize: 18, fontWeight: 700 }}>
                {skill.name}
              </div>
              <div
                style={{
                  fontSize: 12,
                  color: 'var(--text-muted)',
                  marginTop: 3,
                }}
              >
                {skill.description || 'v' + skill.version}
              </div>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <button
              onClick={() => setConfirmDelete(true)}
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
              title="删除 Skill"
            >
              🗑
            </button>
            <button
              onClick={onClose}
              style={{
                width: 32,
                height: 32,
                borderRadius: 8,
                border: '1px solid var(--border-medium)',
                background: 'var(--bg-card)',
                color: 'var(--text-muted)',
                cursor: 'pointer',
                fontSize: 14,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              ✕
            </button>
          </div>
        </div>

        {/* Body — two columns: file tree | content preview */}
        <div
          style={{
            flex: 1,
            display: 'flex',
            overflow: 'hidden',
            minHeight: 0,
          }}
        >
          {/* Left: File Tree */}
          <div
            style={{
              width: 240,
              flexShrink: 0,
              borderRight: '1px solid var(--border-subtle)',
              overflowY: 'auto',
              padding: '8px 0',
              background: 'rgba(0,0,0,0.12)',
            }}
          >
            <div
              style={{
                fontSize: 10,
                fontWeight: 600,
                color: 'var(--text-dim)',
                textTransform: 'uppercase',
                letterSpacing: 0.8,
                marginBottom: 4,
                padding: '0 12px 8px',
              }}
            >
              {skill.name}
            </div>
            {fileTreeLoading ? (
              <div style={{ fontSize: 12, color: 'var(--text-dim)', padding: '0 12px' }}>
                加载中...
              </div>
            ) : fileTree ? (
              renderFileTree(fileTree, 0, '')
            ) : (
              <div style={{ fontSize: 12, color: 'var(--text-dim)', padding: '0 12px' }}>
                无法加载文件树
              </div>
            )}
          </div>

          {/* Right: Content Preview */}
          <div
            style={{
              flex: 1,
              overflowY: 'auto',
              minWidth: 0,
            }}
          >
            {selectedFile ? (
              <>
                <div
                  style={{
                    fontSize: 10,
                    fontWeight: 600,
                    color: 'var(--text-dim)',
                    textTransform: 'uppercase',
                    letterSpacing: 0.5,
                    padding: '10px 20px 0',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                  }}
                >
                  <span style={{
                    fontFamily: 'var(--font-mono)',
                    color: 'var(--text-primary)',
                    fontSize: 12,
                    textTransform: 'none',
                    fontWeight: 400,
                  }}>
                    {selectedFile.name}
                  </span>
                </div>
                <pre
                  style={{
                    background: '#0d1117',
                    border: '1px solid rgba(148,163,184,0.1)',
                    borderRadius: 8,
                    margin: '8px 16px 16px',
                    padding: 16,
                    fontSize: 12,
                    fontFamily: 'var(--font-mono)',
                    color: '#c9d1d9',
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-word',
                    lineHeight: 1.6,
                  }}
                >
                  {selectedFile.content}
                </pre>
              </>
            ) : (
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  height: '100%',
                  color: 'var(--text-dim)',
                  fontSize: 13,
                  gap: 8,
                }}
              >
                <div style={{ fontSize: 32, opacity: 0.2 }}>📂</div>
                <div>点击左侧文件查看内容</div>
                <div style={{ fontSize: 11, color: 'var(--text-dim)', opacity: 0.6 }}>
                  {skill.name} · {skill.version} · {sc.label}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Confirm Delete Modal */}
      {confirmDelete && (
        <>
          <div
            onClick={() => setConfirmDelete(false)}
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
            <div style={{ fontSize: 40, marginBottom: 12 }}>⚠️</div>
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
              确定要删除 Skill「{skill.name}」吗？这将同时删除对应的文件目录，此操作不可撤销。
            </div>
            <div
              style={{ display: 'flex', gap: 10, justifyContent: 'center' }}
            >
              <button
                onClick={() => setConfirmDelete(false)}
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
                onClick={handleDelete}
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
                {deleting ? '删除中...' : '确认删除'}
              </button>
            </div>
          </div>
        </>
      )}

      {/* Toast */}
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
          {toast.message}
        </div>
      )}
    </>
  );
}

// ── Helpers ──

function MetaItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span
        style={{
          fontSize: 11,
          color: 'var(--text-dim)',
          display: 'block',
          marginBottom: 2,
        }}
      >
        {label}
      </span>
      <span
        style={{
          fontSize: 13,
          color: 'var(--text-primary)',
          fontFamily: 'var(--font-mono)',
          wordBreak: 'break-all',
        }}
      >
        {value}
      </span>
      
    </div>
  );
}

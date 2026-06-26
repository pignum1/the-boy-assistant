/** 工作空间文件面板：树形目录 + 上传 + 预览 + 删除 */
import { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { sessionsApi, API_BASE } from '../../shared/api/sessions';

/** Encode path for URL, preserving / separators (for subdirectory paths) */
function encodePath(path: string): string {
  return path.split('/').map(part => encodeURIComponent(part)).join('/');
}

interface FileItem {
  name: string;
  path: string;
  size: number;
  modified: string;
  is_dir: boolean;
  children?: FileItem[] | null;
}

interface PreviewFile {
  name: string;
  content: string;
  mime: string;
  size?: number;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
}

function fileIcon(name: string, isDir?: boolean): string {
  if (isDir) return '📁';
  const ext = name.split('.').pop()?.toLowerCase() || '';
  const map: Record<string, string> = {
    md: '📝', txt: '📄', py: '🐍', ts: '🔷', tsx: '⚛️', js: '🟨', json: '📋',
    yaml: '⚙️', yml: '⚙️', html: '🌐', css: '🎨', sql: '🗄️',
    png: '🖼️', jpg: '🖼️', jpeg: '🖼️', svg: '🎯', pdf: '📕',
    zip: '📦', tar: '📦', gz: '📦',
  };
  return map[ext] || '📄';
}

interface Props { sessionId: string; workspacePath?: string; }

export function WorkspacePanel({ sessionId, workspacePath }: Props) {
  const [items, setItems] = useState<FileItem[]>([]);
  const [expandedDirs, setExpandedDirs] = useState<Set<string>>(new Set());
  const [uploading, setUploading] = useState(false);
  const [previewFile, setPreviewFile] = useState<PreviewFile | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; file: FileItem } | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<FileItem | null>(null);
  const [deleting, setDeleting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadDir = async (subPath: string = '') => {
    try {
      const data = await sessionsApi.listFiles(sessionId, subPath);
      setItems(data.items || []);
    } catch { /* ignore */ }
  };

  useEffect(() => { loadDir(''); }, [sessionId]);

  const toggleDir = async (item: FileItem) => {
    if (!item.is_dir) return;
    const key = item.path;
    if (expandedDirs.has(key)) {
      setExpandedDirs(prev => { const s = new Set(prev); s.delete(key); return s; });
    } else {
      if (!item.children) {
        try {
          const data = await sessionsApi.listFiles(sessionId, item.path);
          item.children = data.items || [];
        } catch { item.children = []; }
      }
      setExpandedDirs(prev => new Set(prev).add(key));
      setItems([...items]); // trigger re-render
    }
  };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]; if (!file) return;
    setUploading(true);
    try { await sessionsApi.uploadFile(sessionId, file); await loadDir(''); }
    catch (err) { alert('上传失败: ' + String(err)); }
    finally { setUploading(false); if (fileInputRef.current) fileInputRef.current.value = ''; }
  };

  const handleDelete = async () => {
    if (!deleteConfirm) return;
    setDeleting(true);
    try { await sessionsApi.deleteFile(sessionId, deleteConfirm.path); await loadDir(''); }
    catch (err) { alert('删除失败: ' + String(err)); }
    finally { setDeleting(false); setDeleteConfirm(null); }
  };

  const handlePreview = async (file: FileItem) => {
    const ext = file.name.split('.').pop()?.toLowerCase() || '';
    const textExts = new Set(['md','txt','py','ts','tsx','js','jsx','json','yaml','yml','html','css','sql','sh','xml','csv','env','ini','cfg','toml','rs','go']);
    if (!textExts.has(ext)) { window.open(`${API_BASE}/api/v1/sessions/${sessionId}/workspace/files/${encodePath(file.path)}`, '_blank'); return; }
    setPreviewLoading(true);
    try {
      const data = await sessionsApi.getFileContent(sessionId, file.path);
      if (data.content !== undefined) setPreviewFile({ name: file.name, content: data.content || '(空文件)', mime: data.mime_type, size: file.size });
    } catch (err) { alert('预览失败: ' + String(err)); }
    finally { setPreviewLoading(false); }
  };

  const handleContextMenu = (e: React.MouseEvent, file: FileItem) => {
    e.preventDefault(); e.stopPropagation();
    setContextMenu({ x: e.clientX, y: e.clientY, file });
  };

  const renderTree = (items: FileItem[], depth: number = 0) => {
    return items.map((item) => (
      <div key={item.path}>
        <div
          onClick={() => item.is_dir ? toggleDir(item) : handlePreview(item)}
          onContextMenu={(e) => handleContextMenu(e, item)}
          style={treeItemStyle(depth)}
          title={item.is_dir ? '点击展开/折叠' : `点击预览 ${item.name}`}
        >
          <span style={{ width: 16, fontSize: 10, textAlign: 'center', flexShrink: 0 }}>
            {item.is_dir ? (expandedDirs.has(item.path) ? '▼' : '▶') : ''}
          </span>
          <span style={{ fontSize: 14, flexShrink: 0 }}>{fileIcon(item.name, item.is_dir)}</span>
          <span style={{ flex: 1, fontSize: 11.5, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--text-primary)' }}>
            {item.name}
          </span>
          {!item.is_dir && <span style={{ fontSize: 9, color: 'var(--text-dim)', flexShrink: 0 }}>{formatSize(item.size)}</span>}
        </div>
        {item.is_dir && expandedDirs.has(item.path) && item.children && (
          <div>{renderTree(item.children, depth + 1)}</div>
        )}
      </div>
    ));
  };

  return (
    <div style={panelStyle} onClick={() => setContextMenu(null)}>
      <div style={panelHeaderStyle}>
        <span style={{ fontWeight: 600, fontSize: 12 }}>📁 文件</span>
        <span style={{ fontSize: 10, color: 'var(--text-dim)', marginLeft: 'auto' }}>{items.length}</span>
        <label onClick={(e) => e.stopPropagation()} style={{ background: 'none', border: 'none', color: 'var(--gold-400)', fontSize: 12, cursor: 'pointer', padding: '0 4px', fontWeight: 700, borderRadius: 4 }} title="上传文件">
          {uploading ? '⏳' : '⬆'}
          <input ref={fileInputRef} type="file" style={{ display: 'none' }} onChange={handleUpload} />
        </label>
      </div>
      <div style={fileListStyle}>
        {items.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 20, color: 'var(--text-dim)', fontSize: 11 }}>📭 拖拽或点击上传</div>
        ) : renderTree(items)}
      </div>

      {/* Preview Modal */}
      {previewFile && (
        <>
          <div onClick={() => setPreviewFile(null)} style={overlayStyle} />
          <div style={previewModalStyle}>
            <div style={previewHeaderStyle}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 700, fontSize: 15 }}>{previewFile.name.endsWith('.md') ? '📝' : '📄'} {previewFile.name}</div>
                {previewFile.size !== undefined && <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 2 }}>{formatSize(previewFile.size)}</div>}
              </div>
              <button onClick={() => setPreviewFile(null)} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', fontSize: 18, cursor: 'pointer' }}>✕</button>
            </div>
            <div style={{ flex: 1, overflow: 'auto', padding: 0, minHeight: 0 }}>
              {previewFile.name.endsWith('.md') ? (
                <div className="markdown-body" style={{ padding: '20px 28px', lineHeight: 1.7 }}>
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{previewFile.content}</ReactMarkdown>
                </div>
              ) : (
                <pre style={{ background: '#0d1117', margin: 0, fontFamily: 'var(--font-mono)', fontSize: 12, lineHeight: 1.6, color: 'var(--text-primary)', overflow: 'auto', whiteSpace: 'pre', padding: '16px 20px', minHeight: 200 }}><code>{previewFile.content}</code></pre>
              )}
            </div>
          </div>
        </>
      )}
      {previewLoading && (
        <div style={{ position: 'fixed', top: 20, left: '50%', transform: 'translateX(-50%)', zIndex: 500, background: 'var(--bg-card)', padding: '8px 16px', borderRadius: 8, border: '1px solid var(--border-subtle)', fontSize: 12, color: 'var(--text-muted)' }}>加载预览...</div>
      )}

      {/* Delete confirmation */}
      {deleteConfirm && (
        <>
          <div onClick={() => setDeleteConfirm(null)} style={overlayStyle} />
          <div style={modalStyle}>
            <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>确认删除？</div>
            <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 6 }}>{fileIcon(deleteConfirm.name, deleteConfirm.is_dir)} {deleteConfirm.name}</div>
            <div style={{ fontSize: 11, color: 'var(--text-dim)', marginBottom: 20 }}>{deleteConfirm.is_dir ? '将删除此目录及所有内容' : `大小: ${formatSize(deleteConfirm.size)}`}。不可恢复。</div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
              <button onClick={() => setDeleteConfirm(null)} style={btnSecStyle}>取消</button>
              <button onClick={handleDelete} disabled={deleting} style={{ ...btnPriStyle, background: 'var(--red-500)' }}>{deleting ? '删除中...' : '确认删除'}</button>
            </div>
          </div>
        </>
      )}

      {/* Context Menu */}
      {contextMenu && (
        <>
          <div style={{ position: 'fixed', inset: 0, zIndex: 402 }} onClick={() => setContextMenu(null)} />
          <div style={{ position: 'fixed', left: contextMenu.x, top: contextMenu.y, zIndex: 403, background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', borderRadius: 8, boxShadow: '0 8px 24px rgba(0,0,0,0.4)', padding: '6px 0', minWidth: 160 }}>
            {!contextMenu.file.is_dir && <div onClick={() => { handlePreview(contextMenu.file); setContextMenu(null); }} style={menuItemStyle}>👁️ 预览</div>}
            <div onClick={() => { window.open(`${API_BASE}/api/v1/sessions/${sessionId}/workspace/files/${encodePath(contextMenu.file.path)}`, '_blank'); setContextMenu(null); }} style={menuItemStyle}>🔗 打开</div>
            <div style={{ height: 1, background: 'var(--border-subtle)', margin: '4px 0' }} />
            <div onClick={() => { setDeleteConfirm(contextMenu.file); setContextMenu(null); }} style={{ ...menuItemStyle, color: 'var(--red-400)' }}>🗑️ 删除</div>
          </div>
        </>
      )}
    </div>
  );
}

const panelStyle: React.CSSProperties = { display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden' };
const panelHeaderStyle: React.CSSProperties = { display: 'flex', alignItems: 'center', gap: 6, padding: '8px 10px', borderBottom: '1px solid var(--border-subtle)', flexShrink: 0 };
const fileListStyle: React.CSSProperties = { flex: 1, overflowY: 'auto', padding: 4 };
const treeItemStyle = (depth: number): React.CSSProperties => ({
  display: 'flex', alignItems: 'center', gap: 4, padding: '4px 8px', paddingLeft: 8 + depth * 14,
  borderRadius: 4, cursor: 'pointer', transition: 'background 0.1s', fontSize: 12,
});
const overlayStyle: React.CSSProperties = { position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 400 };
const previewModalStyle: React.CSSProperties = {
  position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%, -50%)',
  width: '80vw', maxWidth: 900, height: '85vh', zIndex: 401,
  background: 'var(--bg-base)', border: '1px solid var(--border-subtle)',
  borderRadius: 16, display: 'flex', flexDirection: 'column',
  boxShadow: '0 24px 80px rgba(0,0,0,0.5)', overflow: 'hidden',
};
const previewHeaderStyle: React.CSSProperties = { padding: '10px 16px', borderBottom: '1px solid var(--border-subtle)', display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0 };
const modalStyle: React.CSSProperties = {
  position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', zIndex: 501,
  background: 'var(--bg-base)', border: '1px solid var(--border-subtle)', borderRadius: 12,
  padding: '20px 24px', minWidth: 340, boxShadow: '0 24px 80px rgba(0,0,0,0.5)',
};
const menuItemStyle: React.CSSProperties = { padding: '8px 16px', fontSize: 13, cursor: 'pointer', color: 'var(--text-primary)' };
const btnSecStyle: React.CSSProperties = { padding: '8px 16px', borderRadius: 8, background: 'var(--bg-card)', border: '1px solid var(--border-medium)', color: 'var(--text-secondary)', fontSize: 13, cursor: 'pointer' };
const btnPriStyle: React.CSSProperties = { padding: '8px 16px', borderRadius: 8, border: 'none', color: 'white', fontSize: 13, fontWeight: 500, cursor: 'pointer' };

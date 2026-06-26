/** 文件目录树选择器 */
import { useState, useEffect } from 'react';

interface DirEntry { name: string; path: string; is_empty: boolean; }
interface TreeNode extends DirEntry { children?: TreeNode[]; expanded?: boolean; loading?: boolean; }

interface Props {
  selectedPath: string;
  onSelect: (path: string) => void;
  onClear: () => void;
}

const API = (import.meta as any).env?.VITE_API_URL || 'http://localhost:8000';

export function DirectoryPicker({ selectedPath, onSelect, onClear }: Props) {
  const [open, setOpen] = useState(false);
  const [roots, setRoots] = useState<TreeNode[]>([]);
  const [loading, setLoading] = useState(false);
  const [currentPath, setCurrentPath] = useState('');
  const [pathInput, setPathInput] = useState('');

  const fetchChildren = async (path: string): Promise<TreeNode[]> => {
    try {
      const res = await fetch(`${API}/api/v1/sessions/workspace/dirs?path=${encodeURIComponent(path)}`);
      if (!res.ok) return [];
      const data = await res.json();
      return (data.directories || []).map((d: DirEntry) => ({ ...d, children: undefined, expanded: false }));
    } catch { return []; }
  };

  const handleOpen = async () => {
    setOpen(true);
    setPathInput(selectedPath || '');
    setLoading(true);
    const startPath = selectedPath || '';
    const home = await fetchChildren(startPath);
    setRoots(home.map(n => ({ ...n, children: undefined, expanded: false })));
    setCurrentPath(startPath);
    setLoading(false);
  };

  const toggleExpand = async (node: TreeNode, parentPath: string) => {
    if (node.expanded) {
      node.expanded = false;
      node.children = undefined;
      setRoots([...roots]);
      return;
    }
    node.loading = true;
    setRoots([...roots]);
    const children = await fetchChildren(node.path);
    node.children = children;
    node.expanded = true;
    node.loading = false;
    setRoots([...roots]);
  };

  const handlePathJump = async (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && pathInput.trim()) {
      setLoading(true);
      const target = pathInput.trim();
      const children = await fetchChildren(target);
      setRoots(children.map(n => ({ ...n, children: undefined, expanded: false })));
      setCurrentPath(target);
      onSelect(target);  // 直接选中输入的路径
      setLoading(false);
    }
  };

  const handleDoubleClick = (nodePath: string) => {
    onSelect(nodePath);
    setCurrentPath(nodePath);
  };

  const renderNode = (node: TreeNode, depth: number) => {
    const isSelected = node.path === selectedPath;
    return (
      <div key={node.path}>
        <div
          style={treeItemStyle(depth, isSelected)}
          onClick={() => toggleExpand(node, '')}
          onDoubleClick={(e) => { e.stopPropagation(); handleDoubleClick(node.path); }}
        >
          <span style={{ width: 16, fontSize: 10, flexShrink: 0, textAlign: 'center' }}>
            {node.loading ? '⏳' : node.expanded ? '▼' : '▶'}
          </span>
          <span style={{ fontSize: 13, flexShrink: 0 }}>
            {node.expanded ? '📂' : '📁'}
          </span>
          <span style={{
            flex: 1, fontSize: 12.5, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            color: isSelected ? 'var(--gold-400)' : 'var(--text-primary)', fontWeight: isSelected ? 600 : 400,
          }}>
            {node.name}
          </span>
          {isSelected && <span style={{ fontSize: 10, color: 'var(--gold-400)' }}>✓</span>}
        </div>
        {node.expanded && node.children && (
          <div>
            {node.children.length === 0
              ? <div style={{ paddingLeft: (depth + 1) * 20 + 24, fontSize: 11, color: 'var(--text-dim)', paddingTop: 2 }}>空目录</div>
              : node.children.map(child => renderNode(child, depth + 1))
            }
          </div>
        )}
      </div>
    );
  };

  return (
    <>
      <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
        {selectedPath ? (
          <div style={pathDisplayStyle} title={selectedPath}>📂 {selectedPath}</div>
        ) : (
          <div style={defaultPathStyle}>默认路径</div>
        )}
        <button onClick={handleOpen} style={browseBtnStyle}>📂 浏览...</button>
        {selectedPath && <button onClick={onClear} style={clearBtnStyle} title="使用默认">✕</button>}
      </div>

      {open && (
        <>
          <div onClick={() => setOpen(false)} style={overlayStyle} />
          <div style={dialogStyle}>
            <div style={dialogHeaderStyle}>
              <span>📂 选择目录</span>
              <button onClick={() => setOpen(false)} style={closeBtnStyle}>✕</button>
            </div>
            <input
              style={pathInputStyle}
              value={pathInput}
              onChange={(e) => setPathInput(e.target.value)}
              onKeyDown={handlePathJump}
              placeholder="输入路径，回车直接跳转（如 /Users/xxx/projects）"
            />
            {loading ? (
              <div style={{ textAlign: 'center', padding: 30, color: 'var(--text-dim)' }}>加载中...</div>
            ) : (
              <div style={treeContainerStyle}>
                {roots.length === 0 ? (
                  <div style={{ textAlign: 'center', padding: 20, color: 'var(--text-dim)' }}>无可用目录</div>
                ) : (
                  roots.map(n => renderNode(n, 0))
                )}
              </div>
            )}
            <div style={{ display: 'flex', gap: 8, justifyContent: 'space-between', marginTop: 8 }}>
              <button onClick={() => { onClear(); setOpen(false); }} style={defaultBtnStyle}>使用默认路径</button>
              <div style={{ fontSize: 11, color: 'var(--text-dim)', alignSelf: 'center', flex: 1, textAlign: 'center', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {selectedPath || currentPath || '~'}
              </div>
              <button onClick={() => { if (selectedPath || currentPath) onSelect(selectedPath || currentPath); setOpen(false); }} style={confirmBtnStyle}>确定</button>
            </div>
          </div>
        </>
      )}
    </>
  );
}

const pathDisplayStyle: React.CSSProperties = {
  flex: 1, padding: '8px 12px', borderRadius: 8, fontSize: 11,
  background: 'var(--bg-elevated)', border: '1px solid var(--border-medium)',
  color: 'var(--text-primary)', fontFamily: 'var(--font-mono)',
  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
};
const defaultPathStyle: React.CSSProperties = {
  flex: 1, padding: '8px 12px', borderRadius: 8, fontSize: 11,
  background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)',
  color: 'var(--text-dim)',
};
const browseBtnStyle: React.CSSProperties = {
  padding: '8px 14px', borderRadius: 8, fontSize: 12, whiteSpace: 'nowrap',
  background: 'var(--bg-card)', border: '1px solid var(--border-medium)',
  color: 'var(--text-secondary)', cursor: 'pointer',
};
const clearBtnStyle: React.CSSProperties = {
  width: 32, height: 34, borderRadius: 8, fontSize: 14,
  background: 'none', border: '1px solid var(--border-subtle)',
  color: 'var(--text-dim)', cursor: 'pointer',
};
const overlayStyle: React.CSSProperties = {
  position: 'fixed', inset: 0, zIndex: 300, background: 'rgba(0,0,0,0.4)',
};
const dialogStyle: React.CSSProperties = {
  position: 'fixed', top: '8%', left: '50%', transform: 'translateX(-50%)',
  zIndex: 301, width: 520, maxHeight: '80vh',
  background: 'var(--bg-base)', border: '1px solid var(--border-subtle)',
  borderRadius: 14, padding: 20, display: 'flex', flexDirection: 'column',
  boxShadow: '0 24px 80px rgba(0,0,0,0.5)',
};
const dialogHeaderStyle: React.CSSProperties = {
  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
  marginBottom: 8, fontSize: 15, fontWeight: 600,
};
const closeBtnStyle: React.CSSProperties = {
  background: 'none', border: 'none', color: 'var(--text-muted)', fontSize: 18, cursor: 'pointer',
};
const pathInputStyle: React.CSSProperties = {
  width: '100%', padding: '8px 12px', borderRadius: 8, marginBottom: 8,
  background: 'var(--bg-elevated)', border: '1px solid var(--border-medium)',
  color: 'var(--text-primary)', fontSize: 13, fontFamily: 'var(--font-mono)',
  outline: 'none',
};
const treeContainerStyle: React.CSSProperties = {
  flex: 1, overflowY: 'auto', maxHeight: '55vh',
  border: '1px solid var(--border-subtle)', borderRadius: 8, padding: 6,
};
const treeItemStyle = (depth: number, selected: boolean): React.CSSProperties => ({
  display: 'flex', alignItems: 'center', gap: 4, padding: '5px 8px', paddingLeft: depth * 16 + 8,
  borderRadius: 4, cursor: 'pointer', transition: 'background 0.1s',
  background: selected ? 'var(--gold-bg)' : 'transparent',
});
const defaultBtnStyle: React.CSSProperties = {
  padding: '8px 16px', borderRadius: 8, fontSize: 12, cursor: 'pointer',
  background: 'var(--bg-card)', border: '1px solid var(--border-medium)',
  color: 'var(--text-secondary)',
};
const confirmBtnStyle: React.CSSProperties = {
  padding: '8px 20px', borderRadius: 8, fontSize: 12, fontWeight: 500, cursor: 'pointer',
  background: 'linear-gradient(135deg, var(--gold-500), #d97706)',
  border: 'none', color: '#0a0f1e',
};

/** 抽屉宿主：右侧多面板堆叠，每面板可独立拖拽宽度

支持：
- 最多 3 个抽屉同时打开
- 每个抽屉独立宽度（20%-60%）
- Esc 键关闭全部，点击遮罩关闭全部
- 拖拽左侧边缘调整宽度
*/
import { useCallback, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import type { DrawerKind, DrawerState } from '../../types/state';

const DRAWER_LABELS: Record<string, string> = {
  plan: '任务计划',
  artifacts: '产物',
  team: '团队',
  workflow: '工作流进度',
};

interface Props {
  openDrawers: DrawerState[];
  onClose: (kind: DrawerKind) => void;
  onCloseAll: () => void;
  onWidthChange: (kind: DrawerKind, width: number) => void;
  children: ReactNode;
}

export function DrawerHost({ openDrawers, onClose, onCloseAll, onWidthChange, children }: Props) {
  // Esc 关闭
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && openDrawers.length > 0) {
        if (openDrawers.length === 1) {
          onClose(openDrawers[0].kind);
        } else {
          onCloseAll();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [openDrawers, onClose, onCloseAll]);

  if (openDrawers.length === 0) return null;

  return (
    <>
      {/* 遮罩层 */}
      <div
        onClick={onCloseAll}
        style={{
          position: 'fixed', inset: 0, zIndex: 9,
          background: 'rgba(0,0,0,0.08)',
        }}
      />
      {/* 抽屉堆叠：fixed 固定在右侧，宽度基于视口（vw），避免百分比相对
          auto 宽度父容器导致的循环收缩（drawer 永远塌缩到 min-width） */}
      <div style={{
        display: 'flex', position: 'fixed', top: 0, right: 0, bottom: 0,
        height: '100%', zIndex: 10,
      }}>
        {openDrawers.map((drawer, i) => (
          <DrawerPanel
            key={drawer.kind}
            kind={drawer.kind}
            width={drawer.width}
            isLast={i === openDrawers.length - 1}
            onClose={() => onClose(drawer.kind)}
            onWidthChange={(w) => onWidthChange(drawer.kind, w)}
          >
            {children}
          </DrawerPanel>
        ))}
      </div>
    </>
  );
}

/** 单个抽屉面板 */
function DrawerPanel({
  kind, width, isLast, onClose, onWidthChange, children,
}: {
  kind: DrawerKind;
  width: number;
  isLast: boolean;
  onClose: () => void;
  onWidthChange: (w: number) => void;
  children: ReactNode;
}) {
  const draggingRef = useRef(false);
  const startXRef = useRef(0);
  const startWidthRef = useRef(width);
  const [dragging, setDragging] = useState(false);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    draggingRef.current = true;
    setDragging(true);
    startXRef.current = e.clientX;
    startWidthRef.current = width;
    e.preventDefault();
  }, [width]);

  useEffect(() => {
    function onMouseMove(e: MouseEvent) {
      if (!draggingRef.current) return;
      const totalWidth = window.innerWidth;
      const deltaPercent = ((startXRef.current - e.clientX) / totalWidth) * 100;
      const next = Math.max(20, Math.min(60, startWidthRef.current + deltaPercent));
      onWidthChange(next);
    }
    function onMouseUp() {
      draggingRef.current = false;
      setDragging(false);
    }
    if (dragging) {
      window.addEventListener('mousemove', onMouseMove);
      window.addEventListener('mouseup', onMouseUp);
      return () => {
        window.removeEventListener('mousemove', onMouseMove);
        window.removeEventListener('mouseup', onMouseUp);
      };
    }
  }, [dragging, onWidthChange, width]);

  const title = DRAWER_LABELS[kind] || kind;

  return (
    <div
      style={{
        width: `${width}vw`,
        minWidth: 280,
        maxWidth: '80vw',
        height: '100%',
        borderLeft: '1px solid var(--border-subtle)',
        background: 'var(--bg-elevated)',
        display: 'flex',
        flexDirection: 'column',
        position: 'relative',
        userSelect: dragging ? 'none' : 'auto',
        boxShadow: '-8px 0 24px rgba(0,0,0,0.12)',
      }}
    >
      {/* 拖拽手柄 */}
      <div
        onMouseDown={handleMouseDown}
        style={{
          position: 'absolute',
          left: 0,
          top: 0,
          bottom: 0,
          width: 6,
          cursor: 'col-resize',
          zIndex: 20,
          background: dragging ? 'var(--gold-border)' : 'transparent',
          transition: 'background 0.15s',
        }}
        onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--gold-border)')}
        onMouseLeave={(e) => { if (!dragging) e.currentTarget.style.background = 'transparent'; }}
      />

      {/* 头部 */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '10px 14px', borderBottom: '1px solid var(--border-subtle)',
        flexShrink: 0,
      }}>
        <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
          {title}
        </span>
        <button
          onClick={onClose}
          style={{
            background: 'none', border: 'none', cursor: 'pointer',
            fontSize: 16, color: 'var(--text-muted)', padding: '2px 6px',
          }}
        >
          ✕
        </button>
      </div>

      {/* 内容 */}
      <div style={{ flex: 1, overflow: 'auto' }}>
        {children}
      </div>
    </div>
  );
}

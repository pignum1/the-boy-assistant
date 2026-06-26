/** 通用分页组件，供所有资源列表页面使用 */
import type { CSSProperties } from 'react';

interface Props {
  skip: number;
  limit: number;
  total: number;
  onPageChange: (skip: number, limit: number) => void;
}

export function Pagination({ skip, limit, total, onPageChange }: Props) {
  const currentPage = Math.floor(skip / limit) + 1;
  const totalPages = Math.max(1, Math.ceil(total / limit));
  const start = total === 0 ? 0 : skip + 1;
  const end = Math.min(skip + limit, total);

  const goTo = (page: number) => {
    if (page < 1 || page > totalPages) return;
    onPageChange((page - 1) * limit, limit);
  };

  const pageNumbers: number[] = [];
  for (let i = Math.max(1, currentPage - 2); i <= Math.min(totalPages, currentPage + 2); i++) {
    pageNumbers.push(i);
  }

  const btnStyle = (active: boolean): CSSProperties => ({
    padding: '4px 10px',
    border: `1px solid ${active ? 'var(--gold-border)' : 'var(--border-subtle)'}`,
    borderRadius: 4,
    background: active ? 'var(--gold-bg)' : 'transparent',
    color: active ? 'var(--gold-400)' : 'var(--text-secondary)',
    fontSize: 12,
    cursor: active ? 'default' : 'pointer',
    fontFamily: 'var(--font-mono)',
  });

  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '10px 0', fontSize: 12, color: 'var(--text-muted)',
      borderTop: '1px solid var(--border-subtle)', marginTop: 16,
    }}>
      <span>
        共 <strong style={{ color: 'var(--text-primary)' }}>{total}</strong> 条
        {total > 0 && <> · 显示 {start}–{end}</>}
      </span>
      <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
        <button style={btnStyle(false)} onClick={() => goTo(1)} disabled={currentPage <= 1}>
          ⏮
        </button>
        <button style={btnStyle(false)} onClick={() => goTo(currentPage - 1)} disabled={currentPage <= 1}>
          ◀
        </button>
        {pageNumbers[0] > 1 && <span style={{ padding: '0 4px', color: 'var(--text-dim)' }}>…</span>}
        {pageNumbers.map(p => (
          <button key={p} style={btnStyle(p === currentPage)} onClick={() => goTo(p)}>
            {p}
          </button>
        ))}
        {pageNumbers[pageNumbers.length - 1] < totalPages && <span style={{ padding: '0 4px', color: 'var(--text-dim)' }}>…</span>}
        <button style={btnStyle(false)} onClick={() => goTo(currentPage + 1)} disabled={currentPage >= totalPages}>
          ▶
        </button>
        <button style={btnStyle(false)} onClick={() => goTo(totalPages)} disabled={currentPage >= totalPages}>
          ⏭
        </button>
      </div>
    </div>
  );
}

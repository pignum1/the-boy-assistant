// ── Shared styles for resource pages ──

export const btnPrimaryStyle: React.CSSProperties = {
  background: 'var(--gold-500)',
  color: '#0a0f1e',
  border: 'none',
  borderRadius: 8,
  padding: '8px 18px',
  fontSize: 13,
  fontWeight: 600,
  cursor: 'pointer',
  display: 'flex',
  alignItems: 'center',
  gap: 6,
};

export const btnSecondaryStyle: React.CSSProperties = {
  background: 'var(--bg-card)',
  color: 'var(--text-secondary)',
  border: '1px solid var(--border-medium)',
  borderRadius: 8,
  padding: '8px 18px',
  fontSize: 13,
  cursor: 'pointer',
};

export const cardStyle: React.CSSProperties = {
  background: 'var(--bg-card)',
  border: '1px solid var(--border-subtle)',
  borderRadius: 14,
  padding: '20px 22px',
  cursor: 'pointer',
  transition: 'all 0.2s ease',
};

export const cardHeaderStyle: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  marginBottom: 14,
};

export const iconStyle: React.CSSProperties = {
  width: 42, height: 42, borderRadius: 11,
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  fontSize: 20,
};

export const cardNameStyle: React.CSSProperties = {
  fontSize: 15, fontWeight: 600,
  color: 'var(--text-primary)',
  marginBottom: 6,
};

export const cardDescStyle: React.CSSProperties = {
  fontSize: 12, color: 'var(--text-muted)',
  lineHeight: 1.6, marginBottom: 12,
  overflow: 'hidden', textOverflow: 'ellipsis',
  whiteSpace: 'nowrap' as const,
};

export const cardFooterStyle: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
};

export const cardMetaStyle: React.CSSProperties = {
  fontSize: 11,
  color: 'var(--text-dim)',
  display: 'flex',
  gap: 12,
};

export const actionBtnStyle: React.CSSProperties = {
  width: 28, height: 28, borderRadius: 6,
  border: '1px solid var(--border-medium)',
  background: 'var(--bg-base)',
  color: 'var(--text-muted)',
  cursor: 'pointer',
  fontSize: 12,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
};

export const statusBadgeStyle: React.CSSProperties = {
  fontSize: 10, fontWeight: 500,
  padding: '3px 8px', borderRadius: 6,
};

export const tagsStyle: React.CSSProperties = {
  display: 'flex', gap: 5, flexWrap: 'wrap' as const,
  marginBottom: 14,
};

export const tagStyle: React.CSSProperties = {
  fontSize: 10, fontWeight: 500,
  padding: '3px 9px', borderRadius: 6,
};

export const searchInputStyle: React.CSSProperties = {
  flex: 1,
  padding: '9px 14px',
  fontSize: 13,
  background: 'var(--bg-card)',
  border: '1px solid var(--border-medium)',
  borderRadius: 10,
  color: 'var(--text-primary)',
  outline: 'none',
};

export const overlayStyle: React.CSSProperties = {
  position: 'fixed' as const,
  inset: 0,
  background: 'rgba(0,0,0,0.5)',
  zIndex: 100,
  backdropFilter: 'blur(4px)',
};

export const panelStyle: React.CSSProperties = {
  position: 'fixed' as const,
  top: 0,
  right: 0,
  width: 520,
  height: '100vh',
  background: 'var(--bg-base)',
  borderLeft: '1px solid var(--border-subtle)',
  zIndex: 101,
  display: 'flex',
  flexDirection: 'column',
  boxShadow: '-16px 0 48px rgba(0,0,0,0.4)',
};

export const panelHeaderStyle: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  padding: '20px 24px',
  borderBottom: '1px solid var(--border-subtle)',
  flexShrink: 0,
};

export const panelFooterStyle: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'flex-end',
  gap: 8,
  padding: '16px 24px',
  borderTop: '1px solid var(--border-subtle)',
  flexShrink: 0,
};

export const closeBtnStyle: React.CSSProperties = {
  width: 32, height: 32, borderRadius: 8,
  border: '1px solid var(--border-medium)',
  background: 'var(--bg-card)',
  color: 'var(--text-muted)',
  cursor: 'pointer',
  fontSize: 14,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
};

export const formLabelStyle: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 600,
  color: 'var(--text-dim)',
  textTransform: 'uppercase' as const,
  letterSpacing: 0.5,
  marginBottom: 5,
  display: 'block',
};

export const formInputStyle: React.CSSProperties = {
  width: '100%',
  padding: '9px 12px',
  fontSize: 13,
  background: 'var(--bg-card)',
  border: '1px solid var(--border-medium)',
  borderRadius: 8,
  color: 'var(--text-primary)',
  outline: 'none',
  fontFamily: 'inherit',
};

export const capItemStyle: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  padding: '9px 12px',
  background: 'var(--bg-card)',
  border: '1px solid var(--border-subtle)',
  borderRadius: 8,
};

export const toggleStyle: React.CSSProperties = {
  width: 36, height: 20, borderRadius: 10,
  position: 'relative' as const,
  transition: 'background 0.2s',
};

export const toggleDotStyle: React.CSSProperties = {
  position: 'absolute',
  top: 2,
  width: 16, height: 16, borderRadius: '50%',
  background: '#fff',
  transition: 'left 0.2s',
};

// ── Helper ──

export function getProviderColorKey(color?: string): string {
  const match = color?.match(/var\(--(\w+)-\d+\)/);
  return match ? match[1] : 'gold';
}

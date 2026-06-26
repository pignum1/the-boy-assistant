import { useState, useMemo } from 'react';

// ---- Props Interface ----
interface {ComponentName}Props {
  /** 数据 ID */
  id?: string;
  /** 初始数据 */
  initialValue?: string;
  /** 是否加载中 */
  loading?: boolean;
  /** 值变更回调 */
  onChange?: (value: string) => void;
}

// ---- Component ----
export function {ComponentName}({
  id,
  initialValue = '',
  loading = false,
  onChange,
}: {ComponentName}Props) {
  const [value, setValue] = useState(initialValue);
  const [error, setError] = useState<string | null>(null);

  const handleChange = (newValue: string) => {
    setValue(newValue);
    setError(null);
    onChange?.(newValue);
  };

  // ---- States ----

  if (loading) {
    return (
      <div data-testid="{component-name}-loading" style={{ padding: 20, textAlign: 'center' }}>
        <div style={{ opacity: 0.5 }}>加载中...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div data-testid="{component-name}-error" style={{ padding: 20, textAlign: 'center' }}>
        <div style={{ color: 'var(--red-400)' }}>{error}</div>
        <button onClick={() => setError(null)}>重试</button>
      </div>
    );
  }

  // ---- Main Render ----
  return (
    <div data-testid="{component-name}" style={{ padding: 16 }}>
      <input
        data-testid="{component-name}-input"
        value={value}
        onChange={(e) => handleChange(e.target.value)}
        placeholder="请输入..."
        style={{
          width: '100%',
          padding: '8px 12px',
          borderRadius: 8,
          border: '1px solid var(--border-medium)',
          background: 'var(--bg-card)',
          color: 'var(--text-primary)',
          fontSize: 13,
          outline: 'none',
        }}
      />
    </div>
  );
}

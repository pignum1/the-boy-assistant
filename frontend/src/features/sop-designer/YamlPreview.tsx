interface YamlPreviewProps {
  yaml: string;
  errors: string[];
  onChange: (value: string) => void;
}

export function YamlPreview({ yaml, errors, onChange }: YamlPreviewProps) {
  return (
    <div style={{ borderTop: '1px solid var(--border-subtle)', background: 'var(--bg-base)' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '8px 16px',
          borderBottom: '1px solid var(--border-subtle)',
        }}
      >
        <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 0.5 }}>
          YAML 预览
        </span>
        {errors.length > 0 && (
          <span style={{ fontSize: 11, color: 'var(--red-400)' }}>{errors.length} error(s)</span>
        )}
      </div>
      <div style={{ position: 'relative' }}>
        <textarea
          style={{
            width: '100%',
            height: 140,
            padding: '10px 16px',
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            background: 'var(--bg-deep)',
            color: 'var(--green-400)',
            border: 'none',
            outline: 'none',
            resize: 'vertical' as const,
          }}
          value={yaml}
          onChange={(e) => onChange(e.target.value)}
          spellCheck={false}
        />
        {errors.length > 0 && (
          <div
            style={{
              position: 'absolute',
              top: 0,
              right: 0,
              background: 'var(--bg-card)',
              borderLeft: '1px solid var(--border-subtle)',
              borderBottom: '1px solid var(--border-subtle)',
              padding: '8px 12px',
              maxWidth: 280,
              fontSize: 11,
              color: 'var(--red-400)',
              fontFamily: 'var(--font-mono)',
            }}
          >
            {errors.map((err, i) => (
              <div key={i}>{err}</div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

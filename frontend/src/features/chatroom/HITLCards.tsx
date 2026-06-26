/**
 * HITL 卡片组件 - 三种类型：确认/输入/选择
 *
 * 状态机：pending → answering → answered
 * 操作：confirm/input/cancel
 */
import { useState } from 'react';
import { HITLOptions } from './components/shared/HITLOptions';
import type { HitlOption } from './types/state';

interface HITLCardProps {
  taskId: string;
  nodeId: string;
  nodeLabel: string;
  hitlType: 'confirm' | 'input' | 'choice';
  message?: string;
  context?: Record<string, any>;
  choices?: Array<{ value: string; label: string; description?: string }>;
  timeout?: number;
  onResponse: (response: HITLResponse) => void;
  disabled?: boolean;
}

export interface HITLResponse {
  action: 'approve' | 'reject' | 'defer';
  value?: any;
  feedback?: string;
}

export function HITLConfirmCard({
  taskId,
  nodeId,
  nodeLabel,
  message = '请确认',
  context,
  timeout = 300,
  onResponse,
  disabled = false,
}: Omit<HITLCardProps, 'hitlType' | 'choices'>) {
  const [loading, setLoading] = useState(false);

  const handleAction = async (action: 'approve' | 'reject' | 'defer') => {
    setLoading(true);
    try {
      await onResponse({ action });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={cardStyle}>
      <div style={cardHeaderStyle}>
        <span style={{ fontSize: 14 }}>👤</span>
        <span style={{ fontSize: 11, fontWeight: 500 }}>HITL · {nodeLabel}</span>
        <span style={{ fontSize: 10, color: 'var(--orange-400)', marginLeft: 'auto' }}>
          ⏸ 等待你的确认
        </span>
      </div>

      <div style={cardBodyStyle}>
        <p style={{ fontSize: 12, color: 'var(--text-primary)', marginBottom: 12 }}>
          {message}
        </p>

        {context && Object.keys(context).length > 0 && (
          <div style={contextBoxStyle}>
            {Object.entries(context).map(([key, value]) => (
              <div key={key} style={{ fontSize: 11, display: 'flex', gap: 8 }}>
                <span style={{ color: 'var(--text-dim)', minWidth: 80 }}>{key}:</span>
                <span style={{ color: 'var(--text-secondary)' }}>{String(value)}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div style={cardActionsStyle}>
        <button
          onClick={() => handleAction('reject')}
          disabled={disabled || loading}
          style={btnStyle('reject')}
        >
          {loading ? '...' : '✗ 驳回'}
        </button>
        <button
          onClick={() => handleAction('defer')}
          disabled={disabled || loading}
          style={btnStyle('defer')}
        >
          {loading ? '...' : '⏸️ 稍后处理'}
        </button>
        <button
          onClick={() => handleAction('approve')}
          disabled={disabled || loading}
          style={btnStyle('approve')}
        >
          {loading ? '...' : '✓ 批准'}
        </button>
      </div>
    </div>
  );
}

export function HITLInputCard({
  taskId,
  nodeId,
  nodeLabel,
  message = '请输入',
  context,
  timeout = 300,
  onResponse,
  disabled = false,
}: Omit<HITLCardProps, 'hitlType' | 'choices'>) {
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async () => {
    if (!input.trim()) return;
    setLoading(true);
    try {
      await onResponse({ action: 'approve', value: input });
    } finally {
      setLoading(false);
    }
  };

  const handleSkip = async () => {
    setLoading(true);
    try {
      await onResponse({ action: 'defer' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={cardStyle}>
      <div style={cardHeaderStyle}>
        <span style={{ fontSize: 14 }}>✏️</span>
        <span style={{ fontSize: 11, fontWeight: 500 }}>HITL · {nodeLabel}</span>
        <span style={{ fontSize: 10, color: 'var(--orange-400)', marginLeft: 'auto' }}>
          ⏸ 等待你的输入
        </span>
      </div>

      <div style={cardBodyStyle}>
        <p style={{ fontSize: 12, color: 'var(--text-primary)', marginBottom: 12 }}>
          {message}
        </p>

        {context && Object.keys(context).length > 0 && (
          <div style={contextBoxStyle}>
            {Object.entries(context).map(([key, value]) => (
              <div key={key} style={{ fontSize: 11, display: 'flex', gap: 8 }}>
                <span style={{ color: 'var(--text-dim)', minWidth: 80 }}>{key}:</span>
                <span style={{ color: 'var(--text-secondary)' }}>{String(value)}</span>
              </div>
            ))}
          </div>
        )}

        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={disabled || loading}
          placeholder="在此输入..."
          style={textareaStyle}
        />
      </div>

      <div style={cardActionsStyle}>
        <button
          onClick={handleSkip}
          disabled={disabled || loading}
          style={btnStyle('defer')}
        >
          {loading ? '...' : '⏭️ 跳过'}
        </button>
        <button
          onClick={handleSubmit}
          disabled={disabled || loading || !input.trim()}
          style={btnStyle('approve')}
        >
          {loading ? '...' : '✓ 提交'}
        </button>
      </div>
    </div>
  );
}

export function HITLChoiceCard({
  taskId,
  nodeId,
  nodeLabel,
  message = '请选择',
  context,
  choices = [],
  timeout = 300,
  onResponse,
  disabled = false,
}: Omit<HITLCardProps, 'hitlType'>) {
  const [selected, setSelected] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async () => {
    if (!selected) return;
    setLoading(true);
    try {
      await onResponse({ action: 'approve', value: selected });
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = async () => {
    setLoading(true);
    try {
      await onResponse({ action: 'reject' });
    } finally {
      setLoading(false);
    }
  };

  // 将 choices 映射为 HitlOption[]
  const hitlOptions: HitlOption[] = choices.map(c => ({
    label: c.label,
    value: c.value,
    description: c.description,
  }));

  return (
    <div style={cardStyle}>
      <div style={cardHeaderStyle}>
        <span style={{ fontSize: 14 }}>🔘</span>
        <span style={{ fontSize: 11, fontWeight: 500 }}>HITL · {nodeLabel}</span>
        <span style={{ fontSize: 10, color: 'var(--orange-400)', marginLeft: 'auto' }}>
          ⏸ 等待你的选择
        </span>
      </div>

      <div style={cardBodyStyle}>
        <p style={{ fontSize: 12, color: 'var(--text-primary)', marginBottom: 12 }}>
          {message}
        </p>

        {context && Object.keys(context).length > 0 && (
          <div style={contextBoxStyle}>
            {Object.entries(context).map(([key, value]) => (
              <div key={key} style={{ fontSize: 11, display: 'flex', gap: 8 }}>
                <span style={{ color: 'var(--text-dim)', minWidth: 80 }}>{key}:</span>
                <span style={{ color: 'var(--text-secondary)' }}>{String(value)}</span>
              </div>
            ))}
          </div>
        )}

        <HITLOptions
          mode="selectable"
          options={hitlOptions}
          selected={selected}
          onSelect={setSelected}
          disabled={disabled || loading}
        />
      </div>

      <div style={cardActionsStyle}>
        <button
          onClick={handleCancel}
          disabled={disabled || loading}
          style={btnStyle('reject')}
        >
          {loading ? '...' : '✗ 取消'}
        </button>
        <button
          onClick={handleSubmit}
          disabled={disabled || loading || !selected}
          style={btnStyle('approve')}
        >
          {loading ? '...' : '✓ 确认选择'}
        </button>
      </div>
    </div>
  );
}

/** 通用 HITL 卡片入口 */
export function HITLCard(props: HITLCardProps) {
  switch (props.hitlType) {
    case 'confirm':
      return <HITLConfirmCard {...props} />;
    case 'input':
      return <HITLInputCard {...props} />;
    case 'choice':
      return <HITLChoiceCard {...props} />;
    default:
      return <HITLConfirmCard {...props} hitlType="confirm" />;
  }
}

// ── Styles ──

const cardStyle: React.CSSProperties = {
  background: 'var(--bg-card)',
  border: '1px solid var(--orange-border)',
  borderRadius: 12,
  overflow: 'hidden',
};

const cardHeaderStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  padding: '10px 12px',
  background: 'var(--orange-bg)',
  borderBottom: '1px solid var(--orange-border)',
};

const cardBodyStyle: React.CSSProperties = {
  padding: 12,
};

const cardActionsStyle: React.CSSProperties = {
  display: 'flex',
  gap: 8,
  padding: '10px 12px',
  background: 'var(--bg-elevated)',
  borderTop: '1px solid var(--border-subtle)',
  justifyContent: 'flex-end',
};

const contextBoxStyle: React.CSSProperties = {
  background: 'var(--bg-deep)',
  border: '1px solid var(--border-subtle)',
  borderRadius: 8,
  padding: 8,
  marginTop: 8,
};

const textareaStyle: React.CSSProperties = {
  width: '100%',
  minHeight: 80,
  padding: '10px 12px',
  background: 'var(--bg-elevated)',
  border: '1px solid var(--border-subtle)',
  borderRadius: 8,
  fontSize: 12,
  color: 'var(--text-primary)',
  fontFamily: 'var(--font-body)',
  resize: 'vertical' as const,
  outline: 'none',
};

const btnStyle = (type: 'approve' | 'reject' | 'defer'): React.CSSProperties => ({
  padding: '8px 16px',
  borderRadius: 8,
  fontSize: 12,
  fontWeight: 500,
  cursor: 'pointer',
  border: 'none',
  opacity: 0.9,
  transition: 'all 0.15s',
  ...(type === 'approve' && {
    background: 'linear-gradient(135deg, var(--gold-500), #d97706)',
    color: '#0a0f1e',
  }),
  ...(type === 'reject' && {
    background: 'var(--red-bg)',
    color: 'var(--red-400)',
    border: '1px solid var(--red-border)',
  }),
  ...(type === 'defer' && {
    background: 'var(--bg-card)',
    color: 'var(--text-secondary)',
    border: '1px solid var(--border-medium)',
  }),
  ':hover': {
    opacity: 1,
  },
  ':disabled': {
    opacity: 0.5,
    cursor: 'not-allowed',
  },
});


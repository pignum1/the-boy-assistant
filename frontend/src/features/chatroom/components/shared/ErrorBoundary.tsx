/** 聊天室错误边界 — 防止子组件崩溃导致整个页面白屏 */

import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
  /** 自定义降级 UI */
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

const containerStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  justifyContent: 'center',
  padding: '32px 16px',
  color: 'var(--text-secondary)',
  fontFamily: 'var(--font-mono)',
  fontSize: 13,
  gap: 12,
};

const titleStyle: React.CSSProperties = {
  fontSize: 16,
  fontWeight: 600,
  color: 'var(--text-primary)',
};

const detailStyle: React.CSSProperties = {
  maxWidth: 600,
  padding: '12px 16px',
  background: 'var(--surface-elevated)',
  borderRadius: 8,
  border: '1px solid var(--border-subtle)',
  fontSize: 12,
  color: 'var(--text-muted)',
  wordBreak: 'break-all',
  whiteSpace: 'pre-wrap',
};

const buttonStyle: React.CSSProperties = {
  padding: '8px 20px',
  border: '1px solid var(--gold-border)',
  borderRadius: 6,
  background: 'var(--gold-bg)',
  color: 'var(--gold-400)',
  cursor: 'pointer',
  fontSize: 13,
  fontWeight: 500,
};

export class ChatRoomErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error(
      '[ChatRoomErrorBoundary] Component crash:',
      error.message,
      '\nComponent stack:',
      info.componentStack,
    );
  }

  handleReset = (): void => {
    this.setState({ hasError: false, error: null });
  };

  render(): ReactNode {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;

      return (
        <div style={containerStyle}>
          <span style={titleStyle}>⚠️ 页面渲染异常</span>
          <span>聊天室组件发生错误，请尝试刷新页面。</span>
          {this.state.error && (
            <div style={detailStyle}>
              {this.state.error.name}: {this.state.error.message}
            </div>
          )}
          <button style={buttonStyle} onClick={this.handleReset}>
            🔄 尝试恢复
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}

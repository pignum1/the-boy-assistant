/** HITL 卡片（通用版）— 使用共享 HITLOptions 组件 */
import type { CSSProperties } from 'react';
import type { HitlOption } from '../types/state';
import { HITLOptions } from './shared/HITLOptions';

interface Props {
  message: string;
  options: HitlOption[];
  onSelect: (value: string) => void;
  style?: CSSProperties;
}

export function HitlCard({ message, options, onSelect, style }: Props) {
  return (
    <div style={{
      padding: '14px 18px',
      background: 'var(--bg-card, #ffffff)',
      borderTop: '2px solid var(--gold-500, #f59e0b)',
      borderBottom: '1px solid var(--border-subtle, #e5e7eb)',
      animation: 'fadeIn 0.2s ease',
      ...style,
    }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
        <span style={{ fontSize: 20, flexShrink: 0, marginTop: 2 }}>🤔</span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            fontSize: 13, fontWeight: 600, color: 'var(--text-primary, #1f2937)',
            marginBottom: 6,
          }}>
            需要确认
          </div>
          <div style={{
            fontSize: 12.5, color: 'var(--text-secondary, #4b5563)',
            lineHeight: 1.6, whiteSpace: 'pre-wrap', wordBreak: 'break-word',
            maxHeight: 240, overflowY: 'auto',
          }}>
            {message}
          </div>
          <div style={{ display: 'flex', gap: 6, marginTop: 10, flexWrap: 'wrap' }}>
            <HITLOptions
              mode="interactive"
              options={options}
              onSelect={onSelect}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

/** 用户消息气泡：右对齐 + 代码块渲染 + 复制 */
import { useState, useCallback } from 'react';
import type { UserMessageItem } from '../../types/state';
import { renderContentWithCodeBlocks } from './CodeBlockRenderer';

interface Props {
  item: UserMessageItem;
}

export function UserMessageBubble({ item }: Props) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(item.content).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }, [item.content]);

  return (
    <div style={{ display: 'flex', justifyContent: 'flex-end', margin: '8px 0' }}>
      <div style={{
        maxWidth: '75%',
        padding: '10px 14px',
        background: 'var(--bg-elevated)',
        color: 'var(--text-primary)',
        border: '1px solid var(--border-medium)',
        borderRadius: 8,
        fontSize: 13,
        lineHeight: 1.65,
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-word',
        position: 'relative',
      }}>
        {renderContentWithCodeBlocks(item.content, () => {})}
        {/* 复制按钮 */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 6 }}>
          <button
            onClick={handleCopy}
            title="复制"
            style={{
              background: copied ? 'var(--green-bg)' : 'transparent',
              border: 'none',
              cursor: 'pointer',
              fontSize: 10,
              color: copied ? 'var(--green-400)' : 'var(--text-dim)',
              padding: '1px 4px',
              borderRadius: 3,
            }}
          >
            {copied ? '✓' : '📋'}
          </button>
        </div>
      </div>
    </div>
  );
}

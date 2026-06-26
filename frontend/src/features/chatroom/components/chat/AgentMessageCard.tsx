/** Agent 消息卡片：身份 + 内容（含代码块渲染）+ 可展开区域 + 复制

- 长文本（>500 字符）默认折叠，点击"展开"查看全部
- 代码块自动识别渲染，支持按语言着色 + 复制
- 每条消息可一键复制全文
*/
import { useState, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { AgentMessageItem, ArtifactFile, WorkPlan } from '../../types/state';
import { AgentCardHeader, hasExpandableContent } from './AgentCardHeader';
import { AgentCardExpandable } from './AgentCardExpandable';
import { renderContentWithCodeBlocks } from './CodeBlockRenderer';

const LONG_TEXT_THRESHOLD = 500;

interface Props {
  item: AgentMessageItem;
  workPlan: WorkPlan | null;
  artifacts: ArtifactFile[];
  onToggleExpand: (messageId: string) => void;
}

export function AgentMessageCard({ item, workPlan, artifacts, onToggleExpand }: Props) {
  const taskName = item.taskId && workPlan
    ? workPlan.tasks[item.taskId]?.name
    : undefined;

  const itemArtifacts = artifacts.filter(a => item.artifactIds.includes(a.id));
  const isLong = item.content.length > LONG_TEXT_THRESHOLD;
  const [textExpanded, setTextExpanded] = useState(false);
  const [copied, setCopied] = useState(false);

  const displayContent = (!isLong || textExpanded)
    ? item.content
    : item.content.slice(0, LONG_TEXT_THRESHOLD);

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(item.content).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }, [item.content]);

  return (
    <div
      data-message-id={item.id}
      data-meta-phase={item.metaPhase ?? ''}
      data-task-id={item.taskId ?? ''}
      style={{
        margin: '10px 0',
        padding: '10px 12px',
        background: 'var(--bg-card)',
        border: '1px solid var(--border-subtle)',
        borderRadius: 8,
        position: 'relative',
      }}
    >
      {/* 头部 + 复制按钮 */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
        <AgentCardHeader
          item={item}
          taskName={taskName}
          expanded={item.expanded}
          onToggleExpand={() => onToggleExpand(item.id)}
        />
        <button
          onClick={handleCopy}
          title="复制全文"
          style={{
            background: copied ? 'var(--green-bg)' : 'transparent',
            border: `1px solid ${copied ? 'var(--green-border)' : 'var(--border-subtle)'}`,
            borderRadius: 4,
            padding: '1px 6px',
            cursor: 'pointer',
            fontSize: 10,
            color: copied ? 'var(--green-400)' : 'var(--text-muted)',
            whiteSpace: 'nowrap',
            marginLeft: 8,
            flexShrink: 0,
            transition: 'all 0.15s',
          }}
        >
          {copied ? '✓ 已复制' : '📋 复制'}
        </button>
      </div>

      {/* 思考链（在对话内容上方 — 推理过程先于结论） */}
      {item.expanded && (
        <AgentCardExpandable item={item} artifacts={itemArtifacts} />
      )}

      {/* 消息内容（含代码块渲染） */}
      <div style={{
        fontSize: 13,
        lineHeight: 1.7,
        color: 'var(--text-primary)',
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-word',
        marginTop: 4,
      }}>
        {renderContentWithCodeBlocks(displayContent, () => {})}
        {item.isStreaming && <BlinkingCursor />}
      </div>

      {/* 长文本折叠/展开 */}
      {isLong && (
        <button
          onClick={() => setTextExpanded(!textExpanded)}
          style={{
            marginTop: 6,
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            fontSize: 11,
            color: 'var(--cyan-400)',
            padding: 0,
          }}
        >
          {textExpanded
            ? `▲ 收起（共 ${item.content.length} 字符）`
            : `▼ 展开全部（共 ${item.content.length} 字符）`}
        </button>
      )}

      {/* 产物缩略 */}
      {!item.expanded && itemArtifacts.length > 0 && (
        <div style={{
          marginTop: 8,
          display: 'flex',
          flexWrap: 'wrap',
          gap: 6,
        }}>
          {itemArtifacts.slice(0, 4).map(a => (
            <span key={a.id} style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 4,
              padding: '2px 6px',
              borderRadius: 4,
              background: 'rgba(34, 211, 238, 0.06)',
              color: 'var(--cyan-400)',
              fontSize: 10,
              fontFamily: 'var(--font-mono)',
            }}>
              📎 {a.name}
            </span>
          ))}
          {itemArtifacts.length > 4 && (
            <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>
              +{itemArtifacts.length - 4} 个
            </span>
          )}
        </div>
      )}
    </div>
  );
}

function BlinkingCursor() {
  return (
    <span style={{
      display: 'inline-block',
      width: 8,
      height: 14,
      marginLeft: 2,
      background: 'var(--cyan-400)',
      verticalAlign: 'text-bottom',
      animation: 'chatroom-blink 1s steps(2) infinite',
    }} />
  );
}

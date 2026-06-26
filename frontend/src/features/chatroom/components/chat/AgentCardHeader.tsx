/** Agent 卡片头部：头像 + 名 + 阶段/任务/模型/耗时 chip + 展开按钮 */
import type { AgentMessageItem } from '../../types/state';
import { AgentAvatar } from '../shared/AgentAvatar';
import { Chip } from '../shared/Chip';
import { metaPhaseChipText } from '../shared/labels';

interface Props {
  item: AgentMessageItem;
  /** 任务名（如果该消息关联了具体业务任务） */
  taskName?: string;
  /** 是否展开（控制 ▸/▾ 图标） */
  expanded: boolean;
  /** 点击展开按钮 */
  onToggleExpand: () => void;
}

export function AgentCardHeader({ item, taskName, expanded, onToggleExpand }: Props) {
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 8,
      marginBottom: 6,
      flexWrap: 'wrap',
    }}>
      <AgentAvatar emoji={item.agentEmoji} name={item.agentName} size={26} />
      <span style={{
        fontSize: 13,
        fontWeight: 600,
        color: 'var(--text-primary)',
      }}>
        {item.agentName}
      </span>

      {/* 维度 A · 系统阶段 chip（仅多 Agent 路径有） */}
      {item.metaPhase && (
        <Chip variant="phase" icon="📊">
          {metaPhaseChipText(item.metaPhase, item.iteration)}
        </Chip>
      )}

      {/* 维度 B · 业务任务 chip（M6 中才有） */}
      {item.taskId && (
        <Chip variant="task" icon="📋" title={taskName}>
          {item.taskId}{taskName ? ` ${taskName}` : ''}
        </Chip>
      )}

      {/* 模型 chip */}
      {item.model && (
        <Chip variant="model" icon="🧠">
          {item.model}
        </Chip>
      )}

      {/* 耗时 chip */}
      {item.latency !== undefined && item.latency > 0 && (
        <Chip variant="latency" icon="⏱">
          {formatLatency(item.latency)}
        </Chip>
      )}

      <div style={{ flex: 1 }} />

      {/* 展开/折叠 — 仅在有可展开内容时显示 */}
      {hasExpandableContent(item) && (
        <button
          onClick={onToggleExpand}
          style={{
            background: expanded ? 'var(--cyan-bg)' : 'rgba(56, 189, 248, 0.06)',
            border: '1px solid var(--cyan-border)',
            cursor: 'pointer',
            color: 'var(--cyan-400)',
            fontSize: 10,
            padding: '2px 8px',
            borderRadius: 4,
            fontFamily: 'var(--font-mono)',
            display: 'inline-flex',
            alignItems: 'center',
            gap: 4,
          }}
          aria-label={expanded ? '折叠' : '展开'}
        >
          {expanded ? '▾ 收起' : '▸ 思考链'}
        </button>
      )}
    </div>
  );
}

/** 决定该消息是否有可展开的内容（思考、模型路由、工具调用、产物） */
export function hasExpandableContent(item: AgentMessageItem): boolean {
  if (!item.reasoning) return item.artifactIds.length > 0;
  const r = item.reasoning;
  return !!(
    r.supervisorAnalysis ||
    r.thinkingSteps ||
    r.decisionSummary ||
    r.modelRouting?.selectedModel ||
    (r.toolCalls && r.toolCalls.length > 0) ||
    item.artifactIds.length > 0
  );
}

function formatLatency(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

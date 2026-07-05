/** Agent 卡片头部：头像 + 名 + 阶段/任务/模型/耗时 chip + 展开按钮 */
import type { AgentMessageItem } from '../../types/state';
import { AgentAvatar } from '../shared/AgentAvatar';
import { Chip } from '../shared/Chip';
import { metaPhaseChipText } from '../shared/labels';
import { getAgentColorSet } from './AgentMessageCard';

interface Props {
  item: AgentMessageItem;
  /** 任务名（如果该消息关联了具体业务任务） */
  taskName?: string;
  /** 是否展开（控制 ▸/▾ 图标） */
  expanded: boolean;
  /** 点击展开按钮 */
  onToggleExpand: () => void;
}

// ── 执行模式显示名 ──
const MODE_LABEL: Record<string, string> = {
  single_pass: '⚡单次', chain_of_thought: '🔗思维链', plan_execute: '📋规划执行',
  rewoo: '📦ReWOO', react: '🔄ReAct', reflexion: '🪞Reflexion', self_consistency: '🗳️自一致性',
};

// ── 按 Agent 名推断模式（fallback，用于历史消息 / WS 断连场景）──
const NAME_MODE_HINT: Record<string, string> = {
  '产品经理': 'plan_execute',
  '架构师': 'self_consistency',
  '后端': 'react',
  '前端': 'single_pass',
  '测试': 'reflexion',
  'UI': 'chain_of_thought',
  '设计': 'chain_of_thought',
  '部署': 'rewoo',
  '运维': 'rewoo',
};
function inferModeFromName(agentName: string): string {
  for (const [kw, mode] of Object.entries(NAME_MODE_HINT)) {
    if (agentName.includes(kw)) return mode;
  }
  return 'single_pass';
}

export function AgentCardHeader({ item, taskName, expanded, onToggleExpand, showExpandBtn }: Props) {
  const agentColor = getAgentColorSet(item.agentName).accent;
  const reasoning = item.reasoning as Record<string, unknown> | undefined;
  // WS实时数据优先 → item.execMode → reasoning.execMode → 名字推断fallback
  const execMode = (item.execMode || reasoning?.execMode || reasoning?.exec_mode || inferModeFromName(item.agentName)) as string;
  const iterations = (reasoning?.iterations as number) || 0;
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
        color: agentColor,
      }}>
        {item.agentName}
      </span>

      {/* 执行模式 chip */}
      {execMode && MODE_LABEL[execMode] && (
        <span style={{
          fontSize: 10, padding: '1px 6px', borderRadius: 4,
          background: `${agentColor}22`, color: agentColor,
          border: `1px solid ${agentColor}44`, fontWeight: 500,
        }}>
          {MODE_LABEL[execMode]}
          {iterations > 1 && ` ×${iterations}`}
        </span>
      )}

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

      {/* 模型 chip — 仅当有有效模型名时显示 */}
      {item.model && item.model !== 'unknown' && (
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
      {showExpandBtn && (
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

/** 决定该消息是否有可展开的内容（思考、模型路由、工具调用、产物、执行模式信息） */
export function hasExpandableContent(item: AgentMessageItem): boolean {
  // 只在有实际 reasoning 数据或产物时才显示展开按钮
  // 名字推断的模式标签始终显示，但思考链按钮不依赖名字推断
  if (item.artifactIds.length > 0) return true;
  const r = item.reasoning as Record<string, unknown> | undefined;
  if (!r) return false;
  return !!(
    r.supervisorAnalysis ||
    r.thinkingSteps ||
    r.thinking_steps ||
    r.decisionSummary ||
    (r.modelRouting as Record<string, unknown> | undefined)?.selectedModel ||
    (Array.isArray(r.toolCalls) && r.toolCalls.length > 0) ||
    r.execMode ||
    r.exec_mode ||
    r.iterations ||
    // 模式专属数据：ReAct 迭代链 / Reflexion 反思 / Self-Consistency 采样 / ReWOO 计划等
    (Array.isArray(r.history) && r.history.length > 0) ||
    (Array.isArray(r.reflections) && r.reflections.length > 0) ||
    (Array.isArray(r.samples) && r.samples.length > 0) ||
    r.plan ||
    (Array.isArray(r.tool_results) && r.tool_results.length > 0) ||
    r.review_score != null
  );
}

function formatLatency(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

/** Agent 消息卡片：身份 + 内容 + 独立的思维链折叠面板 */
import { useState, useCallback, useMemo } from 'react';
import type { AgentMessageItem, ArtifactFile, WorkPlan } from '../../types/state';

// ── Agent 颜色映射 ——
const ROLE_COLOR_MAP: Record<string, string> = {
  '产品经理': '#e67e22', '架构师': '#8e44ad', '后端': '#e74c3c',
  '前端': '#3498db', '测试': '#2ecc71', 'UI': '#f39c12', '设计': '#f39c12',
  '部署': '#1abc9c', '运维': '#1abc9c',
};
const FALLBACK_COLORS = ['#c0392b', '#16a085', '#d35400', '#2980b9'];

export function getAgentColorSet(agentName: string) {
  let accent = '';
  for (const [keyword, color] of Object.entries(ROLE_COLOR_MAP)) {
    if (agentName.includes(keyword)) { accent = color; break; }
  }
  if (!accent) {
    let hash = 5381;
    for (let i = 0; i < agentName.length; i++) hash = ((hash << 5) + hash) + agentName.charCodeAt(i);
    accent = FALLBACK_COLORS[Math.abs(hash) % FALLBACK_COLORS.length];
  }
  return { accent, bg: `${accent}1A`, border: `${accent}44` };
}

import { AgentCardHeader, hasExpandableContent } from './AgentCardHeader';
import { AgentCardExpandable } from './AgentCardExpandable';
import { renderContentWithCodeBlocks } from './CodeBlockRenderer';

const LONG_TEXT_THRESHOLD = 500;

const MODE_LABEL: Record<string, string> = {
  single_pass: '⚡单次', chain_of_thought: '🔗思维链', plan_execute: '📋规划执行',
  rewoo: '📦ReWOO', react: '🔄ReAct', reflexion: '🪞Reflexion', self_consistency: '🗳️自一致性',
};
const NAME_MODE_HINT: Record<string, string> = {
  '产品经理': 'plan_execute', '架构师': 'self_consistency', '后端': 'react',
  '前端': 'single_pass', '测试': 'reflexion', 'UI': 'chain_of_thought',
  '设计': 'chain_of_thought', '部署': 'rewoo', '运维': 'rewoo',
};
function inferMode(agentName: string): string {
  for (const [kw, mode] of Object.entries(NAME_MODE_HINT)) {
    if (agentName.includes(kw)) return mode;
  }
  return 'single_pass';
}

interface Props {
  item: AgentMessageItem;
  workPlan: WorkPlan | null;
  artifacts: ArtifactFile[];
  onToggleExpand: (messageId: string) => void;
}

export function AgentMessageCard({ item, workPlan, artifacts, onToggleExpand }: Props) {
  const taskName = item.taskId && workPlan ? workPlan.tasks[item.taskId]?.name : undefined;
  const itemArtifacts = artifacts.filter(a => item.artifactIds.includes(a.id));
  const isLong = item.content.length > LONG_TEXT_THRESHOLD;
  const [textExpanded, setTextExpanded] = useState(false);
  const [copied, setCopied] = useState(false);
  const displayContent = (!isLong || textExpanded) ? item.content : item.content.slice(0, LONG_TEXT_THRESHOLD);
  const agentColors = useMemo(() => getAgentColorSet(item.agentName), [item.agentName]);
  const canExpand = hasExpandableContent(item);

  // 模式名
  const reasoning = item.reasoning as Record<string, unknown> | undefined;
  const execMode = (item.execMode || reasoning?.execMode || reasoning?.exec_mode || inferMode(item.agentName)) as string;
  const modeLabel = MODE_LABEL[execMode] || execMode;
  const iterations = (reasoning?.iterations as number) || 0;

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(item.content).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500); });
  }, [item.content]);

  const accent = agentColors.accent;

  return (
    <div style={{ margin: '10px 0' }}>
      {/* ── 独立折叠面板：思考链（消息气泡上方，推理过程先于结论）── */}
      {canExpand && (
        <div style={{ marginBottom: 6, marginLeft: 8 }}>
          <button
            onClick={() => onToggleExpand(item.id)}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              width: '100%', maxWidth: 400,
              padding: '6px 12px',
              background: 'var(--bg-elevated)',
              border: `1px solid ${accent}33`,
              borderLeft: `3px solid ${accent}66`,
              borderRadius: 6,
              cursor: 'pointer',
              fontSize: 11,
              color: 'var(--text-secondary)',
              fontFamily: 'inherit',
              transition: 'background 0.15s',
            }}
            onMouseEnter={e => (e.currentTarget.style.background = `${accent}0D`)}
            onMouseLeave={e => (e.currentTarget.style.background = 'var(--bg-elevated)')}
          >
            <span style={{ fontSize: 14 }}>🧠</span>
            <span style={{ fontWeight: 600 }}>思考过程</span>
            <span style={{ color: accent, fontWeight: 500 }}>{modeLabel}</span>
            {iterations > 0 && <span style={{ color: 'var(--text-muted)' }}>· {iterations}次调用</span>}
            <span style={{ marginLeft: 'auto', fontSize: 10, transition: 'transform 0.2s', transform: item.expanded ? 'rotate(180deg)' : 'rotate(0deg)' }}>▼</span>
          </button>

          {item.expanded && (
            <div style={{
              marginTop: 4,
              padding: '10px 14px',
              background: 'var(--bg-elevated)',
              border: `1px solid ${accent}22`,
              borderLeft: `3px solid ${accent}55`,
              borderRadius: 6,
              maxWidth: 600,
            }}>
              <AgentCardExpandable item={item} artifacts={itemArtifacts} />
            </div>
          )}
        </div>
      )}

      {/* ── 消息气泡（思考过程下方，最终答案）── */}
      <div data-message-id={item.id} style={{
        padding: '10px 12px',
        background: agentColors.bg,
        border: `1px solid ${agentColors.border}`,
        borderLeft: `4px solid ${accent}`,
        borderRadius: 8,
      }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
          <AgentCardHeader item={item} taskName={taskName}
            expanded={false} onToggleExpand={() => {}} showExpandBtn={false} />
          <button onClick={handleCopy} title="复制全文" style={{
            background: copied ? 'var(--green-bg)' : 'transparent',
            border: `1px solid ${copied ? 'var(--green-border)' : 'var(--border-subtle)'}`,
            borderRadius: 4, padding: '1px 6px', cursor: 'pointer', fontSize: 10,
            color: copied ? 'var(--green-400)' : 'var(--text-muted)',
            whiteSpace: 'nowrap', marginLeft: 8, flexShrink: 0, transition: 'all 0.15s',
          }}>{copied ? '✓ 已复制' : '📋 复制'}</button>
        </div>

        <div style={{ fontSize: 13, lineHeight: 1.7, color: 'var(--text-primary)', whiteSpace: 'pre-wrap', wordBreak: 'break-word', marginTop: 4 }}>
          {renderContentWithCodeBlocks(displayContent, () => {})}
          {item.isStreaming && <BlinkingCursor />}
        </div>

        {isLong && (
          <button onClick={() => setTextExpanded(!textExpanded)} style={{ marginTop: 6, background: 'none', border: 'none', cursor: 'pointer', fontSize: 11, color: 'var(--cyan-400)', padding: 0 }}>
            {textExpanded ? `▲ 收起（共 ${item.content.length} 字符）` : `▼ 展开全部（共 ${item.content.length} 字符）`}
          </button>
        )}

        {!item.expanded && itemArtifacts.length > 0 && (
          <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {itemArtifacts.slice(0, 4).map(a => (
              <span key={a.id} style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '2px 6px', borderRadius: 4, background: 'rgba(34,211,238,0.06)', color: 'var(--cyan-400)', fontSize: 10, fontFamily: 'var(--font-mono)' }}>📎 {a.name}</span>
            ))}
            {itemArtifacts.length > 4 && <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>+{itemArtifacts.length - 4} 个</span>}
          </div>
        )}
      </div>
    </div>
  );
}

function BlinkingCursor() {
  return <span style={{ display: 'inline-block', width: 8, height: 14, marginLeft: 2, background: 'var(--cyan-400)', verticalAlign: 'text-bottom', animation: 'chatroom-blink 1s steps(2) infinite' }} />;
}

/** 思考指示器单行：⏺ 头像 名 · 阶段 摘要 ……  耗时 */
import type { ThinkingAgent } from '../../types/state';
import { AgentAvatar } from '../shared/AgentAvatar';
import { Chip } from '../shared/Chip';
import { metaPhaseChipText } from '../shared/labels';
import { useThinkingTick } from './ThinkingTickProvider';

interface Props {
  agent: ThinkingAgent;
}

export function ThinkingRow({ agent }: Props) {
  const tick = useThinkingTick();
  const elapsed = Math.max(0, Math.floor((tick - agent.startedAt) / 1000));
  const isPlaceholder = agent.agentId === '__placeholder__';

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 8,
      padding: '6px 12px',
      fontSize: 12,
      color: 'var(--text-secondary)',
      fontFamily: 'var(--font-body)',
    }}>
      <PulseDot />
      {!isPlaceholder && <AgentAvatar emoji={agent.agentEmoji} name={agent.agentName} size={22} />}
      <span style={{
        color: 'var(--text-primary)',
        fontWeight: isPlaceholder ? 400 : 500,
      }}>
        {agent.agentName}
      </span>
      {agent.metaPhase && (
        <Chip variant="phase" icon="📊">
          {metaPhaseChipText(agent.metaPhase)}
        </Chip>
      )}
      {agent.taskId && (
        <Chip variant="task" icon="📋">
          {agent.taskId}
        </Chip>
      )}
      {agent.summary && (
        <span style={{
          color: 'var(--text-muted)',
          fontSize: 11,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          maxWidth: 240,
        }}>
          {agent.summary}
        </span>
      )}
      <div style={{ flex: 1 }} />
      <span style={{
        fontSize: 10,
        color: 'var(--text-muted)',
        fontFamily: 'var(--font-mono)',
      }}>
        {agent.status === 'waiting' ? 'idle' : `·${elapsed}s`}
      </span>
    </div>
  );
}

function PulseDot() {
  return (
    <span style={{
      width: 8,
      height: 8,
      borderRadius: '50%',
      background: 'var(--cyan-400)',
      display: 'inline-block',
      animation: 'chatroom-pulse 1.4s ease-in-out infinite',
      flexShrink: 0,
    }} />
  );
}

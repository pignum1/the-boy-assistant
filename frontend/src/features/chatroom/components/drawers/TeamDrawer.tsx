/** 团队抽屉：完整团队 + 实时状态
 *
 * 数据源：
 *   1. useTeamMembers fetch 的完整团队 roster（idle / 待激活）
 *   2. messages 派生 — 已发言 Agent 视为 done
 *   3. thinkingAgents — 当前活跃覆盖为 thinking
 *
 * 合并优先级：thinking > done > idle（来自完整 roster）
 */
import { useMemo } from 'react';
import type {
  TimelineItem,
  ThinkingAgent,
} from '../../types/state';
import type { TeamMember } from '../../hooks/useTeamMembers';
import { AgentAvatar } from '../shared/AgentAvatar';

interface Props {
  messages: TimelineItem[];
  thinkingAgents: ThinkingAgent[];
  teamMembers: TeamMember[];
}

interface ObservedAgent {
  id: string;
  name: string;
  emoji: string;
  role: string;
  status: 'idle' | 'thinking' | 'done';
  messageCount: number;
  lastSummary?: string;
  capabilities: string[];
}

export function TeamDrawer({ messages, thinkingAgents, teamMembers }: Props) {
  const merged = useMemo(
    () => mergeAgents(messages, thinkingAgents, teamMembers),
    [messages, thinkingAgents, teamMembers]
  );

  if (merged.length === 0) {
    return (
      <div style={{
        padding: '60px 20px',
        textAlign: 'center',
        color: 'var(--text-muted)',
        fontSize: 12,
      }}>
        团队信息加载中...
      </div>
    );
  }

  const workingCount = merged.filter(a => a.status === 'thinking').length;
  const doneCount = merged.filter(a => a.status === 'done').length;
  const idleCount = merged.filter(a => a.status === 'idle').length;

  return (
    <div style={{ padding: '10px 14px' }}>
      <div style={{
        fontSize: 11,
        color: 'var(--text-muted)',
        fontFamily: 'var(--font-mono)',
        marginBottom: 10,
      }}>
        {merged.length} 人 ·
        {workingCount > 0 && <span style={{ color: 'var(--blue-400)', marginLeft: 4 }}>{workingCount} 工作中</span>}
        {doneCount > 0 && <span style={{ color: 'var(--green-400)', marginLeft: 4 }}>· {doneCount} 已完成</span>}
        {idleCount > 0 && <span style={{ color: 'var(--text-muted)', marginLeft: 4 }}>· {idleCount} 待命</span>}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {merged.map(a => <AgentRow key={a.id || a.name} agent={a} />)}
      </div>
    </div>
  );
}

function AgentRow({ agent }: { agent: ObservedAgent }) {
  const statusColor =
    agent.status === 'thinking' ? 'var(--blue-400)' :
    agent.status === 'done' ? 'var(--green-400)' :
    'var(--text-dim)';
  const statusIcon =
    agent.status === 'thinking' ? '⏳' :
    agent.status === 'done' ? '✓' :
    '○';
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 8,
      padding: '6px 8px',
      background: agent.status === 'thinking' ? 'var(--blue-bg)' : 'rgba(148,163,184,0.03)',
      border: `1px solid ${agent.status === 'thinking' ? 'var(--blue-border)' : 'var(--border-subtle)'}`,
      borderRadius: 4,
    }}>
      <AgentAvatar emoji={agent.emoji} name={agent.name} size={26} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontSize: 12,
          fontWeight: 500,
          color: 'var(--text-primary)',
        }}>
          {agent.name}
        </div>
        <div style={{
          fontSize: 10,
          color: 'var(--text-muted)',
          fontFamily: 'var(--font-mono)',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}>
          {agent.lastSummary ?? agent.role}
        </div>
      </div>
      <span style={{
        fontSize: 12,
        color: statusColor,
        fontFamily: 'var(--font-mono)',
        minWidth: 14,
        textAlign: 'center',
      }}>
        {statusIcon}
      </span>
      {agent.messageCount > 0 && (
        <span style={{
          fontSize: 10,
          color: 'var(--text-muted)',
          fontFamily: 'var(--font-mono)',
          minWidth: 18,
          textAlign: 'right',
        }}>
          {agent.messageCount}
        </span>
      )}
    </div>
  );
}

function mergeAgents(
  messages: TimelineItem[],
  thinkingAgents: ThinkingAgent[],
  teamMembers: TeamMember[],
): ObservedAgent[] {
  // 用 agentName 作为合并 key（agent_id 在不同场景下可能 mismatch）
  const map = new Map<string, ObservedAgent>();

  // 1. 完整团队 roster 作为底（idle 态）
  for (const m of teamMembers) {
    map.set(m.agentName, {
      id: m.agentId,
      name: m.agentName,
      emoji: m.roleIcon,
      role: m.roleName,
      status: 'idle',
      messageCount: 0,
      capabilities: m.capabilities,
    });
  }

  // 2. 已发言 Agent 视为 done
  for (const item of messages) {
    if (item.kind !== 'agent_message') continue;
    const key = item.agentName;
    const existing = map.get(key);
    if (existing) {
      existing.status = 'done';
      existing.messageCount += 1;
    } else {
      map.set(key, {
        id: item.agentId,
        name: item.agentName,
        emoji: item.agentEmoji,
        role: '',
        status: 'done',
        messageCount: 1,
        capabilities: [],
      });
    }
  }

  // 3. 当前活跃覆盖为 thinking
  for (const t of thinkingAgents) {
    if (t.agentId === '__placeholder__') continue;
    const key = t.agentName;
    const existing = map.get(key);
    if (existing) {
      existing.status = 'thinking';
      existing.lastSummary = t.summary;
    } else {
      map.set(key, {
        id: t.agentId,
        name: t.agentName,
        emoji: t.agentEmoji,
        role: '',
        status: 'thinking',
        messageCount: 0,
        lastSummary: t.summary,
        capabilities: [],
      });
    }
  }

  // 排序：thinking > done > idle，组内按消息数降序
  return Array.from(map.values()).sort((a, b) => {
    const rank = (s: string) => s === 'thinking' ? 0 : s === 'done' ? 1 : 2;
    if (rank(a.status) !== rank(b.status)) return rank(a.status) - rank(b.status);
    return b.messageCount - a.messageCount;
  });
}

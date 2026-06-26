/** 对话流容器：把 timeline items 映射成对应卡片，自动滚到底 */
import { useEffect, useRef, useCallback } from 'react';
import type {
  TimelineItem,
  WorkPlan,
  ArtifactFile,
} from '../../types/state';
import { UserMessageBubble } from './UserMessageBubble';
import { UserInterruptBubble } from './UserInterruptBubble';
import { SystemDivider } from './SystemDivider';
import { AgentMessageCard } from './AgentMessageCard';
import { HITLCard } from './HITLCard';
import { VerificationCard } from './VerificationCard';
import { SystemSummaryCard } from './SystemSummaryCard';

interface Props {
  messages: TimelineItem[];
  workPlan: WorkPlan | null;
  artifacts: ArtifactFile[];
  onToggleExpand: (messageId: string) => void;
  onToggleVerification: (messageId: string) => void;
  onHitlPrimaryAction: (hitlId: string, value: string) => void;
  onHitlEnterAnswering: (hitlId: string) => void;
}

export function ChatStream({
  messages,
  workPlan,
  artifacts,
  onToggleExpand,
  onToggleVerification,
  onHitlPrimaryAction,
  onHitlEnterAnswering,
}: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const lastLengthRef = useRef(0);
  const userScrolledUpRef = useRef(false);

  // 检测用户是否手动上滚
  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    userScrolledUpRef.current = !atBottom;
  }, []);

  // 新消息进入时滚到底（除非用户主动上滚查看历史）
  useEffect(() => {
    if (messages.length > lastLengthRef.current && !userScrolledUpRef.current) {
      const el = scrollRef.current;
      if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
    }
    lastLengthRef.current = messages.length;
  }, [messages.length]);

  return (
    <div
      ref={scrollRef}
      onScroll={handleScroll}
      style={{
        flex: 1,
        overflowY: 'auto',
        padding: '14px 18px',
      }}
    >
      {messages.length === 0 && (
        <div style={{
          textAlign: 'center',
          color: 'var(--text-muted)',
          fontSize: 12,
          paddingTop: 60,
          fontFamily: 'var(--font-mono)',
        }}>
          ╴ 开始一段新对话 ╴
        </div>
      )}
      {messages.map(item => (
        <ItemRenderer
          key={item.id}
          item={item}
          workPlan={workPlan}
          artifacts={artifacts}
          onToggleExpand={onToggleExpand}
          onToggleVerification={onToggleVerification}
          onHitlPrimaryAction={onHitlPrimaryAction}
          onHitlEnterAnswering={onHitlEnterAnswering}
        />
      ))}
    </div>
  );
}

function ItemRenderer({
  item,
  workPlan,
  artifacts,
  onToggleExpand,
  onToggleVerification,
  onHitlPrimaryAction,
  onHitlEnterAnswering,
}: Props & { item: TimelineItem }) {
  switch (item.kind) {
    case 'user_message':
      return <UserMessageBubble item={item} />;
    case 'user_interrupt':
      return <UserInterruptBubble item={item} />;
    case 'system_divider':
      return <SystemDivider item={item} />;
    case 'agent_message':
      return (
        <AgentMessageCard
          item={item}
          workPlan={workPlan}
          artifacts={artifacts}
          onToggleExpand={onToggleExpand}
        />
      );
    case 'hitl_card':
      return (
        <HITLCard
          item={item}
          onPrimaryAction={value => onHitlPrimaryAction(item.hitlId, value)}
          onEnterAnswering={() => onHitlEnterAnswering(item.hitlId)}
        />
      );
    case 'verification':
      return <VerificationCard item={item} onToggleExpand={onToggleVerification} />;
    case 'system_summary':
      return <SystemSummaryCard item={item} />;
    default: {
      const _: never = item;
      void _;
      return null;
    }
  }
}

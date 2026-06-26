import { useEffect, useRef } from 'react';
import type { AgentMsg } from './hooks/useTaskEvents';
import { MessageBubble } from './MessageBubble';

interface MessageListProps {
  messages: AgentMsg[];
}

export function MessageList({ messages }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length]);

  return (
    <div
      style={{
        flex: 1,
        overflowY: 'auto',
        padding: 16,
        display: 'flex',
        flexDirection: 'column',
        gap: 12,
        background: 'var(--bg-deep)',
      }}
    >
      {messages.length === 0 && (
        <div style={{ textAlign: 'center', color: 'var(--text-dim)', fontSize: 13, marginTop: 32 }}>
          等待 Agent 消息...
        </div>
      )}
      {messages.map((msg) => (
        <MessageBubble key={msg.id} msg={msg} />
      ))}
      <div ref={bottomRef} />
    </div>
  );
}

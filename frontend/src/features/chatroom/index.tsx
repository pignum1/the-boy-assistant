/** 聊天室主组件：根据 session.mode 渲染 ChatRoomView 或 TaskView (Pipeline)
 *
 * 讨论模式（discussion）→ ChatRoomView（PR2 新对话流）
 * SOP 模式 → TaskView（保留原有 Pipeline）
 *
 * 旧的 DiscussionView 已通过 ChatRoomView 替代；保留文件以便随时回滚（设置
 * localStorage['chatroom:legacy'] = '1' 可强制走旧 UI）。
 */
import { useState, useEffect } from 'react';
import { sessionsApi } from '../../shared/api/sessions';
import type { SessionInfo } from '../../shared/types/session';
import { DiscussionView } from './DiscussionView';
import { ChatRoomView } from './ChatRoomView';
import { useTaskEvents } from './hooks/useTaskEvents';
import { PipelineView } from './PipelineView';
import { MessageList } from './MessageList';
import { HitlDialog } from './HitlDialog';
import { TaskStatusBar } from './TaskStatusBar';

/** 是否强制走旧 DiscussionView（紧急回滚开关） */
function shouldUseLegacy(): boolean {
  if (typeof window === 'undefined') return false;
  return window.localStorage?.getItem('chatroom:legacy') === '1';
}

interface ChatRoomProps {
  sessionId: string;
  taskId?: string;
}

export function ChatRoom({ sessionId, taskId }: ChatRoomProps) {
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    sessionsApi.get(sessionId)
      .then((s) => { setSession(s); setLoading(false); })
      .catch(() => setLoading(false));
  }, [sessionId]);

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-muted)' }}>
        加载中...
      </div>
    );
  }

  if (!session) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-muted)' }}>
        会话不存在或已被删除
      </div>
    );
  }

  // 讨论模式 → ChatRoomView（新）或 DiscussionView（紧急回滚）
  if (session.mode === 'discussion' || !taskId) {
    if (shouldUseLegacy()) {
      return <DiscussionView sessionId={sessionId} teamId={session.team_id} />;
    }
    return <ChatRoomView sessionId={sessionId} teamId={session.team_id} />;
  }

  // SOP 模式 → 现有的 Pipeline + MessageList
  return <TaskView sessionId={sessionId} taskId={taskId} teamId={session.team_id} />;
}

/** SOP 任务视图：保留现有 Pipeline 交互 */
function TaskView({ sessionId, taskId, teamId }: { sessionId: string; taskId: string; teamId: string }) {
  const [sopName, setSopName] = useState<string>();
  const { nodeStates, messages, hitlRequest, taskStatus, connected, dismissHitl } =
    useTaskEvents(taskId, teamId);

  // 获取任务信息（包含 SOP 名称）
  useEffect(() => {
    const fetchTask = async () => {
      try {
        const api = (import.meta as unknown as { env: Record<string, string> }).env?.VITE_API_URL || '';
        const res = await fetch(`${api}/api/v1/tasks/${taskId}`);
        if (res.ok) {
          const task = await res.json();
          if (task.sop_name) {
            setSopName(task.sop_name);
          }
        }
      } catch (e) {
        console.error('Failed to fetch task info:', e);
      }
    };
    fetchTask();
  }, [taskId]);

  return (
    <div className="flex flex-col h-full">
      <div className="flex flex-1 overflow-hidden">
        <PipelineView nodeStates={nodeStates} sopName={sopName} />
        <MessageList messages={messages} />
      </div>
      <TaskStatusBar
        taskStatus={taskStatus}
        connected={connected}
        messageCount={messages.length}
      />
      {hitlRequest && (
        <HitlDialog taskId={taskId} request={hitlRequest} onDismiss={dismissHitl} />
      )}
    </div>
  );
}

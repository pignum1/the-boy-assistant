/** ChatRoomIndex — 模式入口，统一路由到 ChatRoomView

所有三种协作模式（swarm / supervisor / langgraph）通过同一个 ChatRoomView 渲染。
ChatRoomView 内部使用 reducer 管理状态，通过 useWsEvents 共享 WS 连接。

模式差异通过 collabMode 传递给 PhaseProgressBar 和子组件处理：
- swarm:     无 M-stage 阶段条，HITL 为 option/answer 类型
- supervisor: 显示 M0-M7 元阶段进度，HITL 为 clarification/delta_plan 类型
- langgraph:  显示工作流节点进度，HITL 为 pause/resume 类型

旧版独立视图（SwarmView / SupervisorView）保留作为紧急回退。
设置 localStorage['chatroom:legacy_views'] = '1' 可切回旧版。
*/

import { useTeamMode } from './hooks/useTeamMode';
import { ChatRoomView } from './ChatRoomView';
import { ChatRoomErrorBoundary } from './components/shared/ErrorBoundary';
import { SupervisorView } from './views/SupervisorView';
import { SwarmView } from './views/SwarmView';

export type CollabMode = 'supervisor' | 'swarm' | 'langgraph';

export const MODE_CONFIG: Record<string, { emoji: string; label: string; desc: string; color: string }> = {
  supervisor: { emoji: '👑', label: '主管模式', desc: 'Leader 分析任务，委派成员执行', color: '#f59e0b' },
  swarm: { emoji: '💬', label: '群聊模式', desc: '多 Agent 自由讨论协作', color: '#3b82f6' },
  langgraph: { emoji: '🔗', label: '工作流模式', desc: '预定义 DAG 编排执行', color: '#10b981' },
};

interface Props {
  sessionId: string;
  teamId: string;
}

export function ChatRoomIndex({ sessionId, teamId }: Props) {
  const collabMode = useTeamMode(teamId);

  if (!collabMode) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
        <div style={{ textAlign: 'center', color: '#9ca3af' }}>
          <div style={{ fontSize: 32, marginBottom: 8 }}>⏳</div>
          <div style={{ fontSize: 14 }}>加载中...</div>
        </div>
      </div>
    );
  }

  // 紧急回退开关：localStorage['chatroom:legacy_views'] = '1'
  const useLegacy = typeof localStorage !== 'undefined'
    && localStorage.getItem('chatroom:legacy_views') === '1';

  if (useLegacy) {
    switch (collabMode) {
      case 'swarm':
        return <ChatRoomErrorBoundary><SwarmView sessionId={sessionId} teamId={teamId} /></ChatRoomErrorBoundary>;
      case 'supervisor':
        return <ChatRoomErrorBoundary><SupervisorView sessionId={sessionId} teamId={teamId} /></ChatRoomErrorBoundary>;
      default:
        // langgraph 及其他模式在 legacy 路径也使用 ChatRoomView
        break;
    }
  }

  // 统一路径：所有模式使用 ChatRoomView + reducer 架构
  return <ChatRoomView sessionId={sessionId} teamId={teamId} />;
}

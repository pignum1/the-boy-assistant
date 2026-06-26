/** Chat room reducer action types
 *
 * 所有 state 变更都通过 dispatch action 完成。
 * Action 分三类：
 *   1. WS_* —— 来自 WebSocket 入站事件
 *   2. UI_* —— 来自前端 UI 交互
 *   3. CTRL_* —— 内部控制（init/reset/connection）
 */

import type {
  RoutingDecisionPayload,
  AgentStatusPayload,
  AgentMessagePayload,
  ThinkingUpdatePayload,
  ReasoningCompletePayload,
  HitlRequestPayload,
  PhaseUpdatePayload,
  FilesChangedPayload,
  MessageCompletePayload,
  ToolCallPayload,
  StreamTokenPayload,
  ErrorPayload,
  TaskDagPayload,
  TaskStatusPayload,
  ExecutionStatePayload,
  DeltaPlanPayload,
} from '../types/events';
import type { DrawerKind } from '../types/state';

// ── 1. WS 入站事件 actions ──

export type WsAction =
  | { type: 'WS/ROUTING_DECISION'; payload: RoutingDecisionPayload }
  | { type: 'WS/AGENT_STATUS'; payload: AgentStatusPayload }
  | { type: 'WS/AGENT_MESSAGE'; payload: AgentMessagePayload; source?: string }
  | { type: 'WS/THINKING_UPDATE'; payload: ThinkingUpdatePayload }
  | { type: 'WS/REASONING_COMPLETE'; payload: ReasoningCompletePayload }
  | { type: 'WS/HITL_REQUEST'; payload: HitlRequestPayload }
  | { type: 'WS/PHASE_UPDATE'; payload: PhaseUpdatePayload }
  | { type: 'WS/FILES_CHANGED'; payload: FilesChangedPayload }
  | { type: 'WS/MESSAGE_COMPLETE'; payload: MessageCompletePayload }
  | { type: 'WS/TOOL_CALL'; payload: ToolCallPayload }
  | { type: 'WS/STREAM_TOKEN'; payload: StreamTokenPayload }
  | { type: 'WS/ERROR'; payload: ErrorPayload }
  | { type: 'WS/TASK_DAG'; payload: TaskDagPayload }
  | { type: 'WS/TASK_STATUS'; payload: TaskStatusPayload }
  | { type: 'WS/EXECUTION_STATE'; payload: ExecutionStatePayload }
  | { type: 'WS/DELTA_PLAN'; payload: DeltaPlanPayload }
  /** PR5：M1' rebalance 失败 / 介入处理异常时回退 */
  | { type: 'WS/INTERRUPT_FAILED'; reason: string };

// ── 2. UI 交互 actions ──

export type UiAction =
  // 用户发送消息
  | { type: 'UI/USER_SEND_MESSAGE'; content: string }
  // 用户介入（软介入）
  | { type: 'UI/USER_SOFT_INTERRUPT'; content: string }
  // 用户硬中断
  | { type: 'UI/USER_HARD_INTERRUPT' }
  // 用户暂停后恢复
  | { type: 'UI/USER_RESUME'; content?: string }
  // 用户点击 HITL「我来回答」
  | { type: 'UI/HITL_ENTER_ANSWERING'; hitlId: string }
  // 用户点击 HITL「取消回答」(退回 pending)
  | { type: 'UI/HITL_EXIT_ANSWERING'; hitlId: string }
  // 用户回答 HITL（通过输入框 / 按钮）
  | { type: 'UI/HITL_ANSWER'; hitlId: string; answer: string }
  // 打开/关闭抽屉
  | { type: 'UI/TOGGLE_DRAWER'; drawer: DrawerKind | null }
  // 调整抽屉宽度
  | { type: 'UI/SET_DRAWER_WIDTH'; width: number }
  // 展开/折叠 Agent 消息卡
  | { type: 'UI/TOGGLE_MESSAGE_EXPANDED'; messageId: string }
  // 展开/折叠验证卡
  | { type: 'UI/TOGGLE_VERIFICATION_EXPANDED'; messageId: string };

// ── 3. 内部控制 actions ──

export type CtrlAction =
  // 切换 session（重置状态）
  | { type: 'CTRL/INIT_SESSION'; sessionId: string }
  // WS 连接状态
  | { type: 'CTRL/WS_CONNECTED'; connected: boolean }
  // 历史消息加载完成（可同时携带派生的 workPlan / artifacts，避免 reload 后抽屉为空）
  | {
      type: 'CTRL/HISTORY_LOADED';
      messages: import('../types/state').TimelineItem[];
      workPlan?: import('../types/state').WorkPlan | null;
      artifacts?: import('../types/state').ArtifactFile[];
      routing?: import('../types/state').RoutingMode;
      workspacePath?: string;
    }
  // Tick（更新 thinkingAgents 耗时显示）—— UI 层每秒调用，但 state 不存耗时（耗时在 UI selector 算）
  | { type: 'CTRL/TICK' };

export type ChatRoomAction = WsAction | UiAction | CtrlAction;

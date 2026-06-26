/** Chat room global state model
 *
 * 全局状态模型，覆盖 Week 10 重构所有需求：
 * - 对话流（messages timeline）
 * - 维度 A 系统协作阶段（metaPhases）
 * - 维度 B 业务任务计划（workPlan）
 * - 思考指示器（thinkingAgents）
 * - 执行控制（executionState + pendingInterrupt）
 * - HITL 状态机（pendingHitl + answeringHitlId）
 * - 抽屉（openDrawer + 数据）
 *
 * 设计原则：可序列化 + 纯数据 + 不含函数。任何派生数据走 selector。
 */

// ── 系统协作阶段（维度 A · Meta Phase） ──

/** M0~M7 阶段标识 */
export type MetaPhaseId =
  | 'm0_intent'
  | 'm1_analyze'
  | 'm2_clarify'
  | 'm3_orchestrate'
  | 'm4_decompose'
  | 'm6_execute'
  | 'm7_verify';

/** 阶段状态 */
export type MetaPhaseStatus =
  | 'pending'    // 未开始
  | 'thinking'   // 进行中
  | 'waiting'    // 等待用户（HITL）
  | 'done'       // 已完成
  | 'skipped'    // 跳过（单 Agent 路径）
  | 'failed';    // 失败

/** 单个 M 阶段的状态 */
export interface MetaPhaseState {
  id: MetaPhaseId;
  label: string;          // "M0·意图识别"
  shortLabel: string;     // "意图"
  status: MetaPhaseStatus;
  /** 当前活跃 Agent 名称（thinking 期间）*/
  currentAgent?: string;
  /** 当前活跃 Agent 摘要 */
  currentSummary?: string;
  /** 开始时间 ms */
  startedAt?: number;
  /** 结束时间 ms */
  endedAt?: number;
  /** 阶段摘要（done 后填充）*/
  summary?: string;
  /** 二轮重规划时的代号，"" / "'" / "''" 等 */
  iteration?: number;
}

/** 路由模式 */
export type RoutingMode = 'single_agent' | 'multi_agent' | null;

// ── 业务任务（维度 B · Work Plan） ──

/** 任务状态 */
export type WorkTaskStatus =
  | 'pending'      // 未开始
  | 'running'      // 进行中
  | 'done'         // 已完成
  | 'failed'       // 失败
  | 'retrying'     // 重试中
  | 'modified'     // 介入修改（需重做）
  | 'new'          // 介入新增
  | 'cancelled';   // 介入取消

/** 单个业务任务 */
export interface WorkTask {
  id: string;                  // "T3.2"
  phaseId: string;             // "phase-3"
  name: string;                // "看板布局设计"
  agentId: string;
  agentName: string;
  agentEmoji: string;
  dependsOn: string[];         // 其它 task_id
  status: WorkTaskStatus;
  startedAt?: number;
  endedAt?: number;
  /** 版本号，介入修改后递增 */
  version: number;
  /** 修改原因（modified / cancelled 时填写） */
  modifyReason?: string;
  /** 产物文件 ids，引用 artifacts slice */
  artifactIds: string[];
}

/** 业务任务阶段 */
export interface WorkPhase {
  id: string;                  // "phase-1"
  name: string;                // "PRD 撰写"
  status: 'pending' | 'running' | 'done' | 'partial';
  taskIds: string[];
  startedAt?: number;
  endedAt?: number;
}

/** 完整业务任务计划 */
export interface WorkPlan {
  phases: WorkPhase[];
  tasks: Record<string, WorkTask>;   // 平铺，便于按 id 查询
  totalTasks: number;
  doneTasks: number;
}

/** Delta plan（介入后的增量计划） */
export interface DeltaPlan {
  summary: string;
  keep: string[];                              // task_id list
  modify: Array<{ taskId: string; reason: string; newVersion: number }>;
  add: WorkTask[];
  cancel: Array<{ taskId: string; reason: string }>;
}

// ── 思考指示器 ──

/** 思考指示器单行（活跃 Agent） */
export interface ThinkingAgent {
  /** 用作 dedup key */
  agentId: string;
  agentName: string;
  agentEmoji: string;
  /** 当前所在系统阶段 */
  metaPhase?: MetaPhaseId;
  /** 当前业务任务（M6 中） */
  taskId?: string;
  /** 实时摘要文本（截断到 ~30 字） */
  summary: string;
  /** 模型名 */
  model?: string;
  /** 开始时间 ms，UI 端 tick 计算耗时 */
  startedAt: number;
  /** 是 idle 还是 thinking */
  status: 'thinking' | 'idle' | 'waiting';
}

// ── 执行控制 + 介入 ──

/** 整个会话的执行状态 */
export type ExecutionState =
  | 'idle'              // 空闲，等用户提问
  | 'thinking'          // Agent 思考中（M0~M4）
  | 'executing'         // Worker 执行中（M6）
  | 'hitl_pending'      // 等用户回答 HITL
  | 'paused'            // 已暂停（硬中断后）
  | 'interrupting';     // 处理介入中（M1' rebalance 进行中）

/** 待处理的介入请求 */
export interface PendingInterrupt {
  id: string;
  userMessage: string;
  /** 软介入 / 硬中断 */
  mode: 'soft' | 'hard';
  triggeredAt: number;
  state: 'awaiting_pause' | 'analyzing' | 'awaiting_confirm' | 'applied' | 'rejected';
}

// ── HITL ──

export type HitlKind = 'clarification' | 'confirmation' | 'agent_invite' | 'review' | 'delta_plan';

/** HITL 卡片状态 */
export type HitlCardState = 'pending' | 'answering' | 'answered';

export interface HitlOption {
  label: string;
  value: string;
  /** 选项描述（hover tooltip），可选 */
  description?: string;
}

export interface PendingHitl {
  id: string;
  kind: HitlKind;
  message: string;
  options: HitlOption[];
  cardState: HitlCardState;
  /** 用户的回答（answered 后填充） */
  answer?: string;
  /** delta_plan 专属，介入 delta_plan 时附带 */
  deltaPlan?: DeltaPlan;
  createdAt: number;
}

// ── 抽屉 ──

export type DrawerKind = 'plan' | 'artifacts' | 'team' | 'workflow';

/** 单个抽屉状态 */
export interface DrawerState {
  kind: DrawerKind;
  width: number;    // 该抽屉宽度百分比 (20-60)
  order: number;    // 打开顺序（用于堆叠排列）
}

// ── 产物 ──

export interface ArtifactFile {
  id: string;
  name: string;
  path: string;
  sizeBytes: number;
  producerAgentId: string;
  producerAgentName: string;
  producerTaskId?: string;
  status: 'created' | 'modified' | 'deleted';
  createdAt: number;
}

// ── 团队 ──

export interface TeamAgentState {
  agentId: string;
  agentName: string;
  agentEmoji: string;
  role: string;
  /** 实时状态 */
  status: 'idle' | 'thinking' | 'working' | 'done';
  /** 当前正在做的任务（执行期间） */
  currentTaskId?: string;
  /** 当前所在阶段 */
  currentMetaPhase?: MetaPhaseId;
  /** 累计耗时 ms */
  totalDuration: number;
}

// ── 对话流时间线条目 ──

/** 工具调用记录 */
export interface ToolCallRecord {
  tool: string;
  status: 'running' | 'done' | 'error';
  detail?: string;
}

/** Agent 推理详情 */
export interface ReasoningDetail {
  /** 主管分析文本 */
  supervisorAnalysis?: string;
  /** 思考步骤文本 */
  thinkingSteps?: string;
  /** 决策摘要 */
  decisionSummary?: string;
  /** 模型路由信息 */
  modelRouting?: {
    complexity?: string;
    selectedModel?: string;
    fallbackUsed?: boolean;
    fallbackReason?: string;
    provider?: string;
  };
  /** 工具调用列表 */
  toolCalls?: ToolCallRecord[];
}

/** 时间线条目联合类型 */
export type TimelineItem =
  | UserMessageItem
  | UserInterruptItem
  | SystemDividerItem
  | AgentMessageItem
  | HitlCardItem
  | VerificationItem
  | SystemSummaryItem;

export interface UserMessageItem {
  id: string;
  kind: 'user_message';
  content: string;
  timestamp: number;
}

export interface UserInterruptItem {
  id: string;
  kind: 'user_interrupt';
  content: string;
  /** 触发的介入模式 */
  mode: 'soft' | 'hard';
  timestamp: number;
}

export interface SystemDividerItem {
  id: string;
  kind: 'system_divider';
  /** 分隔线类型 */
  reason: 'interrupt' | 'm6_start' | 'm6_done' | 'delta_applied' | 'paused' | 'resumed';
  text: string;
  timestamp: number;
}

export interface AgentMessageItem {
  id: string;
  kind: 'agent_message';
  agentId: string;
  agentName: string;
  agentEmoji: string;
  /** 维度 A 系统阶段。
   *  null 表示"未知阶段"——UI 端应隐藏 phase chip 而非编造一个 M-id。
   *  单 Agent 路径的回复也可能是 null（不显示 meta phase chip）。 */
  metaPhase: MetaPhaseId | null;
  /** 维度 B 业务任务（M6 中才有） */
  taskId?: string;
  /** 阶段二轮代号（介入后） */
  iteration?: number;
  content: string;
  /** 推理详情（展开区） */
  reasoning?: ReasoningDetail;
  /** 模型名 */
  model?: string;
  /** 耗时 ms */
  latency?: number;
  /** 关联产物文件 ids */
  artifactIds: string[];
  /** UI 状态：是否展开 */
  expanded: boolean;
  /** UI 状态：流式中 */
  isStreaming: boolean;
  timestamp: number;
}

export interface HitlCardItem {
  id: string;
  kind: 'hitl_card';
  /** 对应 PendingHitl.id */
  hitlId: string;
  /** 卡片状态（同 PendingHitl.cardState） */
  cardState: HitlCardState;
  hitlKind: HitlKind;
  message: string;
  options: HitlOption[];
  answer?: string;
  deltaPlan?: DeltaPlan;
  timestamp: number;
}

export interface VerificationItem {
  id: string;
  kind: 'verification';
  passed: boolean;
  severity: 'none' | 'minor' | 'major' | 'critical';
  feedback: string;
  suggestions: string[];
  expanded: boolean;
  timestamp: number;
}

export interface SystemSummaryItem {
  id: string;
  kind: 'system_summary';
  summary: string;
  totalDurationMs: number;
  totalTasks: number;
  totalArtifacts: number;
  timestamp: number;
}

// ── 全局 state ──

export interface ChatRoomState {
  // 会话标识
  sessionId: string;

  // 对话流
  messages: TimelineItem[];

  // 维度 A 系统阶段
  metaPhases: MetaPhaseState[];
  currentMetaPhaseId: MetaPhaseId | null;
  routing: RoutingMode;

  // 维度 B 业务任务
  workPlan: WorkPlan | null;
  workPlanVersion: number;
  /** 最近一次介入的 diff（用于抽屉顶部摘要条） */
  workPlanDelta: DeltaPlan | null;

  // 思考指示器
  thinkingAgents: ThinkingAgent[];

  // 执行控制 + 介入
  executionState: ExecutionState;
  pendingInterrupt: PendingInterrupt | null;

  // HITL
  pendingHitl: PendingHitl | null;
  /** 用户点了"我来回答"的卡片 id（拦截输入框） */
  answeringHitlId: string | null;

  // 抽屉（支持多开，最多 3 个）
  openDrawers: DrawerState[];

  // 产物
  artifacts: ArtifactFile[];

  // 团队
  teamAgents: TeamAgentState[];

  // WS 连接
  wsConnected: boolean;

  // 工作空间路径
  workspacePath?: string;
}

// ── 阶段静态定义 ──

export const META_PHASES_STATIC: ReadonlyArray<{
  id: MetaPhaseId;
  label: string;
  shortLabel: string;
}> = [
  { id: 'm0_intent',      label: 'M0·意图识别',  shortLabel: '意图' },
  { id: 'm1_analyze',     label: 'M1·需求分析',  shortLabel: '分析' },
  { id: 'm2_clarify',     label: 'M2·澄清确认',  shortLabel: '澄清' },
  { id: 'm3_orchestrate', label: 'M3·Agent 编排', shortLabel: '编排' },
  { id: 'm4_decompose',   label: 'M4·任务分解',  shortLabel: '分解' },
  { id: 'm6_execute',     label: 'M6·DAG 执行',  shortLabel: '执行' },
  { id: 'm7_verify',      label: 'M7·独立验证',  shortLabel: '验证' },
] as const;

/** 创建初始 MetaPhaseState 列表 */
export function makeInitialMetaPhases(): MetaPhaseState[] {
  return META_PHASES_STATIC.map(p => ({
    ...p,
    status: 'pending' as const,
  }));
}

/** 创建初始 state */
export function makeInitialChatRoomState(sessionId: string): ChatRoomState {
  return {
    sessionId,
    messages: [],
    metaPhases: makeInitialMetaPhases(),
    currentMetaPhaseId: null,
    routing: null,
    workPlan: null,
    workPlanVersion: 0,
    workPlanDelta: null,
    thinkingAgents: [],
    executionState: 'idle',
    pendingInterrupt: null,
    pendingHitl: null,
    answeringHitlId: null,
    openDrawers: [],
    artifacts: [],
    teamAgents: [],
    wsConnected: false,
  };
}

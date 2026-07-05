/** useSessionHistory — 加载会话历史消息 + 反推 workPlan / artifacts
 *
 * 仅在「空白会话」首次挂载时触发，避免覆盖 WS 实时消息。
 *
 * 派生数据：
 *   - workPlan: 从 source=m6_execute 的 worker 消息提取 task_id/title → 构建任务列表
 *   - artifacts: 从 reasoning.tool_calls 中的 file-ops 提取产物文件
 *   - routing: 若有任何 m1_analyze / m6_execute 等消息 → multi_agent
 */
import { useEffect } from 'react';
import type { ChatRoomAction } from '../store/actions';
import type {
  TimelineItem,
  UserMessageItem,
  AgentMessageItem,
  HitlCardItem,
  ReasoningDetail,
  WorkPlan,
  WorkPhase,
  WorkTask,
  ArtifactFile,
  RoutingMode,
  MetaPhaseId,
} from '../types/state';

const API_BASE = (import.meta as unknown as { env: Record<string, string> }).env?.VITE_API_URL || '';

interface RawHistoryMessage {
  id: string;
  role: string;
  content: string;
  agent_name?: string;
  timestamp: string;
  metadata?: Record<string, unknown>;
}

const META_PHASE_IDS = new Set<string>([
  'm0_intent', 'm1_analyze', 'm1_rebalance', 'm2_clarify',
  'm3_orchestrate', 'm4_decompose', 'm6_execute', 'm7_verify',
  'langgraph',  // Mode 3 图编排
]);

const ROLE_EMOJI: Record<string, string> = {
  architect: '🏗',
  backend_dev: '💻',
  frontend_dev: '🌐',
  pm: '📋',
  ui_designer: '🎨',
  tester: '🧪',
  devops: '🚀',
  supervisor: '👑',
};

function inferEmoji(agentName: string): string {
  const lower = agentName.toLowerCase();
  if (lower.includes('架构')) return '🏗';
  if (lower.includes('产品') || lower.includes('pm')) return '📋';
  if (lower.includes('前端') || lower.includes('frontend')) return '🌐';
  if (lower.includes('后端') || lower.includes('backend')) return '💻';
  if (lower.includes('ui') || lower.includes('设计')) return '🎨';
  if (lower.includes('测试') || lower.includes('test') || lower.includes('qa')) return '🧪';
  if (lower.includes('devops') || lower.includes('运维') || lower.includes('部署')) return '🚀';
  if (lower.includes('super') || lower.includes('主管')) return '👑';
  return '🤖';
}

/** 将后端 hitl_type 映射为前端的 HitlKind */
function mapHitlTypeToKind(hitlType: string): HitlCardItem['hitlKind'] {
  switch (hitlType) {
    case 'select':
    case 'confirmation':
      return 'confirmation';
    case 'multi_select':
    case 'clarification':
      return 'clarification';
    case 'answer':
    case 'review':
      return 'review';
    case 'agent_invite':
      return 'agent_invite';
    case 'delta_plan':
      return 'delta_plan';
    default:
      return 'confirmation';
  }
}

function toTimelineItem(m: RawHistoryMessage): TimelineItem | null {
  const ts = new Date(m.timestamp).getTime();
  const meta = (m.metadata || {}) as Record<string, unknown>;

  if (m.role === 'user') {
    const item: UserMessageItem = {
      id: m.id,
      kind: 'user_message',
      content: m.content,
      timestamp: ts,
    };
    return item;
  }

  // HITL 卡片：从 metadata 中的 hitl_notification / hitl_options 重建
  if (meta.hitl_notification) {
    const hitlId = (meta.hitl_id as string) || `hitl-${m.id}`;
    const rawHitlType = (meta.hitl_type as string) || 'confirmation';
    const hitlKind = mapHitlTypeToKind(rawHitlType);
    const rawOptions: unknown[] = (meta.hitl_options as unknown[]) || [];
    // 按 value 去重，保留第一个
    const seenValues = new Set<string>();
    const options = rawOptions
      .map((opt: unknown) => {
        if (typeof opt === 'string') return { label: opt, value: opt };
        const o = opt as Record<string, unknown>;
        return {
          label: (o.label as string) || (o.value as string) || '',
          value: (o.value as string) || '',
          description: (o.description as string) || undefined,
        };
      })
      .filter(opt => {
        if (seenValues.has(opt.value)) return false;
        seenValues.add(opt.value);
        return true;
      });

    // 检查是否有对应的回答
    const hitlResponse = meta.hitl_response as string | undefined;
    const isResolved = !!hitlResponse;
    const cardState: HitlCardItem['cardState'] = isResolved ? 'answered' : 'pending';

    const item: HitlCardItem = {
      id: m.id,
      kind: 'hitl_card',
      hitlId,
      cardState,
      hitlKind,
      message: (meta.hitl_message as string) || m.content,
      options,
      answer: hitlResponse,
      timestamp: ts,
    };
    return item;
  }

  if (m.role === 'assistant' || m.role === 'system') {
    const agentName = (meta.agent as string) || m.agent_name || 'Agent';
    const reasoning: ReasoningDetail | undefined =
      (meta.thinking_steps || meta.tool_calls || meta.model_routing || meta.decision_summary
        || meta.history || meta.reflections || meta.samples || meta.plan || meta.tool_results
        || meta.review_score != null || meta.exec_mode)
        ? {
            supervisorAnalysis: meta.supervisor_analysis as string | undefined,
            thinkingSteps: meta.thinking_steps as string | undefined,
            decisionSummary: meta.decision_summary as string | undefined,
            modelRouting: meta.model_routing as ReasoningDetail['modelRouting'],
            toolCalls: meta.tool_calls as ReasoningDetail['toolCalls'],
            execMode: meta.exec_mode as string | undefined,
            iterations: meta.iterations as number | undefined,
            // 模式专属数据（与 AgentCardExpandable 读取的 key 保持一致）
            history: meta.history as string[] | undefined,
            reflections: meta.reflections as Array<Record<string, unknown>> | undefined,
            samples: meta.samples as string[] | undefined,
            merged: meta.merged as boolean | undefined,
            plan: meta.plan as Record<string, unknown> | undefined,
            tool_results: meta.tool_results as Array<Record<string, unknown>> | undefined,
            review_score: meta.review_score as number | undefined,
          }
        : undefined;

    const source = meta.source as string | undefined;
    const metaPhase = source && META_PHASE_IDS.has(source) ? source as MetaPhaseId : null;
    const taskId = (meta.task_id as string | undefined) || undefined;

    const item: AgentMessageItem = {
      id: m.id,
      kind: 'agent_message',
      agentId: agentName,
      agentName,
      agentEmoji: inferEmoji(agentName),
      metaPhase,
      taskId,
      content: m.content,
      reasoning,
      model: (meta.model || (meta.model_routing as { selected_model?: string })?.selected_model) as string | undefined,
      latency: meta.latency as number | undefined,
      artifactIds: [],
      expanded: false,
      isStreaming: false,
      timestamp: ts,
    };
    return item;
  }

  return null;
}

/** 从消息元数据派生 WorkPlan / Artifacts / routing 等 */
function deriveExtras(
  raw: RawHistoryMessage[],
  items: TimelineItem[],
): {
  workPlan: WorkPlan | null;
  artifacts: ArtifactFile[];
  routing: RoutingMode;
} {
  const tasks: Record<string, WorkTask> = {};
  let totalTasks = 0;
  let doneTasks = 0;
  const artifacts: ArtifactFile[] = [];
  let isMultiAgent = false;
  const idToArtifactIds = new Map<string, string[]>();

  // role → phase 简单分桶（默认每个 task 自成 phase；若 phases 全在同一 source，就分一个 phase）
  for (const m of raw) {
    const meta = (m.metadata || {}) as Record<string, unknown>;
    const source = meta.source as string | undefined;
    const taskId = meta.task_id as string | undefined;
    if (source && META_PHASE_IDS.has(source)) {
      isMultiAgent = true;
    }
    // worker 完成的 task：source 实际是 m6_execute_worker（旧代码只匹配 m6_execute，
    // 导致 reload 后 workPlan 永远为空、抽屉无内容）。用 startsWith 兼容 m6_execute* 全家桶。
    const isWorkerDone = !!source && (source.startsWith('m6_execute') || source === 'langgraph');
    if (isWorkerDone && taskId) {
      const agentName = (meta.agent as string) || m.agent_name || 'Worker';
      const title = (meta.task_title as string) || taskId;
      if (!tasks[taskId]) {
        tasks[taskId] = {
          id: taskId,
          phaseId: 'phase-1', // 单一 phase 兜底
          name: title,
          agentId: agentName,
          agentName,
          agentEmoji: inferEmoji(agentName),
          dependsOn: [],
          status: 'done',
          version: 1,
          artifactIds: [],
          endedAt: new Date(m.timestamp).getTime(),
        };
        totalTasks += 1;
        doneTasks += 1;
      }
      // 派生 artifacts from tool_calls
      const toolCalls = (meta.tool_calls as Array<{ tool: string; params?: Record<string, unknown>; success?: boolean }> | undefined) || [];
      for (const tc of toolCalls) {
        if (!tc) continue;
        const tname = (tc.tool || '').toLowerCase();
        if (tname.includes('file') && tc.success !== false) {
          const params = tc.params || {};
          const path = (params.path || params.file_path || params.filename || params.name || 'unknown') as string;
          const artId = `art_hist_${artifacts.length}`;
          artifacts.push({
            id: artId,
            name: path.split('/').pop() || path,
            path,
            sizeBytes: 0,
            producerAgentId: agentName,
            producerAgentName: agentName,
            producerTaskId: taskId,
            status: 'created',
            createdAt: new Date(m.timestamp).getTime(),
          });
          if (!idToArtifactIds.has(m.id)) idToArtifactIds.set(m.id, []);
          idToArtifactIds.get(m.id)!.push(artId);
        }
      }
    }
  }

  // 把派生的 artifactIds 附到对应 timeline item
  for (const item of items) {
    if (item.kind === 'agent_message') {
      const ids = idToArtifactIds.get(item.id);
      if (ids) (item as AgentMessageItem).artifactIds.push(...ids);
    }
  }

  // 从 worker 完成消息派生粗略单阶段计划（兜底）；
  // 完整任务计划由 useSessionHistory 里的 /tasks 接口还原（见 load()）。
  const workPlan: WorkPlan | null = totalTasks > 0 ? {
    phases: [{
      id: 'phase-1',
      name: '协作任务',
      status: 'done',
      taskIds: Object.keys(tasks),
    }] as WorkPhase[],
    tasks,
    totalTasks,
    doneTasks,
  } : null;

  const routing: RoutingMode = isMultiAgent ? 'multi_agent' : null;

  return { workPlan, artifacts, routing };
}

export function useSessionHistory(
  sessionId: string,
  dispatch: React.Dispatch<ChatRoomAction>,
  /** 当前已渲染的消息数 — 若 >0 跳过历史加载（WS 实时消息为准） */
  currentMessageCount: number,
) {
  useEffect(() => {
    if (!sessionId) return;
    if (currentMessageCount > 0) return;

    let cancelled = false;

    async function load() {
      // 1. 加载历史消息
      const resp = await fetch(`${API_BASE}/api/v1/sessions/${sessionId}/messages?limit=200`);
      if (cancelled || !resp.ok) return;
      const data = await resp.json();
      const raw: RawHistoryMessage[] = data.messages || [];
      const items = raw.map(toTimelineItem).filter((x): x is TimelineItem => x !== null);
      if (items.length === 0) return;
      const extras = deriveExtras(raw, items);

      // 1b. 拉取持久化的会话任务（SessionTask），还原完整任务计划。
      // 优先级高于 deriveExtras 从 worker 消息派生的粗略计划；缺失时回退。
      try {
        const tasksResp = await fetch(`${API_BASE}/api/v1/sessions/${sessionId}/tasks`);
        if (!cancelled && tasksResp.ok) {
          const tasksData = await tasksResp.json();
          const persisted = (tasksData.tasks || []) as Array<{
            id: string; title: string; status: string; assigned_agent_name?: string;
          }>;
          if (persisted.length > 0) {
            const planTasks: Record<string, WorkTask> = {};
            const taskIds: string[] = [];
            for (const t of persisted) {
              const agent = t.assigned_agent_name || 'Worker';
              planTasks[t.id] = {
                id: t.id,
                phaseId: 'phase-tasks',
                name: t.title || t.id,
                agentId: agent,
                agentName: agent,
                agentEmoji: inferEmoji(agent),
                dependsOn: [],
                status: (t.status === 'done' || t.status === 'completed') ? 'done' : 'pending',
                version: 1,
                artifactIds: [],
              };
              taskIds.push(t.id);
            }
            const doneCount = Object.values(planTasks).filter(x => x.status === 'done').length;
            extras.workPlan = {
              phases: [{ id: 'phase-tasks', name: '协作任务', status: 'done', taskIds }],
              tasks: planTasks,
              totalTasks: taskIds.length,
              doneTasks: doneCount,
            };
          }
        }
      } catch {
        // 任务列表加载失败时回退到 deriveExtras 的结果
      }

      // 2. 加载 workspace 产物文件 + workspace path
      let workspacePath: string | undefined;
      try {
        // 并行获取 workspace path 和文件列表
        const [wsInfoResp, wsFilesResp] = await Promise.all([
          fetch(`${API_BASE}/api/v1/sessions/${sessionId}/workspace`),
          fetch(`${API_BASE}/api/v1/sessions/${sessionId}/workspace/files?recursive=true`),
        ]);
        if (!cancelled && wsInfoResp.ok) {
          const infoData = await wsInfoResp.json();
          workspacePath = (infoData as { path?: string }).path;
        }
        if (!cancelled && wsFilesResp.ok) {
          const wsData = await wsFilesResp.json();
          const wsFiles = (wsData.items || [])
            .filter((i: { is_dir: boolean }) => !i.is_dir)
            .map((f: { name: string; path: string; size: number; modified: string }, idx: number) => ({
              id: `art_ws_${idx}`,
              name: f.name,
              path: f.path,
              sizeBytes: f.size || 0,
              producerAgentId: '',
              producerAgentName: '',
              producerTaskId: undefined,
              status: 'created' as const,
              createdAt: new Date(f.modified).getTime(),
            }));
          // 合并去重（按 path 去重）
          const existingPaths = new Set(extras.artifacts.map(a => a.path));
          for (const wf of wsFiles) {
            if (!existingPaths.has(wf.path)) {
              extras.artifacts.push(wf);
            }
          }
        }
      } catch {
        // workspace 加载失败不影响主流程
      }

      if (cancelled) return;
      dispatch({
        type: 'CTRL/HISTORY_LOADED',
        messages: items,
        workPlan: extras.workPlan,
        artifacts: extras.artifacts,
        routing: extras.routing,
        workspacePath,
      });
    }

    load().catch(() => {});
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);
}

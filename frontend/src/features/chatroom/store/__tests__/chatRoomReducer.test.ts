/** chatRoomReducer 单元测试
 *
 * 覆盖每个 action → state 变更。
 * 不测 UI，不测 WS 连接。仅纯函数行为。
 */

import { describe, it, expect, beforeEach } from 'vitest';
import {
  chatRoomReducer,
  makeInitialReducerState,
  type ReducerState,
} from '../chatRoomReducer';
import { _resetIdSeqForTest } from '../helpers';
import type { ChatRoomAction } from '../actions';
import type {
  AgentMessageItem,
  HitlCardItem,
  UserMessageItem,
  SystemDividerItem,
  UserInterruptItem,
} from '../../types/state';

const SID = 'test-session';

function init(): ReducerState {
  _resetIdSeqForTest();
  return makeInitialReducerState(SID);
}

function reduce(state: ReducerState, ...actions: ChatRoomAction[]): ReducerState {
  return actions.reduce(chatRoomReducer, state);
}

describe('chatRoomReducer', () => {
  beforeEach(() => {
    _resetIdSeqForTest();
  });

  describe('CTRL', () => {
    it('INIT_SESSION resets to initial state with new sessionId', () => {
      const s1 = init();
      const s2 = chatRoomReducer(s1, { type: 'UI/USER_SEND_MESSAGE', content: 'hi' });
      const s3 = chatRoomReducer(s2, { type: 'CTRL/INIT_SESSION', sessionId: 'new-sid' });
      expect(s3.sessionId).toBe('new-sid');
      expect(s3.messages).toHaveLength(0);
      expect(s3.executionState).toBe('idle');
    });

    it('WS_CONNECTED updates connected flag', () => {
      const s = chatRoomReducer(init(), { type: 'CTRL/WS_CONNECTED', connected: true });
      expect(s.wsConnected).toBe(true);
    });

    it('HISTORY_LOADED sets messages', () => {
      const history: UserMessageItem[] = [
        { id: 'h1', kind: 'user_message', content: 'old', timestamp: 1 },
      ];
      const s = chatRoomReducer(init(), { type: 'CTRL/HISTORY_LOADED', messages: history });
      expect(s.messages).toEqual(history);
    });
  });

  describe('WS · routing_decision', () => {
    it('single_agent: marks M1~M7 as skipped, M0 as done', () => {
      const s = chatRoomReducer(init(), {
        type: 'WS/ROUTING_DECISION',
        payload: { mode: 'single_agent' },
      });
      expect(s.routing).toBe('single_agent');
      const m0 = s.metaPhases.find(p => p.id === 'm0_intent')!;
      const m1 = s.metaPhases.find(p => p.id === 'm1_analyze')!;
      expect(m0.status).toBe('done');
      expect(m1.status).toBe('skipped');
    });

    it('multi_agent: M0 done, M1~M7 pending', () => {
      const s = chatRoomReducer(init(), {
        type: 'WS/ROUTING_DECISION',
        payload: { mode: 'multi_agent' },
      });
      expect(s.routing).toBe('multi_agent');
      const m0 = s.metaPhases.find(p => p.id === 'm0_intent')!;
      const m1 = s.metaPhases.find(p => p.id === 'm1_analyze')!;
      expect(m0.status).toBe('done');
      expect(m1.status).toBe('pending');
    });
  });

  describe('WS · agent_status', () => {
    it('thinking on M-stage updates meta phase + adds thinking agent', () => {
      const s = chatRoomReducer(init(), {
        type: 'WS/AGENT_STATUS',
        payload: {
          agent_id: 'm1_analyze',
          agent_name: 'Supervisor',
          status: 'thinking',
          summary: 'M1·需求分析 正在工作...',
        },
      });
      expect(s.metaPhases.find(p => p.id === 'm1_analyze')!.status).toBe('thinking');
      expect(s.thinkingAgents).toHaveLength(1);
      expect(s.thinkingAgents[0].agentId).toBe('m1_analyze');
      expect(s.currentMetaPhaseId).toBe('m1_analyze');
    });

    it('done on M-stage clears thinking agent + currentMetaPhase', () => {
      const s1 = chatRoomReducer(init(), {
        type: 'WS/AGENT_STATUS',
        payload: { agent_id: 'm1_analyze', agent_name: 'Supervisor', status: 'thinking' },
      });
      const s2 = chatRoomReducer(s1, {
        type: 'WS/AGENT_STATUS',
        payload: { agent_id: 'm1_analyze', agent_name: 'Supervisor', status: 'done' },
      });
      expect(s2.metaPhases.find(p => p.id === 'm1_analyze')!.status).toBe('done');
      expect(s2.thinkingAgents).toHaveLength(0);
      expect(s2.currentMetaPhaseId).toBeNull();
    });

    it('thinking on a real worker agent (non M-stage) only updates thinking list', () => {
      const s = chatRoomReducer(init(), {
        type: 'WS/AGENT_STATUS',
        payload: {
          agent_id: 'uuid-worker-1',
          agent_name: '前端工程师',
          status: 'thinking',
          summary: '页面布局设计',
        },
      });
      expect(s.thinkingAgents).toHaveLength(1);
      expect(s.thinkingAgents[0].agentName).toBe('前端工程师');
      // M-stage 不受影响
      expect(s.metaPhases.every(p => p.status === 'pending')).toBe(true);
    });
  });

  describe('WS · agent_message', () => {
    it('appends agent_message item to timeline with correct meta phase', () => {
      const s = reduce(init(),
        { type: 'WS/AGENT_STATUS', payload: { agent_id: 'm1_analyze', agent_name: 'Supervisor', status: 'thinking' } },
        { type: 'WS/AGENT_MESSAGE', payload: { agent: 'Supervisor', content: '建议拆 7 阶段' }, source: 'm1_analyze' },
      );
      expect(s.messages).toHaveLength(1);
      const msg = s.messages[0] as AgentMessageItem;
      expect(msg.kind).toBe('agent_message');
      expect(msg.agentName).toBe('Supervisor');
      expect(msg.metaPhase).toBe('m1_analyze');
      expect(msg.content).toBe('建议拆 7 阶段');
      expect(msg.expanded).toBe(false);
      // 思考指示器移除
      expect(s.thinkingAgents).toHaveLength(0);
    });

    it('attaches pending reasoning from previous reasoning_complete', () => {
      const s = reduce(init(),
        { type: 'WS/AGENT_STATUS', payload: { agent_id: 'm1_analyze', agent_name: 'Supervisor', status: 'thinking' } },
        {
          type: 'WS/REASONING_COMPLETE',
          payload: {
            agent: 'Supervisor',
            decision_summary: '复杂度=medium，需要 7 阶段',
            thinking_steps: '...',
            model_routing: { selected_model: 'deepseek-v4-pro' },
            tool_calls: [],
            latency: 32000,
          },
        },
        { type: 'WS/AGENT_MESSAGE', payload: { agent: 'Supervisor', content: '完成' }, source: 'm1_analyze' },
      );
      const msg = s.messages[0] as AgentMessageItem;
      expect(msg.reasoning?.decisionSummary).toBe('复杂度=medium，需要 7 阶段');
      expect(msg.reasoning?.modelRouting?.selectedModel).toBe('deepseek-v4-pro');
      // pending reasoning 应被消费
      expect(s._internal.pendingReasonings['Supervisor']).toBeUndefined();
    });

    it('ignores empty content messages', () => {
      const s = reduce(init(),
        { type: 'WS/AGENT_MESSAGE', payload: { agent: 'Supervisor', content: '' } },
      );
      expect(s.messages).toHaveLength(0);
    });
  });

  describe('WS · hitl_request', () => {
    it('creates pendingHitl + adds hitl_card to timeline + sets executionState', () => {
      const s = chatRoomReducer(init(), {
        type: 'WS/HITL_REQUEST',
        payload: {
          type: 'clarification',
          message: '需要确认目标用户',
          options: [{ label: '我来回答', value: 'answer' }],
        },
      });
      expect(s.pendingHitl).not.toBeNull();
      expect(s.pendingHitl?.kind).toBe('clarification');
      expect(s.pendingHitl?.cardState).toBe('pending');
      expect(s.messages).toHaveLength(1);
      const card = s.messages[0] as HitlCardItem;
      expect(card.kind).toBe('hitl_card');
      expect(card.cardState).toBe('pending');
      expect(s.executionState).toBe('hitl_pending');
    });
  });

  describe('UI · HITL state machine', () => {
    function withPendingHitl(): ReducerState {
      return chatRoomReducer(init(), {
        type: 'WS/HITL_REQUEST',
        payload: {
          type: 'clarification',
          message: 'q',
          options: [{ label: '我来回答', value: 'answer' }],
        },
      });
    }

    it('ENTER_ANSWERING: pending → answering, sets answeringHitlId', () => {
      const s1 = withPendingHitl();
      const hitlId = s1.pendingHitl!.id;
      const s2 = chatRoomReducer(s1, { type: 'UI/HITL_ENTER_ANSWERING', hitlId });
      expect(s2.pendingHitl?.cardState).toBe('answering');
      expect(s2.answeringHitlId).toBe(hitlId);
      const card = s2.messages[0] as HitlCardItem;
      expect(card.cardState).toBe('answering');
    });

    it('EXIT_ANSWERING: answering → pending, clears answeringHitlId', () => {
      const s1 = withPendingHitl();
      const hitlId = s1.pendingHitl!.id;
      const s2 = chatRoomReducer(s1, { type: 'UI/HITL_ENTER_ANSWERING', hitlId });
      const s3 = chatRoomReducer(s2, { type: 'UI/HITL_EXIT_ANSWERING', hitlId });
      expect(s3.pendingHitl?.cardState).toBe('pending');
      expect(s3.answeringHitlId).toBeNull();
    });

    it('ANSWER: answering → answered, clears pendingHitl, stores answer', () => {
      const s1 = withPendingHitl();
      const hitlId = s1.pendingHitl!.id;
      const s2 = chatRoomReducer(s1, { type: 'UI/HITL_ENTER_ANSWERING', hitlId });
      const s3 = chatRoomReducer(s2, { type: 'UI/HITL_ANSWER', hitlId, answer: '企业团队' });
      expect(s3.pendingHitl).toBeNull();
      expect(s3.answeringHitlId).toBeNull();
      expect(s3.executionState).toBe('thinking');
      const card = s3.messages[0] as HitlCardItem;
      expect(card.cardState).toBe('answered');
      expect(card.answer).toBe('企业团队');
    });

    it('ENTER_ANSWERING with mismatched hitlId is no-op', () => {
      const s1 = withPendingHitl();
      const s2 = chatRoomReducer(s1, { type: 'UI/HITL_ENTER_ANSWERING', hitlId: 'wrong-id' });
      expect(s2.pendingHitl?.cardState).toBe('pending');
      expect(s2.answeringHitlId).toBeNull();
    });
  });

  describe('WS · phase_update（粗版 phases_plan）', () => {
    it('creates workPlan with rough phases (M1 阶段)', () => {
      const s = chatRoomReducer(init(), {
        type: 'WS/PHASE_UPDATE',
        payload: {
          phases: ['PRD 撰写', '架构设计', 'UI 设计'],
        },
      });
      expect(s.workPlan).not.toBeNull();
      expect(s.workPlan!.phases).toHaveLength(3);
      expect(s.workPlan!.phases[0].name).toBe('PRD 撰写');
      expect(s.workPlanVersion).toBe(1);
    });

    it('does not overwrite existing workPlan from task_dag', () => {
      const s1 = chatRoomReducer(init(), {
        type: 'WS/TASK_DAG',
        payload: {
          phases: [
            {
              id: 'p1',
              name: 'PRD',
              tasks: [{ id: 'T1.1', name: '故事', agent_id: 'pm-1', agent_name: 'PM' }],
            },
          ],
          total_tasks: 1,
        },
      });
      const s2 = chatRoomReducer(s1, {
        type: 'WS/PHASE_UPDATE',
        payload: { phases: ['不应覆盖'] },
      });
      expect(s2.workPlan!.totalTasks).toBe(1); // 还是 task_dag 的
    });
  });

  describe('WS · task_dag', () => {
    it('builds full WorkPlan from DAG payload', () => {
      const s = chatRoomReducer(init(), {
        type: 'WS/TASK_DAG',
        payload: {
          phases: [
            {
              id: 'p1',
              name: 'PRD 撰写',
              tasks: [
                { id: 'T1.1', name: '用户故事', agent_id: 'pm-1', agent_name: 'PM', agent_emoji: '📋' },
                { id: 'T1.2', name: '验收标准', agent_id: 'pm-1', agent_name: 'PM', agent_emoji: '📋', depends_on: ['T1.1'] },
              ],
            },
          ],
          total_tasks: 2,
        },
      });
      expect(s.workPlan).not.toBeNull();
      expect(s.workPlan!.totalTasks).toBe(2);
      expect(s.workPlan!.tasks['T1.1'].name).toBe('用户故事');
      expect(s.workPlan!.tasks['T1.2'].dependsOn).toEqual(['T1.1']);
      expect(s.workPlan!.phases[0].taskIds).toEqual(['T1.1', 'T1.2']);
      expect(s.workPlanVersion).toBe(1);
    });
  });

  describe('WS · task_status', () => {
    function withDag(): ReducerState {
      return chatRoomReducer(init(), {
        type: 'WS/TASK_DAG',
        payload: {
          phases: [
            {
              id: 'p1',
              name: 'PRD',
              tasks: [
                { id: 'T1.1', name: '故事', agent_id: 'pm-1', agent_name: 'PM', agent_emoji: '📋' },
              ],
            },
          ],
          total_tasks: 1,
        },
      });
    }

    it('running: updates task + adds thinking agent', () => {
      const s = chatRoomReducer(withDag(), {
        type: 'WS/TASK_STATUS',
        payload: { task_id: 'T1.1', status: 'running' },
      });
      expect(s.workPlan!.tasks['T1.1'].status).toBe('running');
      expect(s.thinkingAgents).toHaveLength(1);
      expect(s.thinkingAgents[0].taskId).toBe('T1.1');
    });

    it('done: updates task + removes thinking agent + increments doneTasks', () => {
      const s1 = chatRoomReducer(withDag(), {
        type: 'WS/TASK_STATUS',
        payload: { task_id: 'T1.1', status: 'running' },
      });
      const s2 = chatRoomReducer(s1, {
        type: 'WS/TASK_STATUS',
        payload: { task_id: 'T1.1', status: 'done', duration: 45000 },
      });
      expect(s2.workPlan!.tasks['T1.1'].status).toBe('done');
      expect(s2.workPlan!.doneTasks).toBe(1);
      expect(s2.thinkingAgents).toHaveLength(0);
    });
  });

  describe('WS · files_changed', () => {
    it('appends to artifacts slice', () => {
      const s = chatRoomReducer(init(), {
        type: 'WS/FILES_CHANGED',
        payload: {
          files: [
            { name: 'schema.sql', size: 1200, producer_agent_name: '架构师' },
            { name: 'tasks.py', size: 3400, producer_agent_name: '后端' },
          ],
        },
      });
      expect(s.artifacts).toHaveLength(2);
      expect(s.artifacts[0].name).toBe('schema.sql');
      expect(s.artifacts[0].sizeBytes).toBe(1200);
    });
  });

  describe('WS · message_complete', () => {
    it('finalizes all thinking phases + clears thinkingAgents + sets idle', () => {
      const s1 = chatRoomReducer(init(), {
        type: 'WS/AGENT_STATUS',
        payload: { agent_id: 'm1_analyze', agent_name: 'Supervisor', status: 'thinking' },
      });
      const s2 = chatRoomReducer(s1, {
        type: 'WS/MESSAGE_COMPLETE',
        payload: { message: 'done' },
      });
      expect(s2.metaPhases.find(p => p.id === 'm1_analyze')!.status).toBe('done');
      expect(s2.thinkingAgents).toHaveLength(0);
      expect(s2.executionState).toBe('idle');
    });
  });

  describe('UI · user send', () => {
    it('USER_SEND_MESSAGE: adds user item + placeholder thinking + thinking state', () => {
      const s = chatRoomReducer(init(), {
        type: 'UI/USER_SEND_MESSAGE',
        content: '帮我开发任务看板',
      });
      expect(s.messages).toHaveLength(1);
      expect(s.messages[0].kind).toBe('user_message');
      expect(s.thinkingAgents).toHaveLength(1);
      expect(s.thinkingAgents[0].agentId).toBe('__placeholder__');
      expect(s.executionState).toBe('thinking');
    });
  });

  describe('UI · interrupt', () => {
    it('SOFT_INTERRUPT: adds divider + user_interrupt item + sets pendingInterrupt + executionState=interrupting', () => {
      const s = chatRoomReducer(init(), {
        type: 'UI/USER_SOFT_INTERRUPT',
        content: '改用 MySQL',
      });
      expect(s.messages).toHaveLength(2);
      expect((s.messages[0] as SystemDividerItem).reason).toBe('interrupt');
      expect((s.messages[1] as UserInterruptItem).mode).toBe('soft');
      expect(s.pendingInterrupt?.mode).toBe('soft');
      expect(s.executionState).toBe('interrupting');
    });

    it('HARD_INTERRUPT: adds divider + paused state', () => {
      const s = chatRoomReducer(init(), {
        type: 'UI/USER_HARD_INTERRUPT',
      });
      expect(s.messages).toHaveLength(1);
      expect((s.messages[0] as SystemDividerItem).reason).toBe('paused');
      expect(s.pendingInterrupt?.mode).toBe('hard');
      expect(s.executionState).toBe('paused');
    });

    it('USER_RESUME: clears pendingInterrupt + executionState=executing', () => {
      const s1 = chatRoomReducer(init(), { type: 'UI/USER_HARD_INTERRUPT' });
      const s2 = chatRoomReducer(s1, { type: 'UI/USER_RESUME', content: '继续' });
      expect(s2.pendingInterrupt).toBeNull();
      expect(s2.executionState).toBe('executing');
    });
  });

  describe('WS · delta_plan (PR5)', () => {
    it('creates HITL with delta_plan kind + workPlanDelta + hitl_pending state', () => {
      const s = chatRoomReducer(init(), {
        type: 'WS/DELTA_PLAN',
        payload: {
          summary: 'PG→MySQL',
          keep: ['T1.1'],
          modify: [{ taskId: 'T2.2', reason: 'change DB', newVersion: 2 }],
          add: [],
          cancel: [],
          version: 2,
        },
      });
      expect(s.pendingHitl?.kind).toBe('delta_plan');
      expect(s.workPlanDelta?.summary).toBe('PG→MySQL');
      expect(s.executionState).toBe('hitl_pending');
      const card = s.messages[0] as HitlCardItem;
      expect(card.hitlKind).toBe('delta_plan');
      expect(card.deltaPlan?.summary).toBe('PG→MySQL');
    });
  });

  describe('WS · execution_state (PR5)', () => {
    it('updates executionState', () => {
      const s = chatRoomReducer(init(), {
        type: 'WS/EXECUTION_STATE',
        payload: { state: 'paused', reason: 'user_interrupt' },
      });
      expect(s.executionState).toBe('paused');
    });
  });

  describe('UI · drawer', () => {
    it('TOGGLE_DRAWER: opens then closes on second toggle', () => {
      const s1 = chatRoomReducer(init(), { type: 'UI/TOGGLE_DRAWER', drawer: 'plan' });
      expect(s1.openDrawer).toBe('plan');
      const s2 = chatRoomReducer(s1, { type: 'UI/TOGGLE_DRAWER', drawer: 'plan' });
      expect(s2.openDrawer).toBeNull();
    });

    it('TOGGLE_DRAWER: switches between drawers', () => {
      const s1 = chatRoomReducer(init(), { type: 'UI/TOGGLE_DRAWER', drawer: 'plan' });
      const s2 = chatRoomReducer(s1, { type: 'UI/TOGGLE_DRAWER', drawer: 'artifacts' });
      expect(s2.openDrawer).toBe('artifacts');
    });

    it('SET_DRAWER_WIDTH clamps to [20, 60]', () => {
      const s1 = chatRoomReducer(init(), { type: 'UI/SET_DRAWER_WIDTH', width: 5 });
      expect(s1.drawerWidth).toBe(20);
      const s2 = chatRoomReducer(s1, { type: 'UI/SET_DRAWER_WIDTH', width: 100 });
      expect(s2.drawerWidth).toBe(60);
      const s3 = chatRoomReducer(s2, { type: 'UI/SET_DRAWER_WIDTH', width: 35 });
      expect(s3.drawerWidth).toBe(35);
    });
  });

  describe('UI · message expansion', () => {
    it('TOGGLE_MESSAGE_EXPANDED flips agent_message.expanded', () => {
      const s1 = reduce(init(),
        { type: 'WS/AGENT_MESSAGE', payload: { agent: 'PM', content: 'hi' }, source: 'm1_analyze' },
      );
      const msgId = s1.messages[0].id;
      const s2 = chatRoomReducer(s1, { type: 'UI/TOGGLE_MESSAGE_EXPANDED', messageId: msgId });
      expect((s2.messages[0] as AgentMessageItem).expanded).toBe(true);
      const s3 = chatRoomReducer(s2, { type: 'UI/TOGGLE_MESSAGE_EXPANDED', messageId: msgId });
      expect((s3.messages[0] as AgentMessageItem).expanded).toBe(false);
    });
  });

  describe('WS · interrupt_failed (PR5)', () => {
    it('rolls back pendingInterrupt + adds divider + executionState=executing if was interrupting', () => {
      const s1 = chatRoomReducer(init(), {
        type: 'UI/USER_SOFT_INTERRUPT',
        content: '改 MySQL',
      });
      expect(s1.executionState).toBe('interrupting');
      const s2 = chatRoomReducer(s1, {
        type: 'WS/INTERRUPT_FAILED',
        reason: 'M1 LLM 超时',
      });
      expect(s2.pendingInterrupt).toBeNull();
      expect(s2.executionState).toBe('executing');
      // divider 显示失败原因
      const lastMsg = s2.messages[s2.messages.length - 1];
      expect(lastMsg.kind).toBe('system_divider');
      if (lastMsg.kind === 'system_divider') {
        expect(lastMsg.text).toContain('M1 LLM 超时');
      }
    });
  });

  describe('决策 2 · HITL 待答时收到软介入', () => {
    it('auto-marks pendingHitl as answered + clears answeringHitlId', () => {
      let s = chatRoomReducer(init(), {
        type: 'WS/HITL_REQUEST',
        payload: {
          type: 'clarification',
          message: 'q',
          options: [{ label: '我来回答', value: 'answer' }],
        },
      });
      const hitlId = s.pendingHitl!.id;
      // 用户点了"我来回答"进入 answering
      s = chatRoomReducer(s, { type: 'UI/HITL_ENTER_ANSWERING', hitlId });
      expect(s.answeringHitlId).toBe(hitlId);
      // 但接着用户改主意，直接软介入
      s = chatRoomReducer(s, { type: 'UI/USER_SOFT_INTERRUPT', content: '不对，全部重做' });
      // HITL 应被自动 answered
      expect(s.pendingHitl).toBeNull();
      expect(s.answeringHitlId).toBeNull();
      const card = s.messages.find(m => m.kind === 'hitl_card');
      expect(card).toBeDefined();
      if (card?.kind === 'hitl_card') {
        expect(card.cardState).toBe('answered');
        expect(card.answer).toContain('用户介入');
      }
      expect(s.executionState).toBe('interrupting');
    });
  });

  describe('决策 · 单 Agent 路径的 agent_message metaPhase 为 null', () => {
    it('routing=single_agent → 后续 agent_message 的 metaPhase=null', () => {
      let s = chatRoomReducer(init(), {
        type: 'WS/ROUTING_DECISION',
        payload: { mode: 'single_agent', agent_name: 'PM' },
      });
      s = chatRoomReducer(s, {
        type: 'WS/AGENT_MESSAGE',
        payload: { agent: 'PM', content: '收到，开始处理' },
        source: 'm0_intent',
      });
      const msg = s.messages[0] as AgentMessageItem;
      expect(msg.metaPhase).toBeNull();
    });

    it('routing=multi_agent + 已知 source → metaPhase 正确反查', () => {
      let s = chatRoomReducer(init(), {
        type: 'WS/ROUTING_DECISION',
        payload: { mode: 'multi_agent' },
      });
      s = chatRoomReducer(s, {
        type: 'WS/AGENT_MESSAGE',
        payload: { agent: 'Supervisor', content: '分析中' },
        source: 'm1_analyze',
      });
      expect((s.messages[0] as AgentMessageItem).metaPhase).toBe('m1_analyze');
    });

    it('routing=multi_agent + 未知 source + 无 currentMetaPhase → null（不再编造 m1_analyze）', () => {
      let s = chatRoomReducer(init(), {
        type: 'WS/ROUTING_DECISION',
        payload: { mode: 'multi_agent' },
      });
      s = chatRoomReducer(s, {
        type: 'WS/AGENT_MESSAGE',
        payload: { agent: 'X', content: 'ghost' },
      });
      expect((s.messages[0] as AgentMessageItem).metaPhase).toBeNull();
    });
  });

  describe('集成 · 多 Agent 完整一轮', () => {
    it('user send → routing → M1 thinking → M1 message → HITL → answered → continue', () => {
      let s = init();
      s = chatRoomReducer(s, { type: 'UI/USER_SEND_MESSAGE', content: '帮我开发任务看板' });
      expect(s.executionState).toBe('thinking');

      s = chatRoomReducer(s, {
        type: 'WS/ROUTING_DECISION',
        payload: { mode: 'multi_agent', agent_name: 'Supervisor' },
      });
      expect(s.routing).toBe('multi_agent');

      s = chatRoomReducer(s, {
        type: 'WS/AGENT_STATUS',
        payload: { agent_id: 'm1_analyze', agent_name: 'Supervisor', status: 'thinking' },
      });
      expect(s.metaPhases.find(p => p.id === 'm1_analyze')!.status).toBe('thinking');

      s = chatRoomReducer(s, {
        type: 'WS/REASONING_COMPLETE',
        payload: {
          agent: 'Supervisor',
          decision_summary: '建议 7 阶段',
          model_routing: { selected_model: 'deepseek-v4-pro' },
          latency: 32000,
        },
      });

      s = chatRoomReducer(s, {
        type: 'WS/AGENT_MESSAGE',
        payload: { agent: 'Supervisor', content: '建议 7 阶段...' },
        source: 'm1_analyze',
      });
      // 用户消息 + supervisor 消息
      expect(s.messages).toHaveLength(2);

      s = chatRoomReducer(s, {
        type: 'WS/HITL_REQUEST',
        payload: {
          type: 'clarification',
          message: '目标用户？',
          options: [{ label: '我来回答', value: 'answer' }],
        },
      });
      expect(s.executionState).toBe('hitl_pending');
      expect(s.messages).toHaveLength(3);

      const hitlId = s.pendingHitl!.id;
      s = chatRoomReducer(s, { type: 'UI/HITL_ENTER_ANSWERING', hitlId });
      expect(s.answeringHitlId).toBe(hitlId);

      s = chatRoomReducer(s, { type: 'UI/HITL_ANSWER', hitlId, answer: '企业团队' });
      expect(s.pendingHitl).toBeNull();
      expect(s.answeringHitlId).toBeNull();
      const card = s.messages[2] as HitlCardItem;
      expect(card.cardState).toBe('answered');
      expect(card.answer).toBe('企业团队');
    });
  });
});

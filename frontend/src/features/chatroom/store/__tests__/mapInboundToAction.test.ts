/** mapInboundToAction 测试：每个 WS 事件类型必须映射为正确的 action */

import { describe, it, expect } from 'vitest';
import { mapInboundToAction } from '../../hooks/useWsEvents';
import type { InboundMessage } from '../../types/events';

describe('mapInboundToAction', () => {
  it('routing_decision', () => {
    const msg: InboundMessage = {
      type: 'routing_decision',
      payload: { mode: 'multi_agent', agent_name: 'Supervisor' },
    };
    expect(mapInboundToAction(msg)).toEqual({
      type: 'WS/ROUTING_DECISION',
      payload: { mode: 'multi_agent', agent_name: 'Supervisor' },
    });
  });

  it('agent_status', () => {
    const msg: InboundMessage = {
      type: 'agent_status',
      payload: {
        agent_id: 'm1_analyze',
        agent_name: 'Supervisor',
        status: 'thinking',
        summary: '...',
      },
    };
    const action = mapInboundToAction(msg);
    expect(action?.type).toBe('WS/AGENT_STATUS');
  });

  it('agent_message preserves source', () => {
    const msg: InboundMessage = {
      type: 'agent_message',
      source: 'm1_analyze',
      payload: { agent: 'Supervisor', content: '完成' },
    };
    const action = mapInboundToAction(msg);
    expect(action?.type).toBe('WS/AGENT_MESSAGE');
    if (action?.type === 'WS/AGENT_MESSAGE') {
      expect(action.source).toBe('m1_analyze');
    }
  });

  it('hitl_request', () => {
    const msg: InboundMessage = {
      type: 'hitl_request',
      payload: { type: 'clarification', message: 'q', options: [] },
    };
    expect(mapInboundToAction(msg)?.type).toBe('WS/HITL_REQUEST');
  });

  it('phase_update', () => {
    const msg: InboundMessage = {
      type: 'phase_update',
      payload: { phases: ['a', 'b'] },
    };
    expect(mapInboundToAction(msg)?.type).toBe('WS/PHASE_UPDATE');
  });

  it('task_dag', () => {
    const msg: InboundMessage = {
      type: 'task_dag',
      payload: { phases: [], total_tasks: 0 },
    };
    expect(mapInboundToAction(msg)?.type).toBe('WS/TASK_DAG');
  });

  it('task_status', () => {
    const msg: InboundMessage = {
      type: 'task_status',
      payload: { task_id: 'T1', status: 'running' },
    };
    expect(mapInboundToAction(msg)?.type).toBe('WS/TASK_STATUS');
  });

  it('execution_state', () => {
    const msg: InboundMessage = {
      type: 'execution_state',
      payload: { state: 'paused' },
    };
    expect(mapInboundToAction(msg)?.type).toBe('WS/EXECUTION_STATE');
  });

  it('delta_plan', () => {
    const msg: InboundMessage = {
      type: 'delta_plan',
      payload: {
        summary: 's',
        keep: [],
        modify: [],
        add: [],
        cancel: [],
        version: 1,
      },
    };
    expect(mapInboundToAction(msg)?.type).toBe('WS/DELTA_PLAN');
  });

  it('pong returns null', () => {
    expect(mapInboundToAction({ type: 'pong' })).toBeNull();
  });

  it('reasoning_complete / thinking_update / files_changed / message_complete / tool_call / stream_token / error 全部覆盖', () => {
    expect(mapInboundToAction({
      type: 'reasoning_complete',
      payload: { agent: 'a' },
    })?.type).toBe('WS/REASONING_COMPLETE');

    expect(mapInboundToAction({
      type: 'thinking_update',
      payload: { agent: 'a', step: 's', detail: 'd' },
    })?.type).toBe('WS/THINKING_UPDATE');

    expect(mapInboundToAction({
      type: 'files_changed',
      payload: { files: [] },
    })?.type).toBe('WS/FILES_CHANGED');

    expect(mapInboundToAction({
      type: 'message_complete',
      payload: { message: 'done' },
    })?.type).toBe('WS/MESSAGE_COMPLETE');

    expect(mapInboundToAction({
      type: 'tool_call',
      payload: { agent: 'a', tool: 't' },
    })?.type).toBe('WS/TOOL_CALL');

    expect(mapInboundToAction({
      type: 'stream_token',
      payload: { agent: 'a', token: 't', token_type: 'content_token' },
    })?.type).toBe('WS/STREAM_TOKEN');

    expect(mapInboundToAction({
      type: 'error',
      payload: { message: 'oops' },
    })?.type).toBe('WS/ERROR');
  });
});

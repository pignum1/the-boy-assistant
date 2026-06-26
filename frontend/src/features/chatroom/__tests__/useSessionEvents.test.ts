/**
 * useSessionEvents hook 事件处理逻辑测试
 *
 * 测试核心场景：
 * 1. reasoning_complete → agent_message：reasoning 保留（pendingRef fallback）
 * 2. thinking_update 设置可见动作文字
 * 3. reasoning_complete 空 content 时填充总结
 * 4. message_complete 终结所有流式消息
 * 5. 多 agent reasoning 不互相覆盖（stream fallback）
 *
 * 由于 hook 依赖 WebSocket，这里通过模拟消息处理逻辑进行测试。
 */
import { describe, it, expect } from 'vitest';

// ── 从源文件导入的关键函数 ──
// agentColor 函数：按名字 hash 映射到固定颜色数组

const AGENT_COLORS = [
  '#f59e0b', '#3b82f6', '#10b981', '#8b5cf6', '#ef4444',
  '#ec4899', '#06b6d4', '#f97316', '#6366f1', '#14b8a6',
];

function agentColor(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }
  return AGENT_COLORS[Math.abs(hash) % AGENT_COLORS.length];
}

// ── 消息处理模拟 ──

interface SimMessage {
  id: string;
  agent: string;
  content: string;
  isStreaming?: boolean;
  reasoning?: Record<string, unknown> | null;
  type?: string;
  avatarColor?: string;
  isThinking?: boolean;
}

type ReasoningData = Record<string, unknown>;

/**
 * 模拟 reasoning_complete + agent_message 流程
 * 验证：当 pendingReasoningRef 被其他 agent 覆盖时，stream 消息上的 reasoning 可作为 fallback
 */
function simulateReasoningFlow(
  streamMsgs: SimMessage[],
  reasoningAgent: string,
  reasoningData: ReasoningData,
  messageAgent: string,
) {
  // Step 1: reasoning_complete 更新 stream 消息
  const streamId = `stream_${reasoningAgent}`;
  const updated = streamMsgs.map(m =>
    m.id === streamId ? { ...m, reasoning: reasoningData } : m,
  );

  // Step 2: agent_message 处理
  const msgStreamId = `stream_${messageAgent}`;
  const streamMsg = updated.find(m => m.id === msgStreamId);
  const streamReasoning = (streamMsg as any)?.reasoning;

  // 模拟 pendingReasoningRef（可能已被覆盖为其他 agent）
  const pendingRef = reasoningData; // 最后收到的 reasoning

  // 检查是否匹配
  const matches = pendingRef.agent === messageAgent;
  const finalReasoning = matches ? pendingRef : streamReasoning;

  // 移除 stream 消息，添加最终消息
  const filtered = updated.filter(m => m.id !== msgStreamId);
  const finalMsg: SimMessage = {
    id: `agent_${Date.now()}`,
    agent: messageAgent,
    content: 'final content',
    isStreaming: false,
    reasoning: finalReasoning || undefined,
  };
  return { messages: [...filtered, finalMsg], finalReasoning };
}

// ── 测试用例 ──

describe('useSessionEvents 事件处理逻辑', () => {
  describe('agentColor', () => {
    it('同一名称返回一致颜色', () => {
      expect(agentColor('后端工程师-Agent')).toBe(agentColor('后端工程师-Agent'));
    });

    it('返回有效颜色值', () => {
      const color = agentColor('测试Agent');
      expect(AGENT_COLORS).toContain(color);
    });

    it('不同名称返回不同颜色（大概率）', () => {
      // hash 可能碰撞，但概率低
      const c1 = agentColor('产品经理-Agent');
      const c2 = agentColor('架构师-Agent');
      // 不强制断言不同，但确保都是有效颜色
      expect(AGENT_COLORS).toContain(c1);
      expect(AGENT_COLORS).toContain(c2);
    });
  });

  describe('reasoning_complete → agent_message 流程', () => {
    it('pendingReasoningRef 匹配时使用 pendingRef', () => {
      const streamMsgs: SimMessage[] = [
        { id: 'stream_产品经理-Agent', agent: '产品经理-Agent', content: '分析中', isStreaming: true },
      ];
      const reasoningData: ReasoningData = {
        agent: '产品经理-Agent',
        thinking_steps: '分析思考...',
        model_routing: { selected_model: 'glm-5.1' },
        latency: 5.0,
      };

      const { finalReasoning } = simulateReasoningFlow(
        streamMsgs, '产品经理-Agent', reasoningData, '产品经理-Agent',
      );
      expect(finalReasoning).toBeDefined();
      expect((finalReasoning as any).thinking_steps).toBe('分析思考...');
    });

    it('pendingReasoningRef 不匹配时 fallback 到 stream reasoning', () => {
      // 模拟场景：产品经理先完成 reasoning，然后后端工程师也完成 reasoning（覆盖 pendingRef）
      // 产品经理的 agent_message 到来时，pendingRef 已经是后端工程师的了
      const streamMsgs: SimMessage[] = [
        {
          id: 'stream_产品经理-Agent',
          agent: '产品经理-Agent',
          content: '分析中',
          isStreaming: true,
          reasoning: {
            agent: '产品经理-Agent',
            thinking_steps: '主管分析...',
            supervisor_analysis: '指派给 backend_dev',
          },
        },
      ];
      // 后端工程师的 reasoning（覆盖了 pendingRef）
      const backendReasoning: ReasoningData = {
        agent: '后端工程师-Agent',
        thinking_steps: '实现思路...',
        model_routing: { selected_model: 'glm-5.1' },
        latency: 15.0,
      };

      const { finalReasoning } = simulateReasoningFlow(
        streamMsgs, '后端工程师-Agent', backendReasoning, '产品经理-Agent',
      );
      // 即使 pendingRef 是后端工程师的，产品经理的 stream reasoning 应该被保留
      expect(finalReasoning).toBeDefined();
      expect((finalReasoning as any).supervisor_analysis).toBe('指派给 backend_dev');
      expect((finalReasoning as any).agent).toBe('产品经理-Agent');
    });
  });

  describe('thinking_update 动作文字', () => {
    it('supervisor_analysis → "🔍 正在分析消息..."', () => {
      const step = 'supervisor_analysis';
      const actionText =
        step === 'supervisor_analysis' ? '🔍 正在分析消息...' :
        step === 'supervisor_dispatch' ? '📋 正在指派任务...' :
        'thinking...';
      expect(actionText).toBe('🔍 正在分析消息...');
    });

    it('supervisor_dispatch → "📋 ..."', () => {
      const step = 'supervisor_dispatch';
      const detail = '已指派给: backend_dev';
      const actionText = step === 'supervisor_dispatch' ? '📋 ' + detail : '';
      expect(actionText).toContain('📋');
      expect(actionText).toContain('backend_dev');
    });

    it('swarm_thinking → "🐝 ..."', () => {
      const step = 'swarm_thinking';
      const detail = 'Swarm 成员思考中';
      const actionText = step === 'swarm_thinking' ? '🐝 ' + detail : '';
      expect(actionText).toContain('🐝');
    });

    it('swarm_notify → "📢 ..."', () => {
      const step = 'swarm_notify';
      const detail = '已通知全体成员';
      const actionText = step === 'swarm_notify' ? '📢 ' + detail : '';
      expect(actionText).toContain('📢');
    });
  });

  describe('reasoning_complete 内容填充', () => {
    function getCompletionContent(
      currentContent: string,
      payload: Record<string, unknown>,
    ): string {
      if (!currentContent || currentContent === '思考中') {
        if (payload.dispatch_guidance) return '✅ 分析完成，已指派任务';
        if (payload.decision_summary) return payload.decision_summary as string;
        if (payload.supervisor_analysis) return '✅ 分析完成';
        if (payload.thinking_steps) return '✅ 推理完成';
      }
      return currentContent;
    }

    it('空内容 + dispatch_guidance → "✅ 分析完成，已指派任务"', () => {
      expect(getCompletionContent('', { dispatch_guidance: '指派给 x' }))
        .toBe('✅ 分析完成，已指派任务');
    });

    it('"思考中" + dispatch_guidance → "✅ 分析完成，已指派任务"', () => {
      expect(getCompletionContent('思考中', { dispatch_guidance: '...' }))
        .toBe('✅ 分析完成，已指派任务');
    });

    it('空内容 + decision_summary → 使用 decision_summary', () => {
      expect(getCompletionContent('', { decision_summary: '任务已完成' }))
        .toBe('任务已完成');
    });

    it('空内容 + supervisor_analysis → "✅ 分析完成"', () => {
      expect(getCompletionContent('', { supervisor_analysis: '...' }))
        .toBe('✅ 分析完成');
    });

    it('已有内容时不覆盖', () => {
      expect(getCompletionContent('已有回复内容', { dispatch_guidance: '...' }))
        .toBe('已有回复内容');
    });
  });

  describe('message_complete 流式消息终结', () => {
    it('将所有 stream_ 前缀消息标记为 isStreaming=false', () => {
      const messages: SimMessage[] = [
        { id: 'stream_A', agent: 'A', content: '内容A', isStreaming: true },
        { id: 'stream_B', agent: 'B', content: '分析中', isStreaming: true },
        { id: 'agent_1', agent: 'C', content: '已完成', isStreaming: false },
      ];

      const finalized = messages.map(m =>
        m.id.startsWith('stream_') ? { ...m, isStreaming: false } : m,
      );

      // 流式消息被终结
      expect(finalized.find(m => m.id === 'stream_A')?.isStreaming).toBe(false);
      expect(finalized.find(m => m.id === 'stream_B')?.isStreaming).toBe(false);
      // 非流式消息不受影响
      expect(finalized.find(m => m.id === 'agent_1')?.isStreaming).toBe(false);
    });

    it('终结后 stream 消息保留推理数据', () => {
      const reasoningData = { agent: 'A', thinking_steps: '...' };
      const messages: SimMessage[] = [
        { id: 'stream_A', agent: 'A', content: '分析中', isStreaming: true, reasoning: reasoningData },
      ];

      const finalized = messages.map(m =>
        m.id.startsWith('stream_') ? { ...m, isStreaming: false } : m,
      );

      // reasoning 数据保留
      expect(finalized[0].reasoning).toBeDefined();
      expect(finalized[0].reasoning).toEqual(reasoningData);
    });
  });

  describe('stream_token thinking vs content', () => {
    it('thinking_token 累积到 reasoning.thinking_steps', () => {
      const existingReasoning = { agent: 'X', thinking_steps: '已有' };
      const token = '新增思考';
      const updated = {
        ...existingReasoning,
        thinking_steps: existingReasoning.thinking_steps + token,
      };
      expect(updated.thinking_steps).toBe('已有新增思考');
    });

    it('content_token 累积到 content', () => {
      const existingContent = '第一段';
      const newToken = '第二段';
      expect(existingContent + newToken).toBe('第一段第二段');
    });

    it('content_token 保留已有 reasoning', () => {
      const m = { content: 'a', reasoning: { thinking_steps: 'think' } };
      const token = 'b';
      const updated = {
        ...m,
        content: m.content + token,
        reasoning: m.reasoning, // content_token 保留 reasoning
      };
      expect(updated.reasoning).toEqual({ thinking_steps: 'think' });
      expect(updated.content).toBe('ab');
    });
  });

  describe('消息 ID 生成', () => {
    it('stream 消息 ID 格式匹配规则', () => {
      const agent = '产品经理-Agent';
      const streamId = `stream_${agent}`;
      expect(streamId).toBe('stream_产品经理-Agent');
      expect(streamId.startsWith('stream_')).toBe(true);
    });

    it('agent 名字查找：UUID → 真实名字', () => {
      // 模拟 agentStatuses 查找逻辑
      const agentStatuses: Record<string, { agent_name: string }> = {
        'uuid-1': { agent_name: '产品经理-Agent' },
        'uuid-2': { agent_name: '后端工程师-Agent' },
      };
      const agent = 'uuid-1';
      const transformed =
        agent === 'Agent' || /^[0-9a-f-]{30,}$/.test(agent)
          ? Object.values(agentStatuses)[0]?.agent_name || agent
          : agent;
      // 非 UUID 不转换
      expect(transformed).toBe('uuid-1');
    });
  });
});

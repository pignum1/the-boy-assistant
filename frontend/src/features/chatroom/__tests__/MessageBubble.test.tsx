/**
 * MessageBubble 组件测试 — Cherry Studio 风格消息渲染
 *
 * 测试覆盖：
 * 1. 用户消息 / Agent 消息 / 系统消息 / 错误消息
 * 2. 思考过程内联展示（深度思考）
 * 3. 代码块、表格、内联代码渲染
 * 4. 流式状态：输入中 / 已完成
 * 5. 状态文字 vs Markdown 内容区分
 */
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MessageBubble } from '../MessageBubble';
import type { ReasoningTrace } from '../../../shared/types/session';

// ── 测试辅助函数 ──

function makeMsg(overrides: Record<string, unknown> = {}) {
  return {
    id: 'agent_123',
    agent: '测试Agent',
    content: '这是一条测试消息',
    timestamp: Date.now(),
    type: 'message' as const,
    avatarColor: '#3b82f6',
    ...overrides,
  };
}

function makeReasoning(overrides: Partial<ReasoningTrace> = {}): ReasoningTrace {
  return {
    agent: '测试Agent',
    model_routing: {
      complexity: 'medium',
      selected_model: 'glm-5.1',
      fallback_used: false,
      provider: 'zhipu',
    },
    tool_calls: [],
    context_used: { memories_injected: 0, rag_chunks: 0, total_tokens: 1000 },
    thinking_steps: 'Test thinking content',
    latency: 3.5,
    ...overrides,
  };
}

// ── 测试用例 ──

describe('MessageBubble', () => {
  // ── 基础渲染 ──

  describe('基础消息类型', () => {
    it('渲染用户消息（右对齐），头像+名称均显示"我"', () => {
      const msg = makeMsg({ agent: '我', content: '用户消息' });
      render(<MessageBubble msg={msg} />);
      expect(screen.getByText('用户消息')).toBeInTheDocument();
      // "我" 出现在头像和名称两处
      const elements = screen.getAllByText('我');
      expect(elements.length).toBeGreaterThanOrEqual(2);
    });

    it('渲染 Agent 消息（左对齐，含头像和名称）', () => {
      const msg = makeMsg({ agent: '后端工程师-Agent', content: 'Agent 回复' });
      render(<MessageBubble msg={msg} />);
      expect(screen.getByText('Agent 回复')).toBeInTheDocument();
      expect(screen.getByText('后端工程师-Agent')).toBeInTheDocument();
      // 头像首字
      expect(screen.getByText('后')).toBeInTheDocument();
    });

    it('渲染系统消息（居中）', () => {
      const msg = makeMsg({ agent: 'System', content: '系统通知', type: 'system' });
      render(<MessageBubble msg={msg} />);
      expect(screen.getByText('系统通知')).toBeInTheDocument();
    });

    it('渲染错误消息（红色居中）', () => {
      const msg = makeMsg({ agent: 'System', content: '出错了', type: 'error' });
      render(<MessageBubble msg={msg} />);
      expect(screen.getByText('出错了')).toBeInTheDocument();
    });
  });

  // ── 深度思考内联展示 ──

  describe('思考过程（Cherry Studio 风格）', () => {
    it('有 reasoning.thinking_steps 时显示 "深度思考"', () => {
      const msg = makeMsg({ agent: '架构师-Agent', content: '分析结果' });
      const reasoning = makeReasoning({ thinking_steps: '步骤1: 分析...\n步骤2: 决策...' });
      render(<MessageBubble msg={msg} reasoning={reasoning} />);
      // 深度思考标题可见
      expect(screen.getByText('深度思考')).toBeInTheDocument();
      // 消息内容也可见
      expect(screen.getByText('分析结果')).toBeInTheDocument();
    });

    it('reasoning 中包含 supervisor_analysis 时展开可见', () => {
      const msg = makeMsg({ agent: '后端工程师-Agent', content: '代码实现' });
      const r = makeReasoning({ thinking_steps: '实现思路...' });
      (r as any).supervisor_analysis = '主管指派给: backend_dev';
      render(<MessageBubble msg={msg} reasoning={r} defaultThinkingOpen={true} />);
      expect(screen.getByText('深度思考')).toBeInTheDocument();
      // 展开后可见主管分析内容
      expect(screen.getByText(/主管指派给/)).toBeInTheDocument();
    });

    it('无 reasoning 时不显示思考过程', () => {
      const msg = makeMsg({ agent: '测试Agent', content: '纯文本回复' });
      render(<MessageBubble msg={msg} />);
      expect(screen.queryByText('深度思考')).not.toBeInTheDocument();
    });

    it('reasoning 无有效内容时不显示思考过程', () => {
      const msg = makeMsg({ agent: '测试Agent', content: '回复' });
      const reasoning = makeReasoning({
        thinking_steps: undefined,
        tool_calls: [],
        decision_summary: undefined,
      });
      render(<MessageBubble msg={msg} reasoning={reasoning} />);
      // thinking_steps 为空且无 tool_calls 时不渲染
      expect(screen.queryByText('深度思考')).not.toBeInTheDocument();
    });

    it('reasoning 有 tool_calls 时显示工具调用次数', () => {
      const msg = makeMsg({ agent: '后端工程师-Agent', content: '文件已创建' });
      const reasoning = makeReasoning({
        thinking_steps: '需要写文件',
        tool_calls: [
          { tool: 'file-ops', params: { operation: 'write' }, success: true, output: 'OK' },
          { tool: 'terminal', params: { cmd: 'ls' }, success: true, output: 'file.py' },
        ],
      });
      render(<MessageBubble msg={msg} reasoning={reasoning} defaultThinkingOpen={true} />);
      expect(screen.getByText(/2 次工具调用/)).toBeInTheDocument();
    });
  });

  // ── 流式状态 ──

  describe('流式消息状态', () => {
    it('isStreaming 时显示 "输入中..."', () => {
      const msg = makeMsg({ id: 'stream_test', content: '部分内容', isStreaming: true });
      render(<MessageBubble msg={msg} />);
      expect(screen.getByText('输入中...')).toBeInTheDocument();
    });

    it('stream 消息非流式时显示 "已完成" badge', () => {
      const msg = makeMsg({ id: 'stream_test', content: '最终内容', isStreaming: false });
      render(<MessageBubble msg={msg} />);
      expect(screen.getByText('已完成')).toBeInTheDocument();
    });

    it('流式时自动展开思考过程', () => {
      const msg = makeMsg({ id: 'stream_test', content: '内容', isStreaming: true });
      const reasoning = makeReasoning({ thinking_steps: 'thinking...' });
      render(<MessageBubble msg={msg} reasoning={reasoning} />);
      // 流式时 defaultOpen=true，思考内容可见
      expect(screen.getByText(/thinking\.\.\./)).toBeInTheDocument();
    });
  });

  // ── 状态文字展示 ──

  describe('状态文字展示', () => {
    it('🔍 状态文字使用特殊样式', () => {
      const msg = makeMsg({ content: '🔍 正在分析消息...' });
      render(<MessageBubble msg={msg} />);
      expect(screen.getByText('🔍 正在分析消息...')).toBeInTheDocument();
    });

    it('📋 状态文字使用特殊样式', () => {
      const msg = makeMsg({ content: '📋 调度结果: backend_dev' });
      render(<MessageBubble msg={msg} />);
      expect(screen.getByText('📋 调度结果: backend_dev')).toBeInTheDocument();
    });

    it('✅ 状态文字使用特殊样式', () => {
      const msg = makeMsg({ content: '✅ 分析完成，已指派任务' });
      render(<MessageBubble msg={msg} />);
      expect(screen.getByText('✅ 分析完成，已指派任务')).toBeInTheDocument();
    });
  });

  // ── Markdown 渲染 ──

  describe('Markdown 渲染', () => {
    it('渲染内联代码', () => {
      const msg = makeMsg({ content: '文件 `test.py` 已创建' });
      render(<MessageBubble msg={msg} />);
      // 内联代码在 code 标签中
      const code = screen.getByText('test.py');
      expect(code.tagName).toBe('CODE');
    });

    it('代码块应有语言标签和复制按钮', () => {
      const msg = makeMsg({ content: '```python\nprint("hello")\n```' });
      render(<MessageBubble msg={msg} />);
      expect(screen.getByText(/python/i)).toBeInTheDocument();
      // 复制按钮存在
      expect(screen.getByText(/复制/)).toBeInTheDocument();
    });

    it('多行代码（无语言标识）也渲染为代码块', () => {
      const msg = makeMsg({ content: '```\nline1\nline2\n```' });
      render(<MessageBubble msg={msg} />);
      expect(screen.getByText(/code/i)).toBeInTheDocument();
    });
  });

  // ── 头像渲染 ──

  describe('头像', () => {
    it('中文名取首字', () => {
      const msg = makeMsg({ agent: '架构师-Agent' });
      render(<MessageBubble msg={msg} />);
      expect(screen.getByText('架')).toBeInTheDocument();
    });

    it('英文名取首字母大写', () => {
      const msg = makeMsg({ agent: 'TestAgent' });
      render(<MessageBubble msg={msg} />);
      expect(screen.getByText('T')).toBeInTheDocument();
    });

    it('用户消息使用"我"作为标识', () => {
      const msg = makeMsg({ agent: '我', avatarColor: '#64748b' });
      render(<MessageBubble msg={msg} />);
      // 头像和名称都显示"我"
      const elements = screen.getAllByText('我');
      expect(elements.length).toBeGreaterThanOrEqual(2); // 头像 + 名称
    });
  });

  // ── 模型信息展示 ──

  describe('模型信息', () => {
    it('展开后显示模型名称和延迟', () => {
      const msg = makeMsg({ agent: '架构师-Agent', content: '分析' });
      const reasoning = makeReasoning({
        thinking_steps: 'thinking...',
        latency: 10.5,
      });
      render(<MessageBubble msg={msg} reasoning={reasoning} defaultThinkingOpen={true} />);
      // 模型名称出现在摘要标签和模型信息中，用 getAllByText
      const modelElements = screen.getAllByText(/glm-5\.1/);
      expect(modelElements.length).toBeGreaterThanOrEqual(2);
      // 延迟信息
      const latencyElements = screen.getAllByText(/10\.5s/);
      expect(latencyElements.length).toBeGreaterThanOrEqual(1);
    });

    it('显示 provider 信息', () => {
      const msg = makeMsg({ agent: '测试Agent', content: 'ok' });
      const reasoning = makeReasoning({
        thinking_steps: 'think',
        model_routing: { complexity: 'low', selected_model: 'gpt-4', fallback_used: false, provider: 'openai' },
      });
      render(<MessageBubble msg={msg} reasoning={reasoning} defaultThinkingOpen={true} />);
      expect(screen.getByText(/openai/)).toBeInTheDocument();
    });
  });
});

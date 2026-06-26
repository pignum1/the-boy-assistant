/**
 * ThinkingSection 组件测试 — 独立使用和 CherryThinkingSection 内联版
 *
 * 测试覆盖：
 * 1. 折叠/展开行为
 * 2. 主管分析展示
 * 3. 思考过程展示
 * 4. 工具调用展示
 * 5. 空内容隐藏
 */
import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ThinkingSection } from '../ThinkingSection';
import type { ReasoningTrace } from '../../../shared/types/session';

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
    thinking_steps: 'Test thinking',
    ...overrides,
  };
}

describe('ThinkingSection', () => {
  describe('渲染行为', () => {
    it('有思考内容时渲染', () => {
      const reasoning = makeReasoning({ thinking_steps: '步骤1\n步骤2' });
      render(<ThinkingSection reasoning={reasoning} />);
      expect(screen.getByText('深度思考')).toBeInTheDocument();
    });

    it('无思考内容且无工具调用时隐藏', () => {
      const reasoning = makeReasoning({
        thinking_steps: undefined,
        tool_calls: [],
        decision_summary: undefined,
      });
      // 清空 supervisor 等
      (reasoning as any).supervisor_analysis = undefined;
      (reasoning as any).dispatch_guidance = undefined;
      const { container } = render(<ThinkingSection reasoning={reasoning} />);
      expect(container.firstChild).toBeNull();
    });

    it('有工具调用但无思考步骤时仍显示', () => {
      const reasoning = makeReasoning({
        thinking_steps: undefined,
        tool_calls: [{ tool: 'read-file', params: {}, success: true, output: 'content' }],
      });
      render(<ThinkingSection reasoning={reasoning} />);
      expect(screen.getByText('深度思考')).toBeInTheDocument();
    });

    it('有 supervisor_analysis 时显示', () => {
      const reasoning = makeReasoning({
        thinking_steps: undefined,
        tool_calls: [],
      });
      (reasoning as any).supervisor_analysis = '主管分析了任务并指派给 backend_dev';
      render(<ThinkingSection reasoning={reasoning} />);
      expect(screen.getByText('深度思考')).toBeInTheDocument();
    });
  });

  describe('折叠/展开', () => {
    it('默认折叠时不显示思考内容', () => {
      const reasoning = makeReasoning({ thinking_steps: 'hidden content' });
      render(<ThinkingSection reasoning={reasoning} />);
      // 折叠时 header 可见，但内容（思考过程）不在 DOM 中
      expect(screen.getByText('深度思考')).toBeInTheDocument();
      expect(screen.queryByText('思考过程')).not.toBeInTheDocument();
    });

    it('点击标题展开后显示内容', () => {
      const reasoning = makeReasoning({
        thinking_steps: '展开后可见',
        latency: 5.2,
      });
      render(<ThinkingSection reasoning={reasoning} />);
      const header = screen.getByText('深度思考');
      fireEvent.click(header);
      // 展开后模型信息可见
      expect(screen.getByText('思考过程')).toBeInTheDocument();
    });

    it('defaultOpen=true 时默认展开', () => {
      const reasoning = makeReasoning({ thinking_steps: 'default visible' });
      render(<ThinkingSection reasoning={reasoning} defaultOpen={true} />);
      expect(screen.getByText('思考过程')).toBeInTheDocument();
    });
  });

  describe('标签摘要', () => {
    it('折叠状态下显示模型名称在摘要中', () => {
      const reasoning = makeReasoning({ thinking_steps: 't' });
      render(<ThinkingSection reasoning={reasoning} />);
      // 摘要标签中显示模型名称（折叠状态）
      const tags = screen.getByText(/glm-5\.1/);
      expect(tags).toBeInTheDocument();
    });

    it('显示工具调用次数', () => {
      const reasoning = makeReasoning({
        thinking_steps: 't',
        tool_calls: [
          { tool: 'a', params: {}, success: true, output: 'ok' },
          { tool: 'b', params: {}, success: false, output: '', error: 'err' },
          { tool: 'c', params: {}, success: true, output: 'ok' },
        ],
      });
      render(<ThinkingSection reasoning={reasoning} />);
      expect(screen.getByText(/3 次工具调用/)).toBeInTheDocument();
    });

    it('显示耗时', () => {
      const reasoning = makeReasoning({ thinking_steps: 't', latency: 12.34 });
      render(<ThinkingSection reasoning={reasoning} />);
      expect(screen.getByText(/12\.34s/)).toBeInTheDocument();
    });
  });

  describe('主管分析', () => {
    it('展开后显示主管分析内容', () => {
      const reasoning = makeReasoning({ thinking_steps: 't' });
      (reasoning as any).supervisor_analysis = '主管决定指派给架构师';
      render(<ThinkingSection reasoning={reasoning} defaultOpen={true} />);
      expect(screen.getByText('主管分析')).toBeInTheDocument();
      expect(screen.getByText('主管决定指派给架构师')).toBeInTheDocument();
    });

    it('展开后显示执行指导', () => {
      const reasoning = makeReasoning({ thinking_steps: 't' });
      (reasoning as any).dispatch_guidance = '实现架构分析';
      render(<ThinkingSection reasoning={reasoning} defaultOpen={true} />);
      expect(screen.getByText('执行指导')).toBeInTheDocument();
    });
  });

  describe('工具调用详情', () => {
    it('展开后显示成功工具调用', () => {
      const reasoning = makeReasoning({
        thinking_steps: 't',
        tool_calls: [{ tool: 'file-ops', params: { path: '/test.py' }, success: true, output: 'Written 100 chars' }],
      });
      render(<ThinkingSection reasoning={reasoning} defaultOpen={true} />);
      expect(screen.getByText(/file-ops/)).toBeInTheDocument();
      expect(screen.getByText(/✅/)).toBeInTheDocument();
    });

    it('展开后显示失败工具调用', () => {
      const reasoning = makeReasoning({
        thinking_steps: 't',
        tool_calls: [{ tool: 'bad-tool', params: {}, success: false, output: '', error: 'Permission denied' }],
      });
      render(<ThinkingSection reasoning={reasoning} defaultOpen={true} />);
      expect(screen.getByText(/bad-tool/)).toBeInTheDocument();
      expect(screen.getByText(/❌/)).toBeInTheDocument();
      expect(screen.getByText(/Permission denied/)).toBeInTheDocument();
    });
  });

  describe('模型信息', () => {
    it('展开后显示模型/provider/延迟/token', () => {
      const reasoning = makeReasoning({
        thinking_steps: 't',
        latency: 8.5,
        context_used: { memories_injected: 3, rag_chunks: 2, total_tokens: 5000 },
      });
      render(<ThinkingSection reasoning={reasoning} defaultOpen={true} />);
      // 模型名出现在摘要中和模型信息中
      const modelElements = screen.getAllByText(/glm-5\.1/);
      expect(modelElements.length).toBeGreaterThanOrEqual(2);
      expect(screen.getByText(/zhipu/)).toBeInTheDocument();
      const latencyElements = screen.getAllByText(/8\.5s/);
      expect(latencyElements.length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText(/5000 tokens/)).toBeInTheDocument();
    });
  });

  describe('决策摘要', () => {
    it('无思考步骤时显示决策摘要', () => {
      const reasoning = makeReasoning({
        thinking_steps: undefined,
        decision_summary: '已完成项目架构分析',
      });
      render(<ThinkingSection reasoning={reasoning} defaultOpen={true} />);
      expect(screen.getByText('处理决策')).toBeInTheDocument();
      expect(screen.getByText('已完成项目架构分析')).toBeInTheDocument();
    });

    it('有思考步骤时不显示决策摘要', () => {
      const reasoning = makeReasoning({
        thinking_steps: '详细思考...',
        decision_summary: '不应显示',
      });
      render(<ThinkingSection reasoning={reasoning} defaultOpen={true} />);
      expect(screen.queryByText('处理决策')).not.toBeInTheDocument();
    });
  });
});

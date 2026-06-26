/** NodeConfigPanel：节点配置面板

根据节点类型显示不同的配置选项
*/

import { useState, useEffect } from 'react';
import type { Node, NodeType } from '@xyflow/react';
import type {
  AgentNodeConfig,
  RouterNodeConfig,
  ConditionNodeConfig,
  HITLNodeConfig,
  ValidationNodeConfig,
  ParallelNodeConfig,
} from '../../../shared/types/workflow';

interface NodeConfigPanelProps {
  node: Node;
  onChange: (node: Node) => void;
}

export function NodeConfigPanel({ node, onChange }: NodeConfigPanelProps) {
  const [label, setLabel] = useState((node.data as { label: string }).label || '');
  const [config, setConfig] = useState<Record<string, unknown>>(
    (node.data as { config: Record<string, unknown> }).config || {}
  );

  const nodeType = (node.type || 'agent').charAt(0).toUpperCase() + (node.type || 'agent').slice(1) as NodeType;

  useEffect(() => {
    setLabel((node.data as { label: string }).label || '');
    setConfig((node.data as { config: Record<string, unknown> }).config || {});
  }, [node]);

  const handleSave = () => {
    onChange({
      ...node,
      data: {
        ...node.data,
        label,
        config,
      },
    });
  };

  const updateConfig = (key: string, value: unknown) => {
    const newConfig = { ...config, [key]: value };
    setConfig(newConfig);
    onChange({
      ...node,
      data: {
        ...node.data,
        label,
        config: newConfig,
      },
    });
  };

  return (
    <div
      style={{
        width: '320px',
        height: '100%',
        background: '#ffffff',
        borderLeft: '1px solid #e5e7eb',
        padding: '20px',
        overflow: 'auto',
      }}
    >
      <h3 style={{ margin: '0 0 20px', fontSize: '16px', fontWeight: '600' }}>
        节点配置
      </h3>

      {/* 基础配置 */}
      <div style={{ marginBottom: '20px' }}>
        <label style={{ display: 'block', fontSize: '13px', fontWeight: '500', marginBottom: '8px' }}>
          节点类型
        </label>
        <div
          style={{
            padding: '8px 12px',
            background: '#f3f4f6',
            borderRadius: '6px',
            fontSize: '14px',
            color: '#6b7280',
          }}
        >
          {nodeType}
        </div>
      </div>

      <div style={{ marginBottom: '20px' }}>
        <label style={{ display: 'block', fontSize: '13px', fontWeight: '500', marginBottom: '8px' }}>
          节点名称
        </label>
        <input
          type="text"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          onBlur={handleSave}
          placeholder="输入节点名称"
          style={{
            width: '100%',
            padding: '8px 12px',
            border: '1px solid #d1d5db',
            borderRadius: '6px',
            fontSize: '14px',
          }}
        />
      </div>

      {/* 根据节点类型显示不同配置 */}
      {nodeType === 'Agent' && <AgentConfigPanel config={config as AgentNodeConfig} onChange={updateConfig} />}
      {nodeType === 'Router' && <RouterConfigPanel config={config as RouterNodeConfig} onChange={updateConfig} />}
      {nodeType === 'Condition' && <ConditionConfigPanel config={config as ConditionNodeConfig} onChange={updateConfig} />}
      {nodeType === 'HITL' && <HITLConfigPanel config={config as HITLNodeConfig} onChange={updateConfig} />}
      {nodeType === 'Validation' && <ValidationConfigPanel config={config as ValidationNodeConfig} onChange={updateConfig} />}
      {nodeType === 'Parallel' && <ParallelConfigPanel config={config as ParallelNodeConfig} onChange={updateConfig} />}

      {/* Start/End 节点提示 */}
      {(nodeType === 'Start' || nodeType === 'End') && (
        <div
          style={{
            padding: '12px',
            background: '#f3f4f6',
            borderRadius: '6px',
            fontSize: '13px',
            color: '#6b7280',
          }}
        >
          {nodeType === 'Start' ? '开始节点无需额外配置' : '结束节点无需额外配置'}
        </div>
      )}
    </div>
  );
}

// Agent 节点配置
function AgentConfigPanel({ config, onChange }: { config: AgentNodeConfig; onChange: (key: string, value: unknown) => void }) {
  return (
    <>
      <div style={{ marginBottom: '16px' }}>
        <label style={{ display: 'block', fontSize: '13px', fontWeight: '500', marginBottom: '8px' }}>
          Agent ID
        </label>
        <input
          type="text"
          value={config.agent_id || ''}
          onChange={(e) => onChange('agent_id', e.target.value)}
          placeholder="选择或输入 Agent ID"
          style={{
            width: '100%',
            padding: '8px 12px',
            border: '1px solid #d1d5db',
            borderRadius: '6px',
            fontSize: '14px',
          }}
        />
      </div>

      <div style={{ marginBottom: '16px' }}>
        <label style={{ display: 'block', fontSize: '13px', fontWeight: '500', marginBottom: '8px' }}>
          Prompt 模板
        </label>
        <textarea
          value={config.prompt_template || ''}
          onChange={(e) => onChange('prompt_template', e.target.value)}
          placeholder="使用 {user_input} 作为占位符"
          rows={4}
          style={{
            width: '100%',
            padding: '8px 12px',
            border: '1px solid #d1d5db',
            borderRadius: '6px',
            fontSize: '14px',
            resize: 'vertical',
          }}
        />
      </div>

      <div style={{ marginBottom: '16px' }}>
        <label style={{ display: 'block', fontSize: '13px', fontWeight: '500', marginBottom: '8px' }}>
          模型
        </label>
        <select
          value={config.model_config?.model || 'claude-3-5-sonnet'}
          onChange={(e) => onChange('model_config', { ...config.model_config, model: e.target.value })}
          style={{
            width: '100%',
            padding: '8px 12px',
            border: '1px solid #d1d5db',
            borderRadius: '6px',
            fontSize: '14px',
          }}
        >
          <option value="claude-3-5-sonnet">Claude 3.5 Sonnet</option>
          <option value="claude-3-opus">Claude 3 Opus</option>
          <option value="gpt-4">GPT-4</option>
          <option value="gpt-3.5-turbo">GPT-3.5 Turbo</option>
        </select>
      </div>
    </>
  );
}

// Router 节点配置
function RouterConfigPanel({ config, onChange }: { config: RouterNodeConfig; onChange: (key: string, value: unknown) => void }) {
  return (
    <>
      <div style={{ marginBottom: '16px' }}>
        <label style={{ display: 'block', fontSize: '13px', fontWeight: '500', marginBottom: '8px' }}>
          路由策略
        </label>
        <select
          value={config.strategy || 'priority'}
          onChange={(e) => onChange('strategy', e.target.value)}
          style={{
            width: '100%',
            padding: '8px 12px',
            border: '1px solid #d1d5db',
            borderRadius: '6px',
            fontSize: '14px',
          }}
        >
          <option value="priority">优先级</option>
          <option value="round_robin">轮询</option>
          <option value="workload">负载均衡</option>
          <option value="semantic">语义匹配</option>
        </select>
      </div>

      <div style={{ marginBottom: '16px' }}>
        <label style={{ display: 'block', fontSize: '13px', fontWeight: '500', marginBottom: '8px' }}>
          候选 Agent/节点 ID
        </label>
        <textarea
          value={(config.candidates || []).join('\n')}
          onChange={(e) => onChange('candidates', e.target.value.split('\n').filter(Boolean))}
          placeholder="每行一个 ID"
          rows={4}
          style={{
            width: '100%',
            padding: '8px 12px',
            border: '1px solid #d1d5db',
            borderRadius: '6px',
            fontSize: '14px',
            resize: 'vertical',
          }}
        />
      </div>

      <div style={{ marginBottom: '16px' }}>
        <label style={{ display: 'block', fontSize: '13px', fontWeight: '500', marginBottom: '8px' }}>
          失败时回退到（可选）
        </label>
        <input
          type="text"
          value={config.fallback_agent_id || ''}
          onChange={(e) => onChange('fallback_agent_id', e.target.value)}
          placeholder="回退目标 ID"
          style={{
            width: '100%',
            padding: '8px 12px',
            border: '1px solid #d1d5db',
            borderRadius: '6px',
            fontSize: '14px',
          }}
        />
      </div>
    </>
  );
}

// Condition 节点配置
function ConditionConfigPanel({ config, onChange }: { config: ConditionNodeConfig; onChange: (key: string, value: unknown) => void }) {
  return (
    <>
      <div style={{ marginBottom: '16px' }}>
        <label style={{ display: 'block', fontSize: '13px', fontWeight: '500', marginBottom: '8px' }}>
          条件表达式
        </label>
        <input
          type="text"
          value={config.expression || ''}
          onChange={(e) => onChange('expression', e.target.value)}
          placeholder="例如：user_sentiment"
          style={{
            width: '100%',
            padding: '8px 12px',
            border: '1px solid #d1d5db',
            borderRadius: '6px',
            fontSize: '14px',
          }}
        />
        <div style={{ fontSize: '12px', color: '#6b7280', marginTop: '4px' }}>
          从状态中获取值的键名
        </div>
      </div>

      <div style={{ marginBottom: '16px' }}>
        <label style={{ display: 'block', fontSize: '13px', fontWeight: '500', marginBottom: '8px' }}>
          分支映射（JSON）
        </label>
        <textarea
          value={JSON.stringify(config.branches || {}, null, 2)}
          onChange={(e) => {
            try {
              const branches = JSON.parse(e.target.value);
              onChange('branches', branches);
            } catch {
              // 忽略解析错误
            }
          }}
          placeholder='{"positive": "node-1", "negative": "node-2"}'
          rows={6}
          style={{
            width: '100%',
            padding: '8px 12px',
            border: '1px solid #d1d5db',
            borderRadius: '6px',
            fontSize: '13px',
            fontFamily: 'monospace',
            resize: 'vertical',
          }}
        />
      </div>
    </>
  );
}

// HITL 节点配置
function HITLConfigPanel({ config, onChange }: { config: HITLNodeConfig; onChange: (key: string, value: unknown) => void }) {
  return (
    <>
      <div style={{ marginBottom: '16px' }}>
        <label style={{ display: 'block', fontSize: '13px', fontWeight: '500', marginBottom: '8px' }}>
          操作类型
        </label>
        <select
          value={config.action_type || 'approve'}
          onChange={(e) => onChange('action_type', e.target.value)}
          style={{
            width: '100%',
            padding: '8px 12px',
            border: '1px solid #d1d5db',
            borderRadius: '6px',
            fontSize: '14px',
          }}
        >
          <option value="approve">审批</option>
          <option value="input">输入</option>
          <option value="modify">修改</option>
        </select>
      </div>

      <div style={{ marginBottom: '16px' }}>
        <label style={{ display: 'block', fontSize: '13px', fontWeight: '500', marginBottom: '8px' }}>
          超时时间（秒）
        </label>
        <input
          type="number"
          value={config.timeout || 3600}
          onChange={(e) => onChange('timeout', parseInt(e.target.value) || 3600)}
          min={60}
          style={{
            width: '100%',
            padding: '8px 12px',
            border: '1px solid #d1d5db',
            borderRadius: '6px',
            fontSize: '14px',
          }}
        />
      </div>

      <div style={{ marginBottom: '16px' }}>
        <label style={{ display: 'block', fontSize: '13px', fontWeight: '500', marginBottom: '8px' }}>
          超时后升级到（可选）
        </label>
        <input
          type="text"
          value={config.escalation_target || ''}
          onChange={(e) => onChange('escalation_target', e.target.value)}
          placeholder="升级目标节点 ID"
          style={{
            width: '100%',
            padding: '8px 12px',
            border: '1px solid #d1d5db',
            borderRadius: '6px',
            fontSize: '14px',
          }}
        />
      </div>
    </>
  );
}

// Validation 节点配置
function ValidationConfigPanel({ config, onChange }: { config: ValidationNodeConfig; onChange: (key: string, value: unknown) => void }) {
  return (
    <>
      <div style={{ marginBottom: '16px' }}>
        <label style={{ display: 'block', fontSize: '13px', fontWeight: '500', marginBottom: '8px' }}>
          验证器类型
        </label>
        <select
          value={config.validator || 'LLM'}
          onChange={(e) => onChange('validator', e.target.value)}
          style={{
            width: '100%',
            padding: '8px 12px',
            border: '1px solid #d1d5db',
            borderRadius: '6px',
            fontSize: '14px',
          }}
        >
          <option value="LLM">LLM 验证</option>
          <option value="Rule">规则验证</option>
          <option value="Agent">Agent 验证</option>
        </select>
      </div>

      <div style={{ marginBottom: '16px' }}>
        <label style={{ display: 'block', fontSize: '13px', fontWeight: '500', marginBottom: '8px' }}>
          验证标准（每行一条）
        </label>
        <textarea
          value={(config.criteria || []).join('\n')}
          onChange={(e) => onChange('criteria', e.target.value.split('\n').filter(Boolean))}
          placeholder="例如：&#10;内容完整性&#10;格式正确&#10;无敏感信息"
          rows={4}
          style={{
            width: '100%',
            padding: '8px 12px',
            border: '1px solid #d1d5db',
            borderRadius: '6px',
            fontSize: '14px',
            resize: 'vertical',
          }}
        />
      </div>

      <div style={{ marginBottom: '16px' }}>
        <label style={{ display: 'block', fontSize: '13px', fontWeight: '500', marginBottom: '8px' }}>
          验证失败时
        </label>
        <select
          value={config.on_fail || 'reject'}
          onChange={(e) => onChange('on_fail', e.target.value)}
          style={{
            width: '100%',
            padding: '8px 12px',
            border: '1px solid #d1d5db',
            borderRadius: '6px',
            fontSize: '14px',
          }}
        >
          <option value="reject">拒绝</option>
          <option value="retry">重试</option>
          <option value="escalate">升级</option>
        </select>
      </div>
    </>
  );
}

// Parallel 节点配置
function ParallelConfigPanel({ config, onChange }: { config: ParallelNodeConfig; onChange: (key: string, value: unknown) => void }) {
  return (
    <>
      <div style={{ marginBottom: '16px' }}>
        <label style={{ display: 'block', fontSize: '13px', fontWeight: '500', marginBottom: '8px' }}>
          合并策略
        </label>
        <select
          value={config.merge_strategy || 'all'}
          onChange={(e) => onChange('merge_strategy', e.target.value)}
          style={{
            width: '100%',
            padding: '8px 12px',
            border: '1px solid #d1d5db',
            borderRadius: '6px',
            fontSize: '14px',
          }}
        >
          <option value="all">全部完成</option>
          <option value="first">首个完成</option>
          <option value="majority">多数完成</option>
        </select>
      </div>

      <div style={{ marginBottom: '16px' }}>
        <label style={{ display: 'block', fontSize: '13px', fontWeight: '500', marginBottom: '8px' }}>
          超时时间（秒，可选）
        </label>
        <input
          type="number"
          value={config.timeout || ''}
          onChange={(e) => onChange('timeout', e.target.value ? parseInt(e.target.value) : undefined)}
          min={10}
          placeholder="留空则不限制"
          style={{
            width: '100%',
            padding: '8px 12px',
            border: '1px solid #d1d5db',
            borderRadius: '6px',
            fontSize: '14px',
          }}
        />
      </div>

      <div style={{ padding: '12px', background: '#fef3c7', borderRadius: '6px', fontSize: '13px', color: '#92400e' }}>
        ⚠️ 并行分支需要在画布中通过边连接来定义。每个分支的第一个节点即为该分支的起点。
      </div>
    </>
  );
}

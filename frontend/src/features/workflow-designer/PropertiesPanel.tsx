/** PropertiesPanel：边属性配置面板

配置边的类型和条件
*/

import { useState, useEffect } from 'react';
import type { Edge } from '@xyflow/react';
import type { EdgeType } from '../../../shared/types/workflow';

interface PropertiesPanelProps {
  edge: Edge;
  onChange?: (edge: Edge) => void;
}

export function PropertiesPanel({ edge, onChange }: PropertiesPanelProps) {
  const [edgeType, setEdgeType] = useState<EdgeType>(
    (edge.type?.charAt(0).toUpperCase() + edge.type?.slice(1)) as EdgeType || 'Forward'
  );
  const [condition, setCondition] = useState<Record<string, unknown>>(
    (edge.data as { condition?: Record<string, unknown> })?.condition || {}
  );

  useEffect(() => {
    setEdgeType((edge.type?.charAt(0).toUpperCase() + edge.type?.slice(1)) as EdgeType || 'Forward');
    setCondition((edge.data as { condition?: Record<string, unknown> })?.condition || {});
  }, [edge]);

  const handleTypeChange = (newType: EdgeType) => {
    setEdgeType(newType);
    if (onChange) {
      onChange({
        ...edge,
        type: newType.toLowerCase(),
        data: { ...edge.data, condition },
      });
    }
  };

  const handleConditionChange = (key: string, value: unknown) => {
    const newCondition = { ...condition, [key]: value };
    setCondition(newCondition);
    if (onChange) {
      onChange({
        ...edge,
        type: edgeType.toLowerCase(),
        data: { ...edge.data, condition: newCondition },
      });
    }
  };

  const edgeTypeDescriptions: Record<EdgeType, { description: string; color: string }> = {
    Forward: { description: '正常流转到下一个节点', color: '#94a3b8' },
    Reject: { description: '拒绝/驳回流程', color: '#ef4444' },
    Escalate: { description: '升级到上级节点', color: '#f59e0b' },
    Timeout: { description: '超时后的流转', color: '#8b5cf6' },
    Fallback: { description: '失败时的回退', color: '#6b7280' },
  };

  return (
    <div
      style={{
        width: '280px',
        height: '100%',
        background: '#ffffff',
        borderLeft: '1px solid #e5e7eb',
        padding: '20px',
        overflow: 'auto',
      }}
    >
      <h3 style={{ margin: '0 0 20px', fontSize: '16px', fontWeight: '600' }}>
        边属性
      </h3>

      {/* 边类型选择 */}
      <div style={{ marginBottom: '20px' }}>
        <label style={{ display: 'block', fontSize: '13px', fontWeight: '500', marginBottom: '8px' }}>
          边类型
        </label>
        {Object.entries(edgeTypeDescriptions).map(([type, info]) => (
          <button
            key={type}
            onClick={() => handleTypeChange(type as EdgeType)}
            style={{
              width: '100%',
              padding: '10px 12px',
              marginBottom: '8px',
              background: edgeType === type ? info.color + '20' : '#f9fafb',
              border: `2px solid ${edgeType === type ? info.color : '#e5e7eb'}`,
              borderRadius: '6px',
              cursor: 'pointer',
              fontSize: '14px',
              color: '#374151',
              textAlign: 'left',
              transition: 'all 0.2s',
            }}
            onMouseEnter={(e) => {
              if (edgeType !== type) {
                e.currentTarget.style.background = '#f3f4f6';
              }
            }}
            onMouseLeave={(e) => {
              if (edgeType !== type) {
                e.currentTarget.style.background = '#f9fafb';
              }
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ fontWeight: edgeType === type ? '600' : '400' }}>{type}</span>
              <div
                style={{
                  width: '12px',
                  height: '12px',
                  borderRadius: '50%',
                  background: info.color,
                }}
              />
            </div>
            <div style={{ fontSize: '12px', color: '#6b7280', marginTop: '4px' }}>
              {info.description}
            </div>
          </button>
        ))}
      </div>

      {/* 条件配置 */}
      <div style={{ marginBottom: '20px' }}>
        <label style={{ display: 'block', fontSize: '13px', fontWeight: '500', marginBottom: '8px' }}>
          条件配置（可选）
        </label>
        <textarea
          value={JSON.stringify(condition, null, 2)}
          onChange={(e) => {
            try {
              const newCondition = JSON.parse(e.target.value);
              setCondition(newCondition);
              if (onChange) {
                onChange({
                  ...edge,
                  type: edgeType.toLowerCase(),
                  data: { ...edge.data, condition: newCondition },
                });
              }
            } catch {
              // 忽略解析错误，保持本地状态
            }
          }}
          placeholder='{"key": "value"}'
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
        <div style={{ fontSize: '12px', color: '#6b7280', marginTop: '4px' }}>
          JSON 格式的条件表达式
        </div>
      </div>

      {/* 边信息 */}
      <div style={{ padding: '12px', background: '#f3f4f6', borderRadius: '6px' }}>
        <div style={{ fontSize: '13px', color: '#6b7280', marginBottom: '4px' }}>
          源节点：{edge.source}
        </div>
        <div style={{ fontSize: '13px', color: '#6b7280' }}>
          目标节点：{edge.target}
        </div>
      </div>
    </div>
  );
}

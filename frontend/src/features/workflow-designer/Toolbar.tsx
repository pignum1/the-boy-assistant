/** Toolbar：工作流编辑器工具栏

提供保存、验证、新建、返回等操作
*/

import { useState } from 'react';

interface ToolbarProps {
  workflowName?: string;
  isDirty: boolean;
  onSave: () => void;
  onValidate: () => void;
  onNew: () => void;
  onBack: () => void;
}

export function Toolbar({
  workflowName = '未命名工作流',
  isDirty,
  onSave,
  onValidate,
  onNew,
  onBack,
}: ToolbarProps) {
  const [validating, setValidating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [validationResult, setValidationResult] = useState<{
    valid: boolean;
    errors: string[];
    warnings: string[];
  } | null>(null);

  const handleValidate = async () => {
    setValidating(true);
    setValidationResult(null);
    try {
      onValidate();
      // 这里应该从 onValidate 获取结果，简化处理
    } finally {
      setValidating(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await onSave();
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '12px 24px',
        background: '#ffffff',
        borderBottom: '1px solid #e5e7eb',
        boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
      }}
    >
      {/* 左侧：工作流名称 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <button
          onClick={onBack}
          style={{
            padding: '8px 16px',
            background: '#f3f4f6',
            border: '1px solid #d1d5db',
            borderRadius: '6px',
            cursor: 'pointer',
            fontSize: '14px',
            color: '#374151',
          }}
          onMouseEnter={(e) => (e.currentTarget.style.background = '#e5e7eb')}
          onMouseLeave={(e) => (e.currentTarget.style.background = '#f3f4f6')}
        >
          ← 返回
        </button>

        <h1 style={{ margin: 0, fontSize: '18px', fontWeight: '600', color: '#111827' }}>
          {workflowName}
        </h1>

        {isDirty && (
          <span
            style={{
              padding: '2px 8px',
              background: '#fef3c7',
              color: '#92400e',
              fontSize: '12px',
              borderRadius: '4px',
              fontWeight: '500',
            }}
          >
            未保存
          </span>
        )}
      </div>

      {/* 中间：节点类型快捷添加 */}
      <div style={{ display: 'flex', gap: '8px' }}>
        <span style={{ fontSize: '12px', color: '#6b7280', lineHeight: '32px' }}>
          添加节点：
        </span>
        {['Agent', 'Router', 'Condition', 'HITL', 'Validation'].map((type) => (
          <button
            key={type}
            onClick={() => {
              // 触发添加节点事件
              window.dispatchEvent(
                new CustomEvent('workflow-add-node', { detail: { type } })
              );
            }}
            style={{
              padding: '6px 12px',
              background: '#ffffff',
              border: '1px solid #d1d5db',
              borderRadius: '6px',
              cursor: 'pointer',
              fontSize: '13px',
              color: '#374151',
            }}
            onMouseEnter={(e) => (e.currentTarget.style.borderColor = '#9ca3af')}
            onMouseLeave={(e) => (e.currentTarget.style.borderColor = '#d1d5db')}
          >
            {type}
          </button>
        ))}
      </div>

      {/* 右侧：操作按钮 */}
      <div style={{ display: 'flex', gap: '12px' }}>
        <button
          onClick={handleValidate}
          disabled={validating}
          style={{
            padding: '8px 16px',
            background: '#ffffff',
            border: '1px solid #d1d5db',
            borderRadius: '6px',
            cursor: validating ? 'not-allowed' : 'pointer',
            fontSize: '14px',
            color: validating ? '#9ca3af' : '#374151',
          }}
        >
          {validating ? '验证中...' : '验证'}
        </button>

        <button
          onClick={onNew}
          style={{
            padding: '8px 16px',
            background: '#ffffff',
            border: '1px solid #d1d5db',
            borderRadius: '6px',
            cursor: 'pointer',
            fontSize: '14px',
            color: '#374151',
          }}
        >
          新建
        </button>

        <button
          onClick={handleSave}
          disabled={saving || !isDirty}
          style={{
            padding: '8px 20px',
            background: saving || !isDirty ? '#9ca3af' : '#3b82f6',
            border: 'none',
            borderRadius: '6px',
            cursor: saving || !isDirty ? 'not-allowed' : 'pointer',
            fontSize: '14px',
            color: '#ffffff',
            fontWeight: '500',
          }}
        >
          {saving ? '保存中...' : '保存'}
        </button>
      </div>

      {/* 验证结果提示 */}
      {validationResult && !validationResult.valid && (
        <div
          style={{
            position: 'fixed',
            top: '80px',
            right: '24px',
            padding: '12px 16px',
            background: '#fef2f2',
            border: '1px solid #fecaca',
            borderRadius: '8px',
            boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
            zIndex: 1000,
          }}
        >
          <div style={{ fontWeight: '600', color: '#991b1b', marginBottom: '8px' }}>
            验证失败
          </div>
          {validationResult.errors.map((error, i) => (
            <div key={i} style={{ fontSize: '13px', color: '#b91c1c' }}>
              • {error}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

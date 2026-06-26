/** Workflow选择器组件 - 用于Team创建时选择或创建Workflow */
import { useState, useEffect } from 'react';
import { api } from '../../shared/api/client';

interface WorkflowSummary {
  id: string;
  name: string;
  description?: string;
  node_count?: number;
}

interface WorkflowSelectorProps {
  teamId?: string;
  selectedWorkflowId?: string;
  onWorkflowSelect: (workflowId: string | undefined) => void;
  onWorkflowCreate: () => void;
  disabled?: boolean;
}

export function WorkflowSelector({
  teamId,
  selectedWorkflowId,
  onWorkflowSelect,
  onWorkflowCreate,
  disabled = false,
}: WorkflowSelectorProps) {
  const [workflows, setWorkflows] = useState<WorkflowSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    const url = teamId ? `/api/v1/workflows?team_id=${teamId}` : '/api/v1/workflows';
    api.get<{ workflows: WorkflowSummary[] }>(url)
      .then((res) => setWorkflows(res.workflows || []))
      .catch(() => setWorkflows([]))
      .finally(() => setLoading(false));
  }, [teamId]);

  return (
    <div>
      <label style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 6, display: 'block', fontWeight: 500 }}>
        配置 Workflow
      </label>

      {/* 已有工作流选择 */}
      {!loading && workflows.length > 0 && (
        <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
          <select
            value={selectedWorkflowId || ''}
            onChange={(e) => onWorkflowSelect(e.target.value || undefined)}
            disabled={disabled}
            style={selectStyle}
          >
            <option value="">— 选择已有 Workflow —</option>
            {workflows.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name} {w.node_count ? `(${w.node_count} 节点)` : ''}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* 新建工作流按钮 */}
      <div style={{ display: 'flex', gap: 8 }}>
        <button
          type="button"
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            console.log('[WorkflowSelector] Create button clicked');
            onWorkflowCreate();
          }}
          disabled={disabled}
          style={createBtnStyle}
          title="打开SOP设计器创建新Workflow"
        >
          + 新建 Workflow
        </button>
      </div>

      {/* 提示信息 */}
      {!loading && workflows.length === 0 && (
        <div style={{ fontSize: 10, color: 'var(--text-dim)', marginTop: 4 }}>
          暂无工作流，请先创建
        </div>
      )}

      {selectedWorkflowId && (
        <div style={{ fontSize: 10, color: 'var(--green-400)', marginTop: 4 }}>
          ✓ 已选择: {workflows.find((w) => w.id === selectedWorkflowId)?.name || '未知Workflow'}
        </div>
      )}
    </div>
  );
}

const selectStyle: React.CSSProperties = {
  flex: 1,
  padding: '8px 10px',
  background: 'var(--bg-elevated)',
  border: '1px solid var(--border-medium)',
  borderRadius: 6,
  color: 'var(--text-primary)',
  fontSize: 12,
  fontFamily: 'var(--font-body)',
  outline: 'none',
  cursor: 'pointer',
};

const createBtnStyle: React.CSSProperties = {
  padding: '10px 16px',
  background: 'linear-gradient(135deg, var(--gold-500), #d97706)',
  border: 'none',
  borderRadius: 6,
  color: '#0a0f1e',
  fontSize: 12,
  fontWeight: 600,
  cursor: 'pointer',
  transition: 'all 0.15s',
  whiteSpace: 'nowrap',
  minWidth: 140,
  ':hover': {
    opacity: 0.9,
  },
  ':disabled': {
    opacity: 0.5,
    cursor: 'not-allowed',
  },
};

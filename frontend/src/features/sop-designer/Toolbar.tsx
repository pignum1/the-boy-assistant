import { useCallback, useRef, useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import yaml from 'js-yaml';
import type { SOPDefinition, WorkflowMode } from '../../shared/types/sop';
import { validateSop } from '../../shared/utils/validators';
import { sopsApi } from '../../shared/api/sops';

interface ToolbarProps {
  name: string;
  onNameChange: (name: string) => void;
  getSop: () => SOPDefinition;
  loadSop: (sop: SOPDefinition) => void;
  onAutoLayout: () => void;
  onClear: () => void;
  onDeleteSelected?: () => void;
  syncToYaml: () => void;
  onSaved?: (workflowId: string) => void;
  workflowMode?: WorkflowMode;
  onModeChange?: (mode: WorkflowMode) => void;
  availableAgents?: Array<{ id: string; name: string }>;
  sopId?: string;
}

const btnBase: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 5,
  padding: '6px 12px',
  borderRadius: 6,
  fontSize: 12,
  fontWeight: 500,
  cursor: 'pointer',
  border: '1px solid transparent',
  transition: 'all 0.15s',
  fontFamily: 'var(--font-body)',
};

export function Toolbar({
  name,
  onNameChange,
  getSop,
  loadSop,
  onAutoLayout,
  onClear,
  onDeleteSelected,
  syncToYaml,
  onSaved,
  workflowMode = 'template',
  onModeChange,
  availableAgents = [],
  sopId,
}: ToolbarProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const isFromTeamCreate = searchParams.get('from_team_create') === 'true';

  const handleSave = useCallback(async () => {
    const sop = getSop();
    const errors = validateSop(sop.nodes, sop.edges);
    const criticalErrors = errors.filter((e) => e.level === 'error');
    if (criticalErrors.length > 0) {
      alert('Validation errors:\n' + criticalErrors.map((e) => e.message).join('\n'));
      return;
    }
    try {
      let result;
      if (sopId) {
        // Update existing SOP
        result = await sopsApi.update(sopId, sop);
      } else {
        // Create new SOP
        result = await sopsApi.create(sop);
      }
      const workflowId = result.id || result.workflow_id || result.sop_id;

      // 如果来自Team创建流程，返回并传递Workflow ID
      if (isFromTeamCreate && workflowId) {
        sessionStorage.setItem('team_create_new_workflow_id', workflowId);
        sessionStorage.removeItem('team_create_wizard_state'); // 清理状态
        navigate('/teams?create_from_sop=true');
        return;
      }

      alert('SOP saved successfully!');
      onSaved?.(workflowId);
    } catch (err) {
      alert('Save failed: ' + String(err));
    }
  }, [getSop, isFromTeamCreate, navigate, onSaved, sopId]);

  const handleLoad = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleFileChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = (ev) => {
        const text = ev.target?.result as string;
        try {
          const parsed = yaml.load(text) as Record<string, unknown>;
          const sop: SOPDefinition = {
            name: (parsed.name as string) || 'Untitled',
            description: (parsed.description as string) || '',
            version: (parsed.version as string) || '1.0',
            nodes: (parsed.nodes as SOPDefinition['nodes']) || [],
            edges: (parsed.edges as SOPDefinition['edges']) || [],
          };
          loadSop(sop);
          syncToYaml();
        } catch (err) {
          alert('Invalid YAML: ' + String(err));
        }
      };
      reader.readAsText(file);
      e.target.value = '';
    },
    [loadSop, syncToYaml]
  );

  const handleValidate = useCallback(() => {
    const sop = getSop();
    const errors = validateSop(sop.nodes, sop.edges);
    if (errors.length === 0) {
      alert('No validation errors!');
    } else {
      alert(errors.map((e) => `[${e.level}] ${e.message}`).join('\n'));
    }
  }, [getSop]);

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '10px 20px',
        borderBottom: '1px solid var(--border-subtle)',
        background: 'var(--bg-base)',
      }}
    >
      <input
        style={{
          background: 'var(--bg-elevated)',
          border: '1px solid var(--border-subtle)',
          borderRadius: 6,
          padding: '6px 12px',
          fontSize: 13,
          fontWeight: 600,
          color: 'var(--text-primary)',
          width: 200,
          fontFamily: 'var(--font-body)',
          outline: 'none',
        }}
        value={name}
        onChange={(e) => onNameChange(e.target.value)}
        placeholder="SOP Name"
      />

      {/* 模式切换 */}
      {onModeChange && (
        <>
          <div style={{ width: 1, height: 20, background: 'var(--border-subtle)', margin: '0 4px' }} />
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ fontSize: 11, color: 'var(--text-muted)', marginRight: 4 }}>模式:</span>
            <button
              onClick={() => onModeChange('template')}
              style={{
                ...btnBase,
                padding: '4px 8px',
                fontSize: 11,
                background: workflowMode === 'template' ? 'var(--purple-bg)' : 'var(--bg-card)',
                borderColor: workflowMode === 'template' ? 'var(--purple-border)' : 'var(--border-subtle)',
                color: workflowMode === 'template' ? 'var(--purple-400)' : 'var(--text-secondary)',
                borderRadius: 4,
              }}
              title="模板模式：使用角色类型，可跨团队复用"
            >
              📋 模板
            </button>
            <button
              onClick={() => onModeChange('team_specific')}
              style={{
                ...btnBase,
                padding: '4px 8px',
                fontSize: 11,
                background: workflowMode === 'team_specific' ? 'var(--gold-bg)' : 'var(--bg-card)',
                borderColor: workflowMode === 'team_specific' ? 'var(--gold-border)' : 'var(--border-subtle)',
                color: workflowMode === 'team_specific' ? 'var(--gold-400)' : 'var(--text-secondary)',
                borderRadius: 4,
              }}
              title="团队专属：直接选择 Agent，仅本团队使用"
            >
              👥 团队专属
            </button>
          </div>
        </>
      )}

      <div style={{ width: 1, height: 20, background: 'var(--border-subtle)', margin: '0 4px' }} />

      <button onClick={handleSave} style={{ ...btnBase, background: 'linear-gradient(135deg, var(--gold-500), #d97706)', color: '#0a0f1e', border: 'none' }}>
        💾 保存
      </button>
      <button onClick={handleLoad} style={{ ...btnBase, background: 'var(--bg-card)', color: 'var(--text-secondary)', border: '1px solid var(--border-medium)' }}>
        📂 加载
      </button>
      <button onClick={onAutoLayout} style={{ ...btnBase, background: 'var(--bg-card)', color: 'var(--text-secondary)', border: '1px solid var(--border-medium)' }}>
        📐 布局
      </button>
      <button onClick={handleValidate} style={{ ...btnBase, background: 'var(--bg-card)', color: 'var(--text-secondary)', border: '1px solid var(--border-medium)' }}>
        ✅ 校验
      </button>
      {onDeleteSelected && (
        <button onClick={onDeleteSelected} style={{ ...btnBase, background: 'var(--bg-card)', color: 'var(--text-secondary)', border: '1px solid var(--border-medium)' }} title="删除选中的节点和连线 (Delete/Backspace)">
          ✂️ 删除
        </button>
      )}
      <button onClick={onClear} style={{ ...btnBase, background: 'var(--bg-card)', color: 'var(--red-400)', border: '1px solid var(--border-medium)' }}>
        🗑 清空
      </button>

      <input ref={fileInputRef} type="file" accept=".yaml,.yml" className="hidden" onChange={handleFileChange} style={{ display: 'none' }} />
    </div>
  );
}

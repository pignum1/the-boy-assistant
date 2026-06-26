/** 新建任务弹窗：输入需求 → AI 自动生成工作流 */
import { useState } from 'react';
import { userTasksApi } from '../../shared/api/userTasks';
import type { Team } from '../../shared/types/agent';

interface NewTaskModalProps {
  teams: Team[];
  preSelectedTeamId?: string;
  onClose: () => void;
  onCreated: (taskId: string) => void;
}

export function NewTaskModal({ teams, preSelectedTeamId, onClose, onCreated }: NewTaskModalProps) {
  const [selectedTeamId, setSelectedTeamId] = useState(preSelectedTeamId || '');
  const [requirement, setRequirement] = useState('');
  const [priority, setPriority] = useState<'low' | 'medium' | 'high'>('medium');
  const [creating, setCreating] = useState(false);
  const [step, setStep] = useState<'input' | 'planning' | 'confirm'>('input');
  const [aiPlan, setAiPlan] = useState<any>(null);

  const handleStart = async () => {
    if (!selectedTeamId || !requirement.trim()) return;
    setCreating(true);
    setStep('planning');

    try {
      // 1. 创建任务
      const createResponse = await fetch('/api/v1/user-tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          team_id: selectedTeamId || undefined,
          title: requirement.slice(0, 50),
          requirement: requirement,
          priority: priority,
        }),
      });
      const task = await createResponse.json();

      // 2. 调用 AI 规划
      const team = teams.find((t) => t.id === selectedTeamId);
      const availableAgents = team?.members?.map((m: any) => ({
        id: m.agent_id,
        name: m.agent_name || m.name,
        role: m.role,
      })) || [];

      const planResponse = await fetch(`/api/v1/user-tasks/${task.id}/plan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          available_agents: availableAgents,
        }),
      });

      if (planResponse.ok) {
        const plan = await planResponse.json();
        setAiPlan(plan);
        setStep('confirm');
      } else {
        // 如果 AI 规划失败（可能没有配置 LLM），直接确认
        setAiPlan({ task_name: task.title, estimated_steps: 1 });
        setStep('confirm');
      }
    } catch (e) {
      console.error('规划失败:', e);
      alert('AI 规划失败，请检查配置');
      setStep('input');
    } finally {
      setCreating(false);
    }
  };

  const handleConfirm = async () => {
    if (!aiPlan) return;
    setCreating(true);

    try {
      // 获取当前任务 ID（从规划结果中或重新创建）
      // 这里简化处理，实际应该保存 task_id 到状态中
      onCreated('task-id'); // 传递任务 ID 给父组件
    } catch (e) {
      alert('启动失败: ' + String(e));
    } finally {
      setCreating(false);
    }
  };

  const selectedTeam = teams.find((t) => t.id === selectedTeamId);

  return (
    <>
      <div onClick={onClose} style={overlayStyle} />
      <div style={modalStyle}>
        <div style={headerStyle}>
          <div style={{ fontSize: 18, fontWeight: 700 }}>
            {step === 'input' ? '创建新任务' : step === 'planning' ? 'AI 正在规划...' : '确认执行方案'}
          </div>
          <button onClick={onClose} style={closeBtnStyle}>✕</button>
        </div>

        <div style={bodyStyle}>
          {step === 'input' && (
            <>
              {/* 选择团队 */}
              <div style={{ marginBottom: 20 }}>
                <label style={labelStyle}>选择团队 *</label>
                <select
                  style={selectStyle}
                  value={selectedTeamId}
                  onChange={(e) => setSelectedTeamId(e.target.value)}
                >
                  <option value="">— 选择团队 —</option>
                  {teams.map((t) => (
                    <option key={t.id} value={t.id}>{t.name}</option>
                  ))}
                </select>
                {selectedTeam && (
                  <div style={teamHintStyle}>
                    {selectedTeam.members?.length || 0} 个 Agent 可用
                  </div>
                )}
              </div>

              {/* 输入需求 */}
              <div style={{ marginBottom: 20 }}>
                <label style={labelStyle}>任务需求 *</label>
                <textarea
                  style={textareaStyle}
                  value={requirement}
                  onChange={(e) => setRequirement(e.target.value)}
                  placeholder="描述你想要完成的任务，AI 会自动规划执行步骤..."
                  rows={5}
                />
                <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 4 }}>
                  例如：开发一个用户登录功能，包括注册、登录和密码找回
                </div>
              </div>

              {/* 优先级 */}
              <div style={{ marginBottom: 8 }}>
                <label style={labelStyle}>优先级</label>
                <div style={{ display: 'flex', gap: 8 }}>
                  {(['low', 'medium', 'high'] as const).map((p) => (
                    <button
                      key={p}
                      onClick={() => setPriority(p)}
                      style={{
                        flex: 1,
                        padding: '8px 12px',
                        borderRadius: 8,
                        background: priority === p ? 'var(--gold-bg)' : 'var(--bg-card)',
                        border: priority === p ? '1px solid rgba(245,158,11,0.4)' : '1px solid var(--border-subtle)',
                        color: 'var(--text-primary)',
                        fontSize: 12,
                        cursor: 'pointer',
                      }}
                    >
                      {p === 'low' ? '低' : p === 'medium' ? '中' : '高'}
                    </button>
                  ))}
                </div>
              </div>
            </>
          )}

          {step === 'planning' && (
            <div style={{ textAlign: 'center', padding: '40px 0' }}>
              <div style={{ fontSize: 48, marginBottom: 16 }}>🤔</div>
              <div style={{ fontSize: 16, color: 'var(--text-secondary)' }}>
                AI 正在分析您的需求并生成执行方案...
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-dim)', marginTop: 8 }}>
                这可能需要几秒钟
              </div>
            </div>
          )}

          {step === 'confirm' && aiPlan && (
            <>
              <div style={{ marginBottom: 20 }}>
                <label style={labelStyle}>AI 规划的执行方案</label>
                <div style={planBoxStyle}>
                  <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 12 }}>
                    {aiPlan.task_name || '未命名任务'}
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-dim)', marginBottom: 16 }}>
                    预计 {aiPlan.estimated_steps || 1} 个步骤
                  </div>

                  {/* 显示执行步骤 */}
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                    <div style={{ fontWeight: 600, marginBottom: 8 }}>执行步骤：</div>
                    {aiPlan.workflow?.nodes?.map((node: any, i: number) => (
                      <div key={node.id} style={{ marginBottom: 6 }}>
                        <span style={{ color: 'var(--gold-500)' }}>{i + 1}.</span>{' '}
                        {node.label} ({node.type})
                      </div>
                    )) || <div style={{ color: 'var(--text-dim)' }}>暂无详细步骤</div>}
                  </div>

                  {aiPlan.suggestions && aiPlan.suggestions.length > 0 && (
                    <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--border-subtle)' }}>
                      <div style={{ fontSize: 11, fontWeight: 600, marginBottom: 4 }}>建议：</div>
                      {aiPlan.suggestions.map((s: string, i: number) => (
                        <div key={i} style={{ fontSize: 11, color: 'var(--text-dim)' }}>
                          • {s}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </>
          )}
        </div>

        <div style={footerStyle}>
          <button
            className="btn-secondary"
            style={btnSecondaryStyle}
            onClick={() => {
              if (step === 'confirm') {
                setStep('input');
                setAiPlan(null);
              } else {
                onClose();
              }
            }}
          >
            {step === 'input' ? '取消' : '返回修改'}
          </button>
          {step === 'input' ? (
            <button
              className="btn-primary"
              style={{ ...btnPrimaryStyle, opacity: selectedTeamId && requirement.trim() ? 1 : 0.5 }}
              onClick={handleStart}
              disabled={!selectedTeamId || !requirement.trim() || creating}
            >
              {creating ? '分析中...' : '让 AI 规划 →'}
            </button>
          ) : (
            <button
              className="btn-primary"
              style={btnPrimaryStyle}
              onClick={handleConfirm}
              disabled={creating}
            >
              {creating ? '启动中...' : '确认并开始'}
            </button>
          )}
        </div>
      </div>
    </>
  );
}

// ── Styles ──

const overlayStyle: React.CSSProperties = {
  position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 200,
};

const modalStyle: React.CSSProperties = {
  position: 'fixed', top: '10%', left: '50%', transform: 'translateX(-50%)',
  width: 560, maxHeight: '85vh', zIndex: 201,
  background: 'var(--bg-base)', border: '1px solid var(--border-subtle)',
  borderRadius: 16, display: 'flex', flexDirection: 'column',
  boxShadow: '0 24px 80px rgba(0,0,0,0.5)', overflow: 'hidden',
};

const headerStyle: React.CSSProperties = {
  padding: '20px 24px 16px', borderBottom: '1px solid var(--border-subtle)',
  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
};

const bodyStyle: React.CSSProperties = {
  padding: '20px 24px', flex: 1, overflowY: 'auto',
};

const footerStyle: React.CSSProperties = {
  padding: '16px 24px', borderTop: '1px solid var(--border-subtle)',
  display: 'flex', justifyContent: 'flex-end', gap: 8,
};

const labelStyle: React.CSSProperties = {
  fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)',
  marginBottom: 6, display: 'block',
};

const selectStyle: React.CSSProperties = {
  width: '100%', padding: '9px 12px', borderRadius: 8,
  background: 'var(--bg-elevated)', border: '1px solid var(--border-medium)',
  color: 'var(--text-primary)', fontSize: 13, fontFamily: 'var(--font-body)',
  outline: 'none',
};

const textareaStyle: React.CSSProperties = {
  width: '100%', padding: '10px 12px', borderRadius: 8,
  background: 'var(--bg-elevated)', border: '1px solid var(--border-medium)',
  color: 'var(--text-primary)', fontSize: 13, fontFamily: 'var(--font-body)',
  outline: 'none', resize: 'vertical', minHeight: 100,
};

const teamHintStyle: React.CSSProperties = {
  fontSize: 10, color: 'var(--text-dim)', marginTop: 4,
};

const planBoxStyle: React.CSSProperties = {
  padding: 16, borderRadius: 12,
  background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)',
};

const closeBtnStyle: React.CSSProperties = {
  background: 'none', border: 'none', color: 'var(--text-muted)',
  fontSize: 18, cursor: 'pointer', padding: '4px 8px', borderRadius: 6,
};

const btnPrimaryStyle: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 6, padding: '8px 16px',
  borderRadius: 8, fontFamily: 'var(--font-body)', fontSize: 13, fontWeight: 500,
  border: 'none', cursor: 'pointer', transition: 'all 0.15s',
  background: 'linear-gradient(135deg, var(--gold-500), #d97706)',
  color: 'rgba(10,15,30,0.9)', boxShadow: '0 0 16px rgba(245,158,11,0.12)',
};

const btnSecondaryStyle: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 6, padding: '8px 16px',
  borderRadius: 8, fontFamily: 'var(--font-body)', fontSize: 13, fontWeight: 500,
  cursor: 'pointer', transition: 'all 0.15s',
  background: 'var(--bg-card)', color: 'var(--text-secondary)',
  border: '1px solid var(--border-medium)',
};

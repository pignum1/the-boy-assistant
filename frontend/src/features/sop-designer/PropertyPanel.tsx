import type { Node as ReactFlowNode, Edge } from '@xyflow/react';
import type { EdgeType, WorkflowMode } from '../../shared/types/sop';

interface PropertyPanelProps {
  node: ReactFlowNode | null;
  edge: Edge | null;
  onUpdateNode: (nodeId: string, data: Record<string, unknown>) => void;
  onUpdateEdge: (edgeId: string, data: Record<string, unknown>) => void;
  workflowMode?: WorkflowMode;
  availableAgents?: Array<{ id: string; name: string }>;
}

const inputStyle: React.CSSProperties = {
  width: '100%',
  background: 'var(--bg-elevated)',
  border: '1px solid var(--border-subtle)',
  borderRadius: 6,
  padding: '6px 10px',
  fontSize: 12,
  color: 'var(--text-primary)',
  fontFamily: 'var(--font-body)',
  outline: 'none',
};

const labelStyle: React.CSSProperties = {
  display: 'block',
  fontSize: 11,
  color: 'var(--text-muted)',
  marginBottom: 4,
  fontWeight: 500,
};

export function PropertyPanel({
  node,
  edge,
  onUpdateNode,
  onUpdateEdge,
  workflowMode = 'template',
  availableAgents = [],
}: PropertyPanelProps) {
  // ── 空状态 ──
  if (!node && !edge) {
    return (
      <div style={panelBaseStyle}>
        <div style={{ fontSize: 28, opacity: 0.3 }}>🎯</div>
        选择节点或连线以编辑属性
      </div>
    );
  }

  // ── 边属性编辑 ──
  if (edge && !node) {
    const d = (edge.data || {}) as { condition?: string; edgeType?: EdgeType; label?: string };
    return (
      <div style={{ ...panelBaseStyle, alignItems: 'stretch', justifyContent: 'flex-start' }}>
        <div style={sectionTitleStyle}>连线属性</div>
        <div style={{ flex: 1, overflowY: 'auto', padding: 16, display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div>
            <span style={{ ...labelStyle, display: 'inline' }}>从: </span>
            <span style={{ fontSize: 12, color: 'var(--text-primary)' }}>{edge.source}</span>
            <span style={{ ...labelStyle, display: 'inline', marginLeft: 12 }}>到: </span>
            <span style={{ fontSize: 12, color: 'var(--text-primary)' }}>{edge.target}</span>
          </div>
          <div>
            <label style={labelStyle}>类型</label>
            <select
              style={inputStyle}
              value={d.edgeType || 'forward'}
              onChange={(e) => onUpdateEdge(edge.id, { ...d, edgeType: e.target.value as EdgeType })}
            >
              <option value="forward">正向 (forward)</option>
              <option value="reject">打回 (reject)</option>
              <option value="escalate">升级 (escalate)</option>
            </select>
          </div>
          <div>
            <label style={labelStyle}>条件表达式</label>
            <input
              style={inputStyle}
              value={d.condition || ''}
              onChange={(e) => onUpdateEdge(edge.id, { ...d, condition: e.target.value })}
              placeholder="hitl_result == 'approve'"
            />
          </div>
          <div>
            <label style={labelStyle}>标签</label>
            <input
              style={inputStyle}
              value={d.label || ''}
              onChange={(e) => onUpdateEdge(edge.id, { ...d, label: e.target.value })}
              placeholder="通过 / 打回 / 升级"
            />
          </div>
        </div>
      </div>
    );
  }

  // ── 节点属性编辑 ──
  const data = node!.data as Record<string, unknown>;
  const handleChange = (key: string, value: string) => {
    onUpdateNode(node!.id, { ...data, [key]: value });
  };

  return (
    <div style={{ ...panelBaseStyle, alignItems: 'stretch', justifyContent: 'flex-start' }}>
      <div style={sectionTitleStyle}>节点属性</div>
      <div style={{ flex: 1, overflowY: 'auto', padding: 16, display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div>
          <label style={labelStyle}>ID</label>
          <input style={{ ...inputStyle, opacity: 0.5, cursor: 'not-allowed' }} value={node!.id} disabled />
        </div>
        <div>
          <label style={labelStyle}>类型</label>
          <input style={{ ...inputStyle, opacity: 0.5, cursor: 'not-allowed' }} value={node!.type || ''} disabled />
        </div>
        <div>
          <label style={labelStyle}>标签</label>
          <input
            style={inputStyle}
            value={String(data.label || '')}
            onChange={(e) => handleChange('label', e.target.value)}
          />
        </div>

        {node!.type === 'agent_action' && (
          <>
            {workflowMode === 'template' ? (
              <div>
                <label style={labelStyle}>角色类型（模板模式）</label>
                <select
                  style={inputStyle}
                  value={String(data.role_type || '')}
                  onChange={(e) => handleChange('role_type', e.target.value)}
                >
                  <option value="">— 选择角色类型 —</option>
                  <option value="pm">📋 产品经理</option>
                  <option value="ui_designer">🎨 UI 设计师</option>
                  <option value="architect">🏗 架构师</option>
                  <option value="backend_dev">⚙ 后端工程师</option>
                  <option value="frontend_dev">💻 前端工程师</option>
                  <option value="tester">🧪 测试员</option>
                  <option value="devops">🚀 运维工程师</option>
                  <option value="code_reviewer">🔍 代码审查员</option>
                  <option value="custom">⭐ 自定义角色</option>
                </select>
              </div>
            ) : (
              <div>
                <label style={labelStyle}>绑定 Agent（团队专属模式）</label>
                <select
                  style={inputStyle}
                  value={String(data.agent_id || '')}
                  onChange={(e) => handleChange('agent_id', e.target.value)}
                >
                  <option value="">— 选择 Agent —</option>
                  {availableAgents.map((agent) => (
                    <option key={agent.id} value={agent.id}>
                      {agent.name}
                    </option>
                  ))}
                </select>
              </div>
            )}
            <div>
              <label style={labelStyle}>提示词模板</label>
              <textarea
                style={{ ...inputStyle, height: 80, resize: 'none' as const }}
                value={String(data.prompt_template || '')}
                onChange={(e) => handleChange('prompt_template', e.target.value)}
                placeholder="Enter prompt template..."
              />
            </div>
          </>
        )}

        {node!.type === 'hitl' && (
          <>
            <div>
              <label style={labelStyle}>HITL 类型</label>
              <select
                style={inputStyle}
                value={String(data.hitl_type || 'confirm')}
                onChange={(e) => handleChange('hitl_type', e.target.value)}
              >
                <option value="confirm">👤 确认（是/否）</option>
                <option value="input">✏️ 输入收集</option>
                <option value="choice">🔘 选择题</option>
              </select>
            </div>
            <div>
              <label style={labelStyle}>提示消息</label>
              <textarea
                style={{ ...inputStyle, height: 60, resize: 'none' as const }}
                value={String(data.message || '')}
                onChange={(e) => handleChange('message', e.target.value)}
                placeholder="请确认以下内容..."
              />
            </div>
            <div>
              <label style={labelStyle}>强制人工介入</label>
              <select
                style={inputStyle}
                value={String(data.require_human ?? true)}
                onChange={(e) => handleChange('require_human', e.target.value === 'true')}
              >
                <option value="true">☑ 需要人工确认</option>
                <option value="false">☐ 可自动处理</option>
              </select>
            </div>
            <div>
              <label style={labelStyle}>超时时间（秒）</label>
              <input
                style={inputStyle}
                type="number"
                value={String(data.timeout ?? 300)}
                onChange={(e) => handleChange('timeout', parseInt(e.target.value) || 300)}
                min="10"
                max="3600"
              />
            </div>
            {data.require_human !== false && (
              <>
                <div>
                  <label style={labelStyle}>自动动作（条件满足时）</label>
                  <select
                    style={inputStyle}
                    value={String(data.auto_action || 'approve')}
                    onChange={(e) => handleChange('auto_action', e.target.value)}
                  >
                    <option value="approve">✓ 自动批准</option>
                    <option value="reject">✗ 自动驳回</option>
                    <option value="defer">⏸️ 延后处理</option>
                  </select>
                </div>
                <div>
                  <label style={labelStyle}>条件字段</label>
                  <input
                    style={inputStyle}
                    value={String(data.condition_field || '')}
                    onChange={(e) => handleChange('condition_field', e.target.value)}
                    placeholder="last_confidence"
                  />
                </div>
                <div>
                  <label style={labelStyle}>条件表达式</label>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <select
                      style={{ ...inputStyle, width: 80 }}
                      value={String(data.condition_operator || '>=')}
                      onChange={(e) => handleChange('condition_operator', e.target.value)}
                    >
                      <option value=">=">&gt;=</option>
                      <option value="&lt;=">&lt;=</option>
                      <option value=">">&gt;</option>
                      <option value="&lt;">&lt;</option>
                      <option value="==">==</option>
                      <option value="!=">!=</option>
                    </select>
                    <input
                      style={{ ...inputStyle, flex: 1 }}
                      type="number"
                      value={String(data.condition_value ?? 0.8)}
                      onChange={(e) => handleChange('condition_value', parseFloat(e.target.value) || 0)}
                      placeholder="0.8"
                    />
                  </div>
                </div>
              </>
            )}
            {data.hitl_type === 'choice' && (
              <div>
                <label style={labelStyle}>选择题选项（一行一个，格式：值|显示文本）</label>
                <textarea
                  style={{ ...inputStyle, height: 80, resize: 'none' as const }}
                  value={String((data.choices as string[] || []).join('\n'))}
                  onChange={(e) => {
                    const lines = e.target.value.split('\n').filter(Boolean);
                    handleChange('choices', lines);
                  }}
                  placeholder="deploy|部署到生产&#10;staging|部署到测试环境&#10;cancel|取消部署"
                />
              </div>
            )}
            {data.hitl_type === 'input' && (
              <div>
                <label style={labelStyle}>上下文变量（逗号分隔）</label>
                <input
                  style={inputStyle}
                  value={String((data.context_vars as string[] || []).join(', '))}
                  onChange={(e) => handleChange('context_vars', e.target.value.split(',').map(s => s.trim()))}
                  placeholder="user_name, task_summary, confidence"
                />
              </div>
            )}
          </>
        )}

        {node!.type === 'validation' && (
          <>
            {workflowMode === 'template' ? (
              <div>
                <label style={labelStyle}>角色类型（模板模式）</label>
                <select
                  style={inputStyle}
                  value={String(data.role_type || '')}
                  onChange={(e) => handleChange('role_type', e.target.value)}
                >
                  <option value="">— 选择角色类型 —</option>
                  <option value="pm">📋 产品经理</option>
                  <option value="ui_designer">🎨 UI 设计师</option>
                  <option value="architect">🏗 架构师</option>
                  <option value="backend_dev">⚙ 后端工程师</option>
                  <option value="frontend_dev">💻 前端工程师</option>
                  <option value="tester">🧪 测试员</option>
                  <option value="devops">🚀 运维工程师</option>
                  <option value="code_reviewer">🔍 代码审查员</option>
                  <option value="custom">⭐ 自定义角色</option>
                </select>
              </div>
            ) : (
              <div>
                <label style={labelStyle}>绑定 Agent（团队专属模式）</label>
                <select
                  style={inputStyle}
                  value={String(data.agent_id || '')}
                  onChange={(e) => handleChange('agent_id', e.target.value)}
                >
                  <option value="">— 选择 Agent —</option>
                  {availableAgents.map((agent) => (
                    <option key={agent.id} value={agent.id}>
                      {agent.name}
                    </option>
                  ))}
                </select>
              </div>
            )}
            <div>
              <label style={labelStyle}>检查项</label>
              <input
                style={inputStyle}
                value={String((data.checks as string[] || []).join(', '))}
                onChange={(e) => handleChange('checks', e.target.value.split(',').map(s => s.trim()))}
                placeholder="lint, unit_test, build"
              />
            </div>
            <div>
              <label style={labelStyle}>通过阈值</label>
              <input
                style={inputStyle}
                type="number"
                value={String(data.pass_threshold || 80)}
                onChange={(e) => handleChange('pass_threshold', e.target.value)}
              />
            </div>
          </>
        )}

        {node!.type === 'condition' && (
          <div>
            <label style={labelStyle}>条件表达式</label>
            <input
              style={inputStyle}
              value={String(data.expression || '')}
              onChange={(e) => handleChange('expression', e.target.value)}
              placeholder="hitl_result == 'approve'"
            />
          </div>
        )}

        {node!.type === 'router' && (
          <>
            <div>
              <label style={labelStyle}>路由 Schema</label>
              <textarea
                style={{ ...inputStyle, height: 100, resize: 'none' as const }}
                value={String(data.route_schema || '')}
                onChange={(e) => handleChange('route_schema', e.target.value)}
                placeholder='{
  "type": "object",
  "properties": {
    "route": {
      "type": "string",
      "enum": ["approve", "reject", "escalate"]
    }
  },
  "required": ["route"]
}'
              />
            </div>
            <div>
              <label style={labelStyle}>默认路由</label>
              <input
                style={inputStyle}
                value={String(data.default_route || '')}
                onChange={(e) => handleChange('default_route', e.target.value)}
                placeholder="默认路由路径（当 LLM 无法决定时）"
              />
            </div>
            <div style={{ fontSize: 10, color: 'var(--text-dim)', marginTop: 4, lineHeight: '14px' }}>
              💡 LLM 根据输入决定下一步走向，需提供结构化输出 Schema
            </div>
          </>
        )}

        {node!.type === 'parallel' && (
          <>
            <div>
              <label style={labelStyle}>汇聚方式</label>
              <select
                style={inputStyle}
                value={String(data.join_mode || 'all')}
                onChange={(e) => handleChange('join_mode', e.target.value)}
              >
                <option value="all">全部完成（等待所有分支）</option>
                <option value="any">任一完成（任一分支完成即继续）</option>
                <option value="n">N 个完成（指定数量）</option>
              </select>
            </div>
            {data.join_mode === 'n' && (
              <div>
                <label style={labelStyle}>完成数量</label>
                <input
                  style={inputStyle}
                  type="number"
                  value={String(data.join_count || 1)}
                  onChange={(e) => handleChange('join_count', parseInt(e.target.value) || 1)}
                  min={1}
                  placeholder="需要完成的分支数量"
                />
              </div>
            )}
            <div style={{ fontSize: 10, color: 'var(--text-dim)', marginTop: 4, lineHeight: '14px' }}>
              💡 多个分支并行执行，可配置汇聚条件
            </div>
          </>
        )}
      </div>
    </div>
  );
}

const panelBaseStyle: React.CSSProperties = {
  width: 320,
  background: 'var(--bg-base)',
  borderLeft: '1px solid var(--border-subtle)',
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  justifyContent: 'center',
  color: 'var(--text-dim)',
  fontSize: 13,
  gap: 8,
  flexShrink: 0,
  overflow: 'hidden',
};

const sectionTitleStyle: React.CSSProperties = {
  padding: '14px 16px 10px',
  fontSize: 11,
  fontWeight: 600,
  color: 'var(--text-muted)',
  textTransform: 'uppercase' as const,
  letterSpacing: 0.5,
  borderBottom: '1px solid var(--border-subtle)',
};

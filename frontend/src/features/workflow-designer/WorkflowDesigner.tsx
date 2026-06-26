/** Workflow Designer：统一工作流可视化编辑器

主要功能：
1. 工作流列表管理
2. 可视化编辑节点和边
3. 节点配置面板
4. 工作流验证
5. LLM 辅助生成
*/

import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { workflowApi } from '../../shared/api/workflows';

import { Canvas } from './Canvas';
import { Toolbar } from './Toolbar';
import { NodeConfigPanel } from './NodeConfigPanel';
import { PropertiesPanel } from './PropertiesPanel';
import type { Workflow } from '../../shared/types/workflow';
import type { Node, Edge, OnConnect, OnSelectionChangeFunc } from '@xyflow/react';

interface WorkflowDesignerProps {
  workflowId?: string;
}

export function WorkflowDesigner({ workflowId: propWorkflowId }: WorkflowDesignerProps) {
  const navigate = useNavigate();
  const params = useParams();
  const workflowId = propWorkflowId || params.id;

  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<Edge | null>(null);
  const [isDirty, setIsDirty] = useState(false);
  const [validationResult, setValidationResult] = useState<{
    valid: boolean;
    errors: string[];
    warnings: string[];
  } | null>(null);

  // 加载工作流
  useEffect(() => {
    if (workflowId && workflowId !== 'new') {
      loadWorkflow(workflowId);
    } else if (workflowId === 'new') {
      // 新建工作流
      initNewWorkflow();
    }
  }, [workflowId]);

  const loadWorkflow = async (id: string) => {
    try {
      const data = await workflowApi.getDetail(id);
      setWorkflow(data);

      // 转换为 React Flow 格式
      const reactNodes: Node[] = (data.definition?.nodes || []).map((n) => ({
        id: n.id,
        type: n.type.toLowerCase(),
        position: n.position || { x: 100 + Math.random() * 200, y: 100 + Math.random() * 200 },
        data: {
          label: n.label,
          config: n.config || {},
        },
      }));

      const reactEdges: Edge[] = (data.definition?.edges || []).map((e, i) => ({
        id: e.id || `edge-${i}`,
        source: e.source,
        target: e.target,
        type: (e.type || 'forward').toLowerCase(),
        data: {
          condition: e.condition,
        },
      }));

      setNodes(reactNodes);
      setEdges(reactEdges);
    } catch (error) {
      console.error('Failed to load workflow:', error);
    }
  };

  const initNewWorkflow = () => {
    setWorkflow({
      id: 'new',
      name: '新建工作流',
      description: '',
      definition: { nodes: [], edges: [] },
      version: 1,
      status: 'draft',
      is_template: false,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
    setNodes([]);
    setEdges([]);
  };

  const handleNodesChange = useCallback((changes: any[]) => {
    setNodes((nds) => {
      const updated = nds.map((node) => {
        const change = changes.find((c) => c.id === node.id);
        if (change) {
          if (change.type === 'position' && change.position) {
            return { ...node, position: change.position };
          }
          if (change.type === 'remove') {
            return null;
          }
        }
        return node;
      }).filter(Boolean) as Node[];
      setIsDirty(true);
      return updated;
    });
  }, []);

  const handleEdgesChange = useCallback((changes: any[]) => {
    setEdges((eds) => {
      const updated = eds.map((edge) => {
        const change = changes.find((c) => c.id === edge.id);
        if (change) {
          if (change.type === 'remove') {
            return null;
          }
        }
        return edge;
      }).filter(Boolean) as Edge[];
      setIsDirty(true);
      return updated;
    });
  }, []);

  const handleConnect: OnConnect = useCallback((connection) => {
    const newEdge: Edge = {
      ...connection,
      id: `edge-${Date.now()}`,
      type: 'forward',
      data: {},
    };
    setEdges((eds) => {
      setIsDirty(true);
      return [...eds, newEdge];
    });
  }, []);

  const handleSelectionChange: OnSelectionChangeFunc = useCallback(({ nodes: selectedNodes, edges: selectedEdges }) => {
    setSelectedNode(selectedNodes[0] || null);
    setSelectedEdge(selectedEdges[0] || null);
  }, []);

  const handleSave = async () => {
    if (!workflow) return;

    // 转换回工作流格式
    const definition = {
      nodes: nodes.map((n) => ({
        id: n.id,
        type: (n.type?.charAt(0).toUpperCase() + n.type?.slice(1)) as any,
        label: (n.data as { label: string }).label,
        config: (n.data as { config: Record<string, unknown> }).config,
        position: n.position,
      })),
      edges: edges.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        type: (e.type?.charAt(0).toUpperCase() + e.type?.slice(1)) as any,
        condition: (e.data as { condition?: Record<string, unknown> })?.condition,
      })),
    };

    try {
      if (workflow.id === 'new') {
        // 创建新工作流
        const newWorkflow = await workflowApi.create({
          name: workflow.name,
          description: workflow.description,
          definition,
        });
        setWorkflow(newWorkflow);
        navigate(`/workflows/${newWorkflow.id}`, { replace: true });
      } else {
        // 更新现有工作流
        const updated = await workflowApi.update(workflow.id, { definition });
        setWorkflow(updated);
      }
      setIsDirty(false);
      setValidationResult({ valid: true, errors: [], warnings: [] });
    } catch (error: any) {
      console.error('Failed to save workflow:', error);
      setValidationResult({
        valid: false,
        errors: [error.message || '保存失败'],
        warnings: [],
      });
    }
  };

  const handleValidate = async () => {
    if (!workflow || workflow.id === 'new') {
      setValidationResult({
        valid: false,
        errors: ['请先保存工作流后再验证'],
        warnings: [],
      });
      return;
    }

    try {
      const result = await workflowApi.validate(workflow.id);
      setValidationResult(result);
    } catch (error: any) {
      console.error('Failed to validate workflow:', error);
      setValidationResult({
        valid: false,
        errors: [error.message || '验证失败'],
        warnings: [],
      });
    }
  };

  const handleNew = () => {
    navigate('/workflows/new');
  };

  const handleBack = () => {
    if (isDirty) {
      if (confirm('有未保存的更改，确定要离开吗？')) {
        navigate('/workflows');
      }
    } else {
      navigate('/workflows');
    }
  };

  // 处理添加节点事件
  useEffect(() => {
    const handleAddNode = (event: CustomEvent) => {
      const { type } = event.detail;
      const newNode: Node = {
        id: `node-${Date.now()}`,
        type: type.toLowerCase(),
        position: { x: 100 + Math.random() * 300, y: 100 + Math.random() * 300 },
        data: {
          label: `${type} 节点`,
          config: {},
        },
      };
      setNodes((nds) => [...nds, newNode]);
      setIsDirty(true);
    };

    window.addEventListener('workflow-add-node', handleAddNode as EventListener);
    return () => {
      window.removeEventListener('workflow-add-node', handleAddNode as EventListener);
    };
  }, []);

  if (!workflow) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100vh',
          fontSize: '16px',
          color: '#6b7280',
        }}
      >
        加载中...
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      {/* 工具栏 */}
      <Toolbar
        workflowName={workflow.name}
        isDirty={isDirty}
        onSave={handleSave}
        onValidate={handleValidate}
        onNew={handleNew}
        onBack={handleBack}
      />

      {/* 验证结果提示 */}
      {validationResult && (
        <div
          style={{
            position: 'fixed',
            top: '80px',
            right: '24px',
            padding: '12px 16px',
            background: validationResult.valid ? '#d1fae5' : '#fef2f2',
            border: `1px solid ${validationResult.valid ? '#6ee7b7' : '#fecaca'}`,
            borderRadius: '8px',
            boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
            zIndex: 1000,
            minWidth: '300px',
          }}
        >
          <div style={{ fontWeight: '600', color: validationResult.valid ? '#065f46' : '#991b1b', marginBottom: '8px' }}>
            {validationResult.valid ? '✓ 验证通过' : '✗ 验证失败'}
          </div>
          {validationResult.errors.length > 0 && (
            <>
              {validationResult.errors.map((error, i) => (
                <div key={i} style={{ fontSize: '13px', color: '#b91c1c' }}>
                  • {error}
                </div>
              ))}
            </>
          )}
          {validationResult.warnings.length > 0 && (
            <>
              <div style={{ fontWeight: '500', color: '#92400e', marginTop: '8px', marginBottom: '4px' }}>
                警告：
              </div>
              {validationResult.warnings.map((warning, i) => (
                <div key={i} style={{ fontSize: '13px', color: '#b45309' }}>
                  • {warning}
                </div>
              ))}
            </>
          )}
        </div>
      )}

      {/* 主内容区 */}
      <div style={{ display: 'flex', flex: 1 }}>
        {/* 画布 */}
        <Canvas
          nodes={nodes}
          edges={edges}
          onNodesChange={handleNodesChange}
          onEdgesChange={handleEdgesChange}
          onConnect={handleConnect}
          onSelectionChange={handleSelectionChange}
        />

        {/* 节点配置面板 */}
        {selectedNode && (
          <NodeConfigPanel
            node={selectedNode}
            onChange={(updatedNode) => {
              setNodes((nds) =>
                nds.map((n) => (n.id === updatedNode.id ? updatedNode : n))
              );
              setIsDirty(true);
            }}
          />
        )}

        {/* 属性面板 */}
        {selectedEdge && !selectedNode && (
          <PropertiesPanel
            edge={selectedEdge}
            onChange={(updatedEdge) => {
              setEdges((eds) =>
                eds.map((e) => (e.id === updatedEdge.id ? updatedEdge : e))
              );
              setIsDirty(true);
            }}
          />
        )}
      </div>
    </div>
  );
}

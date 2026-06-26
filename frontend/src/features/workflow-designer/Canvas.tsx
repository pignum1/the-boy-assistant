/** Canvas：工作流可视化画布组件

使用 ReactFlow 提供拖拽式节点编辑功能
*/

import { useCallback, useMemo } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  NodeTypes,
  EdgeTypes,
  addEdge,
  Connection,
  Edge,
  Node,
  useNodesState,
  useEdgesState,
  OnNodesChange,
  OnEdgesChange,
  OnConnect,
  OnSelectionChangeFunc,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import type { WorkflowNodeDef, NodeType } from '../../../shared/types/workflow';

// 节点颜色配置
const NODE_COLORS: Record<NodeType, { bg: string; border: string }> = {
  Start: { bg: '#dcfce7', border: '#22c55e' },      // 绿色
  End: { bg: '#fee2e2', border: '#ef4444' },        // 红色
  Agent: { bg: '#dbeafe', border: '#3b82f6' },      // 蓝色
  Router: { bg: '#fef3c7', border: '#f59e0b' },     // 黄色
  Parallel: { bg: '#e0e7ff', border: '#6366f1' },    // 靛蓝
  Condition: { bg: '#f3e8ff', border: '#a855f7' },  // 紫色
  HITL: { bg: '#ffe4e6', border: '#f43f5e' },       // 粉红
  Validation: { bg: '#ccfbf1', border: '#14b8a6' }, // 青色
};

// 自定义节点组件
function CustomNode({ data, type }: { data: { label: string }; type: string }) {
  const nodeType = type.charAt(0).toUpperCase() + type.slice(1) as NodeType;
  const colors = NODE_COLORS[nodeType] || { bg: '#f3f4f6', border: '#9ca3af' };

  return (
    <div
      style={{
        padding: '12px 16px',
        borderRadius: '8px',
        background: colors.bg,
        border: `2px solid ${colors.border}`,
        minWidth: '120px',
        textAlign: 'center',
        fontSize: '14px',
        fontWeight: '500',
        color: '#1f2937',
        boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
      }}
    >
      <div style={{ fontSize: '10px', color: '#6b7280', marginBottom: '4px' }}>
        {nodeType}
      </div>
      <div>{data.label}</div>
    </div>
  );
}

// 节点类型配置
const nodeTypes: NodeTypes = {
  start: (props: any) => <CustomNode {...props} type="start" />,
  end: (props: any) => <CustomNode {...props} type="end" />,
  agent: (props: any) => <CustomNode {...props} type="agent" />,
  router: (props: any) => <CustomNode {...props} type="router" />,
  parallel: (props: any) => <CustomNode {...props} type="parallel" />,
  condition: (props: any) => <CustomNode {...props} type="condition" />,
  hitl: (props: any) => <CustomNode {...props} type="hitl" />,
  validation: (props: any) => <CustomNode {...props} type="validation" />,
};

// 边类型配置
const edgeTypes: EdgeTypes = {
  forward: 'default',
  reject: 'default',
  escalate: 'default',
  timeout: 'default',
  fallback: 'default',
};

interface CanvasProps {
  nodes: Node[];
  edges: Edge[];
  onNodesChange: OnNodesChange;
  onEdgesChange: OnEdgesChange;
  onConnect: OnConnect;
  onSelectionChange: OnSelectionChangeFunc;
}

export function Canvas({
  nodes,
  edges,
  onNodesChange,
  onEdgesChange,
  onConnect,
  onSelectionChange,
}: CanvasProps) {
  const [internalNodes, setInternalNodes, onNodesChangeInternal] = useNodesState(nodes);
  const [internalEdges, setInternalEdges, onEdgesChangeInternal] = useEdgesState(edges);

  // 同步外部状态变化
  const syncNodes = useCallback(() => {
    setInternalNodes(nodes);
  }, [nodes, setInternalNodes]);

  const syncEdges = useCallback(() => {
    setInternalEdges(edges);
  }, [edges, setInternalEdges]);

  // 连接处理
  const handleConnect = useCallback(
    (connection: Connection) => {
      const newEdge = {
        ...connection,
        id: `edge-${Date.now()}`,
        type: 'forward',
        animated: false,
        style: { stroke: '#94a3b8', strokeWidth: 2 },
      };
      onConnect(newEdge);
    },
    [onConnect]
  );

  // 边样式计算
  const edgeStyles = useMemo(() => {
    return edges.reduce((acc, edge) => {
      const type = edge.type || 'forward';
      const colors: Record<string, string> = {
        forward: '#94a3b8',
        reject: '#ef4444',
        escalate: '#f59e0b',
        timeout: '#8b5cf6',
        fallback: '#6b7280',
      };
      acc[edge.id] = {
        stroke: colors[type] || '#94a3b8',
        strokeWidth: type === 'forward' ? 2 : 2,
        strokeDasharray: type === 'timeout' ? '5,5' : undefined,
      };
      return acc;
    }, {} as Record<string, { stroke: string; strokeWidth: number; strokeDasharray?: string }>);
  }, [edges]);

  // 应用边样式
  const styledEdges = useMemo(() => {
    return edges.map((edge) => ({
      ...edge,
      animated: edge.type === 'forward',
      style: edgeStyles[edge.id] || { stroke: '#94a3b8', strokeWidth: 2 },
    }));
  }, [edges, edgeStyles]);

  return (
    <div style={{ width: '100%', height: '100%' }}>
      <ReactFlow
        nodes={internalNodes}
        edges={styledEdges}
        onNodesChange={(changes) => {
          onNodesChangeInternal(changes);
          onNodesChange(changes);
        }}
        onEdgesChange={(changes) => {
          onEdgesChangeInternal(changes);
          onEdgesChange(changes);
        }}
        onConnect={handleConnect}
        onSelectionChange={onSelectionChange}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
        snapToGrid
        snapGrid={[15, 15]}
        defaultEdgeOptions={{
          animated: false,
          style: { stroke: '#94a3b8', strokeWidth: 2 },
        }}
      >
        <Background />
        <Controls />
        <MiniMap
          nodeColor={(node) => {
            const nodeType = node.type || 'agent';
            const type = nodeType.charAt(0).toUpperCase() + nodeType.slice(1) as NodeType;
            return NODE_COLORS[type]?.bg || '#f3f4f6';
          }}
        />
      </ReactFlow>
    </div>
  );
}

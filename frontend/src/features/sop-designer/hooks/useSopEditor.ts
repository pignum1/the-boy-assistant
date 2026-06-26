import { useCallback, useState } from 'react';
import {
  useNodesState,
  useEdgesState,
  addEdge,
  type Connection,
  type Node as ReactFlowNode,
  type Edge,
} from '@xyflow/react';
import type { SOPNode, SOPEdge, SOPDefinition, EdgeType, WorkflowMode } from '../../../shared/types/sop';
import { inferEdgeType } from '../../../shared/types/sop';
import { autoLayout } from '../../../shared/utils/layout';

let nodeIdCounter = 0;

function nextId(nodeType: string) {
  nodeIdCounter += 1;
  return `${nodeType}_${nodeIdCounter}`;
}

/** 根据 SOP 边生成 ReactFlow Edge */
function sopEdgeToFlowEdge(e: SOPEdge, index: number): Edge {
  const edgeType = e.edgeType || inferEdgeType(e.condition);
  const label = e.label || inferLabel(e.condition, edgeType);
  return {
    id: `e${index}_${e.from}_${e.to}`,
    source: e.from,
    target: e.to,
    type: edgeType,
    label: undefined, // label 通过 data 传递给自定义组件渲染
    data: {
      condition: e.condition,
      edgeType,
      label,
    },
  };
}

/** 根据 condition 推断显示标签 */
function inferLabel(condition?: string, edgeType?: EdgeType): string {
  if (!condition) return '';
  if (edgeType === 'reject') {
    if (condition.includes('reject')) return '打回';
    if (condition.includes('not ')) return '失败';
    return '不通过';
  }
  if (edgeType === 'escalate') return '升级';
  if (condition.includes('approve')) return '通过';
  if (condition.includes('passed')) return '通过';
  return condition;
}

export function useSopEditor(initialSop?: SOPDefinition) {
  const [name, setName] = useState(initialSop?.name || 'Untitled');
  const [description, setDescription] = useState(initialSop?.description || '');
  const [workflowMode, setWorkflowMode] = useState<WorkflowMode>(
    initialSop?.workflow_mode || 'template'
  );
  const [availableAgents, setAvailableAgents] = useState<Array<{ id: string; name: string }>>([]);

  const initialNodes: ReactFlowNode[] = (initialSop?.nodes || []).map((n) => ({
    id: n.id,
    type: n.type,
    position: { x: 0, y: 0 },
    data: { ...n },
  }));

  const initialEdges: Edge[] = (initialSop?.edges || []).map((e, i) => sopEdgeToFlowEdge(e, i));

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  const onConnect = useCallback(
    (connection: Connection) => {
      const newEdge: Edge = {
        ...connection,
        type: 'forward',
        data: { edgeType: 'forward' as EdgeType, label: '' },
      };
      setEdges((eds) => addEdge(newEdge, eds));
    },
    [setEdges]
  );

  const addNode = useCallback(
    (nodeType: string) => {
      const id = nextId(nodeType);
      const newNode: ReactFlowNode = {
        id,
        type: nodeType,
        position: { x: Math.random() * 400 + 100, y: Math.random() * 400 + 100 },
        data: { id, type: nodeType },
      };
      setNodes((nds) => [...nds, newNode]);
    },
    [setNodes]
  );

  const deleteSelected = useCallback(() => {
    setNodes((nds) => nds.filter((n) => !n.selected));
    setEdges((eds) => eds.filter((e) => !e.selected));
  }, [setNodes, setEdges]);

  const doAutoLayout = useCallback(() => {
    setNodes((nds) => autoLayout(nds, edges));
  }, [edges, setNodes]);

  const clearAll = useCallback(() => {
    setNodes([]);
    setEdges([]);
  }, [setNodes, setEdges]);

  const loadSop = useCallback(
    (sop: SOPDefinition) => {
      setName(sop.name);
      setDescription(sop.description || '');
      setWorkflowMode(sop.workflow_mode || 'template');
      const loadedNodes: ReactFlowNode[] = (sop.nodes || []).map((n) => ({
        id: n.id,
        type: n.type,
        position: { x: 0, y: 0 },
        data: { ...n },
      }));
      const loadedEdges: Edge[] = (sop.edges || []).map((e, i) => sopEdgeToFlowEdge(e, i));
      setNodes(loadedNodes);
      setEdges(loadedEdges);
      requestAnimationFrame(() => {
        setNodes((nds) => autoLayout(nds, loadedEdges));
      });
    },
    [setNodes, setEdges]
  );

  const updateNodeData = useCallback(
    (nodeId: string, data: Record<string, unknown>) => {
      setNodes((nds) =>
        nds.map((n) => {
          if (n.id !== nodeId) return n;
          return { ...n, data: { ...n.data, ...data } };
        })
      );
    },
    [setNodes]
  );

  const updateEdgeData = useCallback(
    (edgeId: string, data: Record<string, unknown>) => {
      setEdges((eds) =>
        eds.map((e) => {
          if (e.id !== edgeId) return e;
          const newType = (data.edgeType as EdgeType) || e.type || 'forward';
          return {
            ...e,
            type: newType,
            data: { ...e.data, ...data },
          };
        })
      );
    },
    [setEdges]
  );

  const toSopDefinition = useCallback((): SOPDefinition => {
    const sopNodes: SOPNode[] = nodes.map((n) => ({
      id: n.id,
      type: n.type as SOPNode['type'],
      ...n.data,
    }));
    const sopEdges: SOPEdge[] = edges.map((e) => {
      const d = (e.data || {}) as { condition?: string; edgeType?: EdgeType; label?: string };
      return {
        from: e.source,
        to: e.target,
        condition: d.condition,
        edgeType: d.edgeType || inferEdgeType(d.condition),
        label: d.label,
      };
    });
    return {
      name,
      description,
      version: '1.0',
      nodes: sopNodes,
      edges: sopEdges,
      workflow_mode: workflowMode,
    };
  }, [nodes, edges, name, description, workflowMode]);

  return {
    name,
    setName,
    description,
    setDescription,
    nodes,
    edges,
    onNodesChange,
    onEdgesChange,
    onConnect,
    addNode,
    deleteSelected,
    doAutoLayout,
    clearAll,
    loadSop,
    updateNodeData,
    updateEdgeData,
    toSopDefinition,
    workflowMode,
    setWorkflowMode,
    availableAgents,
    setAvailableAgents,
  };
}

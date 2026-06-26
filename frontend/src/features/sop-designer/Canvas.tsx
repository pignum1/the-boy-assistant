import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  type NodeTypes,
  type EdgeTypes,
  type OnSelectionChangeFunc,
  type Edge,
  type NodeChange,
  type EdgeChange,
  type OnConnect,
  type Node as ReactFlowNode,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { StartNode } from './custom-nodes/StartNode';
import { EndNode } from './custom-nodes/EndNode';
import { AgentActionNode } from './custom-nodes/AgentActionNode';
import { HitlNode } from './custom-nodes/HitlNode';
import { ValidationNode } from './custom-nodes/ValidationNode';
import { ConditionNode } from './custom-nodes/ConditionNode';
import { RouterNode } from './custom-nodes/RouterNode';
import { ParallelNode } from './custom-nodes/ParallelNode';
import { ForwardEdge } from './custom-edges/ForwardEdge';
import { RejectEdge } from './custom-edges/RejectEdge';
import { EscalateEdge } from './custom-edges/EscalateEdge';

const nodeTypes: NodeTypes = {
  start: StartNode,
  end: EndNode,
  agent_action: AgentActionNode,
  router: RouterNode,
  parallel: ParallelNode,
  hitl: HitlNode,
  validation: ValidationNode,
  condition: ConditionNode,
};

const edgeTypes: EdgeTypes = {
  forward: ForwardEdge,
  reject: RejectEdge,
  escalate: EscalateEdge,
};

interface CanvasProps {
  nodes: ReactFlowNode[];
  edges: Edge[];
  onNodesChange: (changes: NodeChange[]) => void;
  onEdgesChange: (changes: EdgeChange[]) => void;
  onConnect: OnConnect;
  onSelectionChange?: OnSelectionChangeFunc;
  onEdgeDoubleClick?: (event: React.MouseEvent, edge: Edge) => void;
}

export function Canvas({
  nodes,
  edges,
  onNodesChange,
  onEdgesChange,
  onConnect,
  onSelectionChange,
  onEdgeDoubleClick,
}: CanvasProps) {
  return (
    <div style={{ flex: 1, position: 'relative', overflow: 'hidden', background: 'var(--bg-deep)' }}>
      <div
        style={{
          position: 'absolute',
          inset: 0,
          backgroundImage: 'radial-gradient(circle, rgba(148,163,184,0.05) 1px, transparent 1px)',
          backgroundSize: '24px 24px',
          pointerEvents: 'none',
        }}
      />
      {/* 图例 */}
      <div
        style={{
          position: 'absolute',
          bottom: 12,
          left: 12,
          zIndex: 10,
          display: 'flex',
          gap: 12,
          padding: '6px 12px',
          background: 'var(--bg-card)',
          border: '1px solid var(--border-subtle)',
          borderRadius: 8,
          fontSize: 10,
          color: 'var(--text-muted)',
          fontFamily: 'var(--font-body)',
        }}
      >
        <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <span style={{ width: 20, height: 2, background: 'rgba(52,211,153,0.6)', borderRadius: 1 }} />
          正向
        </span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <span style={{ width: 20, height: 2, background: 'rgba(239,68,68,0.5)', borderRadius: 1, borderTop: '2px dashed rgba(239,68,68,0.5)' }} />
          打回
        </span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <span style={{ width: 20, height: 2, background: 'rgba(245,158,11,0.6)', borderRadius: 1 }} />
          升级
        </span>
      </div>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onSelectionChange={onSelectionChange}
        onEdgeDoubleClick={onEdgeDoubleClick}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
        deleteKeyCode={['Backspace', 'Delete']}
        snapToGrid
        snapGrid={[15, 15]}
        style={{ background: 'transparent' }}
      >
        <Background gap={24} size={0.5} color="rgba(148,163,184,0.08)" />
        <Controls
          style={{ background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', borderRadius: 8 }}
        />
        <MiniMap
          nodeStrokeWidth={3}
          zoomable
          pannable
          style={{ border: '1px solid var(--border-subtle)', borderRadius: 8, background: 'var(--bg-card)' }}
        />
      </ReactFlow>
      <style>{`@keyframes dash{to{stroke-dashoffset:-10}}`}</style>
    </div>
  );
}

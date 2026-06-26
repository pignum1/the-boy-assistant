import { useState, useRef, useCallback, useEffect } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
  useNodesState,
  useEdgesState,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { api, getWsUrl } from '../../../shared/api/client';

interface WorkflowNode {
  id: string;
  key: string;
  name: string;
  agentId: string;
  agentName: string;
  agentEmoji: string;
  status: 'pending' | 'running' | 'done' | 'failed' | 'skipped';
  input?: string;
  output?: string;
  reasoning?: {
    thinking_steps?: string;
    decision_summary?: string;
  };
  startedAt?: number;
  endedAt?: number;
}

interface Props {
  sessionId: string;
  teamId: string;
}

export function LangGraphView({ sessionId, teamId }: Props) {
  const [userInput, setUserInput] = useState('');
  const [nodes, setNodes] = useState<WorkflowNode[]>([]);
  const [edges, setEdges] = useState<Array<{ id: string; source: string; target: string }>>([]);
  const [selectedNode, setSelectedNode] = useState<WorkflowNode | null>(null);
  const [expandedReasoning, setExpandedReasoning] = useState<Record<string, boolean>>({});
  const [expandedOutput, setExpandedOutput] = useState<Record<string, boolean>>({});
  const [isConnected, setIsConnected] = useState(false);
  const [executionState, setExecutionState] = useState<'idle' | 'running'>('idle');
  const wsRef = useRef<WebSocket | null>(null);

  // ReactFlow state
  const [flowNodes, setFlowNodes, onNodesChange] = useNodesState([]);
  const [flowEdges, setFlowEdges, onEdgesChange] = useEdgesState([]);

  // Load workflow definition
  useEffect(() => {
    api.get<{
      nodes: WorkflowNode[];
      edges: Array<{ id: string; source_id: string; target_id: string }>;
    }>(`/api/v1/teams/${teamId}/langgraph-workflow`)
      .then(data => {
        const workflowNodes = data.nodes || [];
        const workflowEdges = data.edges || [];

        setNodes(workflowNodes.map(n => ({
          ...n,
          status: 'pending',
        })));

        setEdges(workflowEdges.map(e => ({
          id: e.id,
          source: e.source_id,
          target: e.target_id,
        })));

        // Build ReactFlow nodes with layout
        const newFlowNodes: Node[] = workflowNodes.map((node, idx) => ({
          id: node.id,
          type: 'customNode',
          position: { x: idx * 200, y: 100 },
          data: {
            ...node,
            status: 'pending',
            onNodeClick: () => setSelectedNode(node),
          },
        }));

        const newFlowEdges: Edge[] = workflowEdges.map(e => ({
          id: e.id,
          source: e.source_id,
          target: e.target_id,
          animated: false,
        }));

        setFlowNodes(newFlowNodes);
        setFlowEdges(newFlowEdges);
      })
      .catch(() => {});
  }, [teamId]);

  // WebSocket connection
  useEffect(() => {
    const wsUrl = getWsUrl(`/ws/sessions/${sessionId}`);
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('[LangGraphView] WebSocket connected');
      setIsConnected(true);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        handleMessage(data);
      } catch (e) {
        console.error('Failed to parse WebSocket message:', e);
      }
    };

    ws.onclose = () => {
      console.log('[LangGraphView] WebSocket disconnected');
      setIsConnected(false);
    };

    ws.onerror = (error) => {
      console.error('[LangGraphView] WebSocket error:', error);
    };

    return () => {
      ws.close();
    };
  }, [sessionId]);

  const handleMessage = useCallback((data: any) => {
    switch (data.type) {
      case 'task_dag':
        setExecutionState('running');
        break;

      case 'task_status': {
        const payload = data.payload;
        setNodes(prev => prev.map(n =>
          n.id === payload.task_id
            ? { ...n, status: payload.status, endedAt: payload.status === 'done' ? Date.now() : n.endedAt }
            : n
        ));

        // Update flow nodes
        setFlowNodes(prevNodes =>
          prevNodes.map(node =>
            node.id === payload.task_id
              ? { ...node, data: { ...node.data, status: payload.status } }
              : node
          )
        );
        break;
      }

      case 'agent_message': {
        const payload = data.payload;
        setNodes(prev => prev.map(n => {
          if (n.id === payload.task_id || n.id === payload.node_key) {
            return { ...n, output: payload.content || '' };
          }
          return n;
        }));
        break;
      }

      case 'reasoning_complete': {
        const payload = data.payload;
        setNodes(prev => prev.map(n => {
          if (n.agentName === payload.agent || n.id === payload.task_id) {
            return {
              ...n,
              reasoning: {
                thinking_steps: payload.thinking_steps,
                decision_summary: payload.decision_summary,
              },
            };
          }
          return n;
        }));
        break;
      }

      case 'message_complete':
        setExecutionState('idle');
        break;

      case 'error':
        console.error('Server error:', data.payload);
        setExecutionState('idle');
        break;
    }
  }, []);

  const toggleReasoning = useCallback((nodeId: string) => {
    setExpandedReasoning(prev => ({ ...prev, [nodeId]: !prev[nodeId] }));
  }, []);

  const toggleOutput = useCallback((nodeId: string) => {
    setExpandedOutput(prev => ({ ...prev, [nodeId]: !prev[nodeId] }));
  }, []);

  const handleRetryNode = useCallback(async (nodeId: string) => {
    try {
      await api.post(`/api/v1/sessions/${sessionId}/retry-node`, { nodeId });
    } catch (e) {
      console.error('Failed to retry node:', e);
    }
  }, [sessionId]);

  const handleSubmit = useCallback(() => {
    if (!userInput.trim() || !wsRef.current) return;

    const messageToSend = userInput;
    setUserInput('');

    wsRef.current.send(JSON.stringify({
      type: 'chat',
      message: messageToSend,
    }));
  }, [userInput]);

  // Custom node component
  const nodeTypes = {
    customNode: ({ data }: { data: any }) => (
      <div
        onClick={() => setSelectedNode(data)}
        style={{
          padding: '12px 16px',
          background: '#ffffff',
          borderRadius: 8,
          border: `2px solid ${getNodeStatusColor(data.status)}`,
          minWidth: 150,
          cursor: 'pointer',
          boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{
            width: 24,
            height: 24,
            borderRadius: 6,
            background: getNodeStatusColor(data.status),
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 12,
          }}>
            {data.agentEmoji || '🔀'}
          </div>
          <div>
            <div style={{ fontSize: 13, fontWeight: 500, color: '#1f2937' }}>
              {data.name || data.key || '节点'}
            </div>
            <div style={{ fontSize: 11, color: '#6b7280' }}>
              {getNodeStatusText(data.status)}
            </div>
          </div>
        </div>
      </div>
    ),
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: '#f5f6f7' }}>
      {/* Header */}
      <div style={{
        padding: '16px 20px',
        background: '#ffffff',
        borderBottom: '1px solid #e5e7eb',
        boxShadow: '0 1px 2px rgba(0,0,0,0.02)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{
              display: 'inline-flex', alignItems: 'center', gap: 4,
              padding: '4px 12px', borderRadius: 20,
              fontSize: 12, fontWeight: 600,
              background: '#10b98118', color: '#10b981',
              border: '1px solid #10b98130',
            }}>
              🔗 工作流模式
            </span>
            <span style={{ fontSize: 12, color: '#6b7280' }}>LangGraph DAG 编排执行</span>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <div style={{
              width: 8,
              height: 8,
              borderRadius: '50%',
              background: isConnected ? '#10b981' : '#ef4444',
            }} />
            <div style={{
              padding: '6px 12px',
              background: '#f3f4f6',
              borderRadius: 16,
              fontSize: 12,
              color: '#6b7280',
            }}>
              {nodes.filter(n => n.status === 'done').length} / {nodes.length} 完成
            </div>
            {executionState === 'running' && (
              <div style={{
                padding: '6px 12px',
                background: '#dbeafe',
                borderRadius: 16,
                fontSize: 12,
                color: '#1e40af',
              }}>
                ⚡ 执行中
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* Flow Chart */}
        <div style={{ flex: 1, position: 'relative' }}>
          <ReactFlow
            nodes={flowNodes}
            edges={flowEdges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            nodeTypes={nodeTypes}
            fitView
          >
            <Background color="#e5e7eb" gap={16} />
            <Controls />
            <MiniMap />
          </ReactFlow>
        </div>

        {/* Node Details Panel */}
        <div style={{
          width: 380,
          background: '#ffffff',
          borderLeft: '1px solid #e5e7eb',
          display: 'flex',
          flexDirection: 'column',
        }}>
          <div style={{
            padding: '16px 20px',
            borderBottom: '1px solid #e5e7eb',
            fontWeight: 600,
            fontSize: 14,
            color: '#1f2937',
          }}>
            节点执行日志
          </div>

          <div style={{ flex: 1, overflowY: 'auto', padding: '16px' }}>
            {nodes.length === 0 ? (
              <div style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                height: 200,
                color: '#9ca3af',
                fontSize: 13,
              }}>
                暂无节点
              </div>
            ) : (
              nodes.map(node => (
                <NodeLog
                  key={node.id}
                  node={node}
                  expandedReasoning={expandedReasoning}
                  expandedOutput={expandedOutput}
                  toggleReasoning={toggleReasoning}
                  toggleOutput={toggleOutput}
                  onRetry={handleRetryNode}
                  onSelect={() => setSelectedNode(node)}
                  isSelected={selectedNode?.id === node.id}
                />
              ))
            )}
          </div>
        </div>
      </div>

      {/* Input */}
      <div style={{
        padding: '16px 20px',
        background: '#ffffff',
        borderTop: '1px solid #e5e7eb',
      }}>
        <div style={{
          display: 'flex',
          gap: 12,
          alignItems: 'flex-end',
        }}>
          <input
            type="text"
            value={userInput}
            onChange={(e) => setUserInput(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && handleSubmit()}
            placeholder="输入触发消息..."
            disabled={!isConnected || executionState !== 'idle'}
            style={{
              flex: 1,
              padding: '12px 16px',
              borderRadius: 12,
              border: '1px solid #e5e7eb',
              background: '#f9fafb',
              fontSize: 14,
              outline: 'none',
            }}
          />
          <button
            onClick={handleSubmit}
            disabled={!userInput.trim() || !isConnected || executionState !== 'idle'}
            style={{
              padding: '12px 24px',
              borderRadius: 10,
              background: (userInput.trim() && isConnected && executionState === 'idle') ? '#0066ff' : '#e5e7eb',
              color: (userInput.trim() && isConnected && executionState === 'idle') ? '#ffffff' : '#9ca3af',
              border: 'none',
              fontSize: 14,
              fontWeight: 500,
              cursor: (userInput.trim() && isConnected && executionState === 'idle') ? 'pointer' : 'not-allowed',
            }}
          >
            执行
          </button>
        </div>
      </div>
    </div>
  );
}

// Node Log Component
interface NodeLogProps {
  node: WorkflowNode;
  expandedReasoning: Record<string, boolean>;
  expandedOutput: Record<string, boolean>;
  toggleReasoning: (id: string) => void;
  toggleOutput: (id: string) => void;
  onRetry: (id: string) => void;
  onSelect: () => void;
  isSelected: boolean;
}

function NodeLog({
  node,
  expandedReasoning,
  expandedOutput,
  toggleReasoning,
  toggleOutput,
  onRetry,
  onSelect,
  isSelected,
}: NodeLogProps) {
  return (
    <div
      onClick={onSelect}
      style={{
        padding: '14px',
        background: isSelected ? '#f0f9ff' : '#f9fafb',
        borderRadius: 12,
        marginBottom: 10,
        border: `1px solid ${isSelected ? '#3b82f6' : '#e5e7eb'}`,
        cursor: 'pointer',
        transition: 'all 0.2s',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
        {/* Status Indicator */}
        <div style={{
          width: 10,
          height: 10,
          borderRadius: '50%',
          background: getNodeStatusColor(node.status),
          boxShadow: node.status === 'running' ? `0 0 8px ${getNodeStatusColor(node.status)}` : 'none',
          animation: node.status === 'running' ? 'pulse 2s infinite' : 'none',
        }} />

        {/* Agent Info */}
        <span style={{ fontSize: 14, fontWeight: 500, color: '#1f2937', flex: 1 }}>
          {node.agentEmoji} {node.agentName}
        </span>

        {/* Status Badge */}
        <span style={{
          fontSize: 11,
          padding: '3px 8px',
          borderRadius: 10,
          background: `${getNodeStatusColor(node.status)}15`,
          color: getNodeStatusColor(node.status),
        }}>
          {getNodeStatusText(node.status)}
        </span>
      </div>

      {/* Node Name */}
      <div style={{ fontSize: 13, color: '#374151', marginBottom: 8 }}>
        {node.name || node.key}
      </div>

      {/* Output Toggle */}
      {node.output && (
        <div style={{ marginBottom: 8 }}>
          <button
            onClick={(e) => { e.stopPropagation(); toggleOutput(node.id); }}
            style={{
              background: '#ffffff',
              border: '1px solid #e5e7eb',
              borderRadius: 6,
              padding: '4px 10px',
              fontSize: 11,
              color: '#6b7280',
              cursor: 'pointer',
            }}
          >
            📄 输出
            <span style={{ fontSize: 9, marginLeft: 4 }}>▼</span>
          </button>
          {expandedOutput[node.id] && (
            <div style={{
              marginTop: 6,
              padding: '10px 12px',
              background: '#ffffff',
              borderRadius: 6,
              fontSize: 12,
              color: '#4b5563',
              whiteSpace: 'pre-wrap',
              border: '1px solid #e5e7eb',
              maxHeight: 150,
              overflowY: 'auto',
            }}>
              {node.output}
            </div>
          )}
        </div>
      )}

      {/* Reasoning Toggle */}
      {node.reasoning && (
        <div style={{ marginBottom: 8 }}>
          <button
            onClick={(e) => { e.stopPropagation(); toggleReasoning(node.id); }}
            style={{
              background: '#ffffff',
              border: '1px solid #e5e7eb',
              borderRadius: 6,
              padding: '4px 10px',
              fontSize: 11,
              color: '#6b7280',
              cursor: 'pointer',
            }}
          >
            🧠 推理
            <span style={{ fontSize: 9, marginLeft: 4 }}>▼</span>
          </button>
          {expandedReasoning[node.id] && (
            <div style={{
              marginTop: 6,
              padding: '10px 12px',
              background: '#ffffff',
              borderRadius: 6,
              fontSize: 12,
              color: '#4b5563',
              whiteSpace: 'pre-wrap',
            }}>
              {node.reasoning.thinking_steps || node.reasoning.decision_summary || '无详细推理'}
            </div>
          )}
        </div>
      )}

      {/* Retry Button (for failed nodes) */}
      {node.status === 'failed' && (
        <button
          onClick={(e) => { e.stopPropagation(); onRetry(node.id); }}
          style={{
            padding: '6px 12px',
            borderRadius: 6,
            background: '#ef4444',
            color: '#ffffff',
            border: 'none',
            fontSize: 12,
            cursor: 'pointer',
          }}
        >
          🔄 重试此节点
        </button>
      )}
    </div>
  );
}

// Helper functions
function getNodeStatusColor(status: WorkflowNode['status']): string {
  switch (status) {
    case 'pending': return '#9ca3af';
    case 'running': return '#3b82f6';
    case 'done': return '#10b981';
    case 'failed': return '#ef4444';
    case 'skipped': return '#f59e0b';
  }
}

function getNodeStatusText(status: WorkflowNode['status']): string {
  switch (status) {
    case 'pending': return '待执行';
    case 'running': return '进行中';
    case 'done': return '已完成';
    case 'failed': return '失败';
    case 'skipped': return '跳过';
  }
}

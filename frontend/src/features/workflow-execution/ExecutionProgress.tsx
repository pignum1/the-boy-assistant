/** ExecutionProgress：工作流执行进度展示

实时显示工作流实例的执行状态和节点执行进度
*/

import { useState, useEffect, useRef } from 'react';
import type { WorkflowInstanceDetail, NodeExecution } from '../../shared/types/workflow';
import { workflowApi } from '../../shared/api/workflows';
import { getWsUrl } from '../../shared/api/client';

interface ExecutionProgressProps {
  instanceId: string;
}

export function ExecutionProgress({ instanceId }: ExecutionProgressProps) {
  const [instance, setInstance] = useState<WorkflowInstanceDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    loadInstanceDetail();
    connectWebSocket();

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [instanceId]);

  const loadInstanceDetail = async () => {
    try {
      setLoading(true);
      const data = await workflowApi.getInstanceDetail(instanceId);
      setInstance(data);
    } catch (error) {
      console.error('Failed to load instance detail:', error);
    } finally {
      setLoading(false);
    }
  };

  const connectWebSocket = () => {
    const wsUrl = getWsUrl(`/api/v1/workflow-events/ws/instances/${instanceId}`);
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      setConnected(true);
      console.log('WebSocket connected');
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      console.log('WebSocket event:', data);

      // 处理不同类型的事件
      switch (data.type) {
        case 'workflow.instance.started':
        case 'workflow.instance.updated':
          loadInstanceDetail();
          break;
        case 'workflow.node.started':
        case 'workflow.node.completed':
        case 'workflow.node.failed':
          loadInstanceDetail();
          break;
        case 'workflow.instance.completed':
        case 'workflow.instance.failed':
          loadInstanceDetail();
          break;
        case 'workflow.hitl.required':
          // 处理 HITL 请求
          console.log('HITL required:', data.data);
          break;
      }
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      setConnected(false);
    };

    ws.onclose = () => {
      setConnected(false);
      console.log('WebSocket disconnected');
      // 尝试重连
      setTimeout(() => {
        if (!wsRef.current || wsRef.current.readyState === WebSocket.CLOSED) {
          connectWebSocket();
        }
      }, 3000);
    };

    wsRef.current = ws;
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed':
        return { bg: '#dcfce7', text: '#166534', icon: '✓' };
      case 'failed':
        return { bg: '#fef2f2', text: '#991b1b', icon: '✗' };
      case 'running':
        return { bg: '#dbeafe', text: '#1e40af', icon: '⟳' };
      case 'pending':
        return { bg: '#f3f4f6', text: '#374151', icon: '⋯' };
      case 'paused':
        return { bg: '#fef3c7', text: '#92400e', icon: '⏸' };
      case 'cancelled':
        return { bg: '#f3f4f6', text: '#6b7280', icon: '−' };
      case 'skipped':
        return { bg: '#f3f4f6', text: '#9ca3af', icon: '→' };
      default:
        return { bg: '#f3f4f6', text: '#374151', icon: '?' };
    }
  };

  const getStatusLabel = (status: string) => {
    switch (status) {
      case 'completed':
        return '已完成';
      case 'failed':
        return '失败';
      case 'running':
        return '执行中';
      case 'pending':
        return '等待中';
      case 'paused':
        return '已暂停';
      case 'cancelled':
        return '已取消';
      case 'skipped':
        return '已跳过';
      default:
        return status;
    }
  };

  const handleHITLResponse = (action: 'approve' | 'reject' | 'input', input?: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      alert('WebSocket 未连接');
      return;
    }

    wsRef.current.send(JSON.stringify({
      type: 'workflow.hitl.response',
      data: {
        action,
        input,
      },
    }));
  };

  if (loading) {
    return (
      <div style={{ padding: '40px', textAlign: 'center', color: '#6b7280' }}>
        加载中...
      </div>
    );
  }

  if (!instance) {
    return (
      <div style={{ padding: '40px', textAlign: 'center', color: '#dc2626' }}>
        加载失败
      </div>
    );
  }

  const statusColor = getStatusColor(instance.status);
  const completedNodes = instance.node_executions?.filter((n) => n.status === 'completed').length || 0;
  const totalNodes = instance.node_executions?.length || 0;
  const progress = totalNodes > 0 ? (completedNodes / totalNodes) * 100 : 0;

  return (
    <div style={{ maxWidth: '800px', margin: '0 auto', padding: '24px' }}>
      {/* 头部：实例状态 */}
      <div style={{ marginBottom: '24px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <h1 style={{ margin: 0, fontSize: '24px', fontWeight: '700' }}>
            工作流执行进度
          </h1>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div
              style={{
                width: '8px',
                height: '8px',
                borderRadius: '50%',
                background: connected ? '#22c55e' : '#ef4444',
              }}
            />
            <span style={{ fontSize: '12px', color: '#6b7280' }}>
              {connected ? '已连接' : '未连接'}
            </span>
          </div>
        </div>

        <div
          style={{
            padding: '16px',
            background: statusColor.bg,
            border: '1px solid',
            borderColor: statusColor.text,
            borderRadius: '8px',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <div style={{ fontSize: '14px', color: statusColor.text, fontWeight: '600', marginBottom: '4px' }}>
                {statusColor.icon} {getStatusLabel(instance.status)}
              </div>
              <div style={{ fontSize: '12px', color: statusColor.text }}>
                实例 ID: {instance.id.slice(0, 8)}...
              </div>
            </div>

            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: '24px', fontWeight: '700', color: statusColor.text }}>
                {Math.round(progress)}%
              </div>
              <div style={{ fontSize: '12px', color: statusColor.text }}>
                {completedNodes} / {totalNodes} 节点
              </div>
            </div>
          </div>

          {/* 进度条 */}
          <div style={{ marginTop: '12px' }}>
            <div
              style={{
                height: '8px',
                background: '#e5e7eb',
                borderRadius: '4px',
                overflow: 'hidden',
              }}
            >
              <div
                style={{
                  height: '100%',
                  width: `${progress}%`,
                  background: statusColor.text,
                  transition: 'width 0.3s ease',
                }}
              />
            </div>
          </div>
        </div>
      </div>

      {/* HITL 状态 */}
      {instance.hitl_pending && (
        <div
          style={{
            padding: '16px',
            background: '#ffe4e6',
            border: '1px solid #f43f5e',
            borderRadius: '8px',
            marginBottom: '24px',
          }}
        >
          <div style={{ fontWeight: '600', color: '#881337', marginBottom: '12px' }}>
            ⚠️ 需要人工介入
          </div>

          <div style={{ fontSize: '14px', color: '#9f1239', marginBottom: '12px' }}>
            操作类型: {instance.hitl_action_type}
          </div>

          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              onClick={() => handleHITLResponse('approve')}
              style={{
                padding: '8px 16px',
                background: '#22c55e',
                border: 'none',
                borderRadius: '6px',
                cursor: 'pointer',
                fontSize: '14px',
                color: '#ffffff',
              }}
            >
              批准
            </button>

            <button
              onClick={() => handleHITLResponse('reject')}
              style={{
                padding: '8px 16px',
                background: '#ef4444',
                border: 'none',
                borderRadius: '6px',
                cursor: 'pointer',
                fontSize: '14px',
                color: '#ffffff',
              }}
            >
              拒绝
            </button>

            {instance.hitl_action_type === 'input' && (
              <input
                type="text"
                placeholder="输入内容"
                style={{
                  padding: '8px 12px',
                  border: '1px solid #f43f5e',
                  borderRadius: '6px',
                  fontSize: '14px',
                  flex: 1,
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    handleHITLResponse('input', e.currentTarget.value);
                  }
                }}
              />
            )}
          </div>
        </div>
      )}

      {/* 控制按钮 */}
      {instance.status === 'running' && (
        <div style={{ display: 'flex', gap: '12px', marginBottom: '24px' }}>
          <button
            onClick={async () => {
              await workflowApi.pauseExecution(instance.id);
              loadInstanceDetail();
            }}
            style={{
              padding: '10px 20px',
              background: '#f59e0b',
              border: 'none',
              borderRadius: '8px',
              cursor: 'pointer',
              fontSize: '14px',
              color: '#ffffff',
            }}
          >
            暂停
          </button>

          <button
            onClick={async () => {
              await workflowApi.cancelExecution(instance.id);
              loadInstanceDetail();
            }}
            style={{
              padding: '10px 20px',
              background: '#ef4444',
              border: 'none',
              borderRadius: '8px',
              cursor: 'pointer',
              fontSize: '14px',
              color: '#ffffff',
            }}
          >
            取消
          </button>
        </div>
      )}

      {instance.status === 'paused' && (
        <div style={{ display: 'flex', gap: '12px', marginBottom: '24px' }}>
          <button
            onClick={async () => {
              await workflowApi.resumeExecution(instance.id);
              loadInstanceDetail();
            }}
            style={{
              padding: '10px 20px',
              background: '#22c55e',
              border: 'none',
              borderRadius: '8px',
              cursor: 'pointer',
              fontSize: '14px',
              color: '#ffffff',
            }}
          >
            继续
          </button>

          <button
            onClick={async () => {
              await workflowApi.cancelExecution(instance.id);
              loadInstanceDetail();
            }}
            style={{
              padding: '10px 20px',
              background: '#ef4444',
              border: 'none',
              borderRadius: '8px',
              cursor: 'pointer',
              fontSize: '14px',
              color: '#ffffff',
            }}
          >
            取消
          </button>
        </div>
      )}

      {/* 节点执行列表 */}
      <div>
        <h2 style={{ margin: '0 0 16px', fontSize: '18px', fontWeight: '600' }}>
          节点执行记录
        </h2>

        {(!instance.node_executions || instance.node_executions.length === 0) ? (
          <div style={{ padding: '20px', textAlign: 'center', color: '#6b7280', background: '#f9fafb', borderRadius: '8px' }}>
            暂无执行记录
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {instance.node_executions.map((execution) => {
              const execStatus = getStatusColor(execution.status);

              return (
                <div
                  key={execution.id}
                  style={{
                    padding: '12px 16px',
                    background: '#ffffff',
                    border: '1px solid #e5e7eb',
                    borderRadius: '8px',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <div
                      style={{
                        width: '24px',
                        height: '24px',
                        borderRadius: '50%',
                        background: execStatus.bg,
                        color: execStatus.text,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: '12px',
                        fontWeight: '600',
                      }}
                    >
                      {execStatus.icon}
                    </div>

                    <div>
                      <div style={{ fontSize: '14px', fontWeight: '500', color: '#111827' }}>
                        {execution.node_label || execution.node_type}
                      </div>
                      <div style={{ fontSize: '12px', color: '#6b7280' }}>
                        {execution.node_type}
                        {execution.agent_name && ` · ${execution.agent_name}`}
                      </div>
                    </div>
                  </div>

                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: '13px', color: execStatus.text, fontWeight: '500' }}>
                      {getStatusLabel(execution.status)}
                    </div>
                    {execution.started_at && (
                      <div style={{ fontSize: '12px', color: '#9ca3af' }}>
                        {new Date(execution.started_at).toLocaleTimeString()}
                        {execution.completed_at && ` - ${new Date(execution.completed_at).toLocaleTimeString()}`}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* 错误信息 */}
      {instance.error_message && (
        <div
          style={{
            marginTop: '24px',
            padding: '16px',
            background: '#fef2f2',
            border: '1px solid #fecaca',
            borderRadius: '8px',
          }}
        >
          <div style={{ fontWeight: '600', color: '#991b1b', marginBottom: '8px' }}>
            执行错误
          </div>
          <div style={{ fontSize: '14px', color: '#b91c1c' }}>
            {instance.error_message}
          </div>
        </div>
      )}
    </div>
  );
}

import { useState } from 'react';
import type { HitlRequest } from './hooks/useTaskEvents';
import { tasksApi } from '../../shared/api/tasks';

interface HitlDialogProps {
  taskId: string;
  request: HitlRequest;
  onDismiss: () => void;
}

export function HitlDialog({ taskId, request, onDismiss }: HitlDialogProps) {
  const [feedback, setFeedback] = useState('');
  const [loading, setLoading] = useState(false);

  const handleRespond = async (approved: boolean) => {
    setLoading(true);
    try {
      await tasksApi.approve(taskId, approved, feedback || undefined);
      onDismiss();
    } catch (e) {
      alert('Failed to respond: ' + String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.6)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 50,
        backdropFilter: 'blur(4px)',
      }}
    >
      <div
        style={{
          background: 'var(--bg-card)',
          border: '1px solid var(--border-active)',
          borderRadius: 16,
          boxShadow: '0 24px 48px rgba(0,0,0,0.4)',
          width: '100%',
          maxWidth: 420,
          padding: 24,
        }}
      >
        <h3 style={{ fontSize: 16, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 8 }}>
          🛑 人工审批
        </h3>
        <p style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 4 }}>节点: {request.nodeId}</p>
        <p style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 16 }}>Agent: {request.agent}</p>

        <div
          style={{
            background: 'var(--gold-bg)',
            border: '1px solid var(--gold-border)',
            borderRadius: 10,
            padding: 12,
            marginBottom: 16,
          }}
        >
          <p style={{ fontSize: 13, color: 'var(--text-primary)' }}>{request.question}</p>
        </div>

        <textarea
          style={{
            width: '100%',
            background: 'var(--bg-elevated)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 8,
            padding: '8px 12px',
            fontSize: 12,
            color: 'var(--text-primary)',
            fontFamily: 'var(--font-body)',
            height: 70,
            resize: 'none' as const,
            outline: 'none',
            marginBottom: 16,
          }}
          placeholder="可选反馈..."
          value={feedback}
          onChange={(e) => setFeedback(e.target.value)}
        />

        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <button
            onClick={() => handleRespond(false)}
            disabled={loading}
            style={{
              padding: '8px 16px',
              fontSize: 12,
              background: 'var(--red-bg)',
              color: 'var(--red-400)',
              border: '1px solid var(--red-border)',
              borderRadius: 8,
              cursor: 'pointer',
              fontFamily: 'var(--font-body)',
              fontWeight: 500,
            }}
          >
            驳回
          </button>
          <button
            onClick={() => handleRespond(true)}
            disabled={loading}
            style={{
              padding: '8px 16px',
              fontSize: 12,
              background: 'linear-gradient(135deg, var(--gold-500), #d97706)',
              color: '#0a0f1e',
              border: 'none',
              borderRadius: 8,
              cursor: 'pointer',
              fontFamily: 'var(--font-body)',
              fontWeight: 600,
            }}
          >
            批准
          </button>
        </div>
      </div>
    </div>
  );
}

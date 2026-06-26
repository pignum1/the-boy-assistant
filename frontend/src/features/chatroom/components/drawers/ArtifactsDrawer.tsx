/** 产物抽屉：按 Agent 分组，显示真实路径，点击可预览内容 */

import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { ArtifactFile } from '../../types/state';
import { api } from '../../../../shared/api/client';

/** 判断文件是否为 Markdown 类型（可渲染为富文本） */
function isMarkdownFile(path: string): boolean {
  const ext = path.split('.').pop()?.toLowerCase();
  return ext === 'md' || ext === 'markdown' || ext === 'mdown';
}

interface Props {
  artifacts: ArtifactFile[];
  sessionId?: string;
  workspacePath?: string;
}

export function ArtifactsDrawer({ artifacts, sessionId, workspacePath }: Props) {
  if (artifacts.length === 0) {
    return (
      <div style={{ padding: '60px 20px', textAlign: 'center', color: 'var(--text-muted)', fontSize: 12 }}>
        还没有产物。任务执行完成后会出现在这里。
      </div>
    );
  }

  const byAgent = new Map<string, ArtifactFile[]>();
  for (const a of artifacts) {
    const key = a.producerAgentName || '未知';
    if (!byAgent.has(key)) byAgent.set(key, []);
    byAgent.get(key)!.push(a);
  }
  const totalSize = artifacts.reduce((s, a) => s + (a.sizeBytes || 0), 0);

  return (
    <div style={{ padding: '10px 14px', height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginBottom: 10, flexShrink: 0 }}>
        共 {artifacts.length} 个文件 · {formatSize(totalSize)}
      </div>
      {workspacePath && (
        <div style={{
          fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)',
          marginBottom: 10, padding: '4px 8px', background: 'var(--bg-base)',
          borderRadius: 4, border: '1px solid var(--border-subtle)',
          wordBreak: 'break-all', lineHeight: 1.4,
        }}>
          📂 {workspacePath}
        </div>
      )}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {Array.from(byAgent.entries()).map(([agent, files]) => (
          <div key={agent} style={{ marginBottom: 14 }}>
            <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 4, fontWeight: 600 }}>
              {agent} · {files.length} 文件
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              {files.map(f => <ArtifactRow key={f.id} file={f} sessionId={sessionId} />)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ArtifactRow({ file, sessionId }: { file: ArtifactFile; sessionId?: string }) {
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewContent, setPreviewContent] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  const handleClick = async () => {
    setPreviewOpen(true);
    if (!previewContent) {
      setPreviewLoading(true);
      try {
        if (sessionId) {
          const data = await api.get<{ content?: string; size?: number }>(
            `/api/v1/sessions/${sessionId}/workspace/files/${encodeURIComponent(file.path)}`
          );
          setPreviewContent(data?.content || '(无法读取文件内容)');
        } else {
          setPreviewContent('(会话 ID 不可用)');
        }
      } catch {
        setPreviewContent('(无法读取文件内容)');
      }
      setPreviewLoading(false);
    }
  };

  return (
    <>
      <div
        onClick={handleClick}
        style={{
          display: 'flex', alignItems: 'center', gap: 8,
          padding: '6px 8px', background: 'rgba(34,211,238,0.04)',
          border: '1px solid var(--border-subtle)', borderRadius: 4,
          fontSize: 11, cursor: 'pointer',
        }}
        title={`点击预览: ${file.path}`}
      >
        <span style={{ color: 'var(--cyan-400)', fontSize: 13 }}>📄</span>
        <span style={{
          flex: 1, color: 'var(--text-primary)', overflow: 'hidden',
          textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontFamily: 'var(--font-mono)', fontSize: 11,
        }}>
          {file.path || file.name}
        </span>
        <span style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
          {file.sizeBytes > 0 ? formatSize(file.sizeBytes) : ''}
        </span>
        <StatusBadge status={file.status} />
      </div>

      {/* Modal overlay preview */}
      {previewOpen && (
        <div
          onClick={() => setPreviewOpen(false)}
          style={{
            position: 'fixed', inset: 0, zIndex: 500,
            background: 'rgba(0,0,0,0.45)', display: 'flex',
            alignItems: 'center', justifyContent: 'center',
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              width: '75vw', maxWidth: 900, maxHeight: '85vh',
              background: 'var(--bg-base)',
              borderRadius: 12,
              border: '1px solid var(--border-subtle)',
              boxShadow: '0 24px 64px rgba(0,0,0,0.5)',
              display: 'flex', flexDirection: 'column', overflow: 'hidden',
            }}
          >
            {/* Header */}
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '12px 16px', borderBottom: '1px solid var(--border-subtle)',
              flexShrink: 0,
            }}>
              <span style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>
                📂 {file.path}
              </span>
              <button
                onClick={() => setPreviewOpen(false)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 16, color: 'var(--text-muted)' }}
              >
                ✕
              </button>
            </div>
            {/* Content */}
            <div style={{ flex: 1, overflow: 'auto', padding: '14px 16px' }}>
              {previewLoading ? (
                <div style={{ fontSize: 13, color: 'var(--text-muted)', textAlign: 'center', padding: 40 }}>加载中...</div>
              ) : isMarkdownFile(file.path) ? (
                <div style={{ fontSize: 13, lineHeight: 1.7, color: 'var(--text-primary)' }}>
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    components={{
                      table: ({ children }) => (
                        <div style={{ overflowX: 'auto', margin: '8px 0' }}>
                          <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 12, border: '1px solid var(--border-subtle)' }}>
                            {children}
                          </table>
                        </div>
                      ),
                      thead: ({ children }) => <thead style={{ background: 'var(--surface-elevated)' }}>{children}</thead>,
                      th: ({ children }) => <th style={{ padding: '6px 10px', textAlign: 'left', fontWeight: 600, border: '1px solid var(--border-subtle)', fontSize: 11 }}>{children}</th>,
                      td: ({ children }) => <td style={{ padding: '5px 10px', border: '1px solid var(--border-subtle)' }}>{children}</td>,
                      h1: ({ children }) => <h1 style={{ fontSize: 18, fontWeight: 700, margin: '12px 0 6px' }}>{children}</h1>,
                      h2: ({ children }) => <h2 style={{ fontSize: 15, fontWeight: 600, margin: '10px 0 5px' }}>{children}</h2>,
                      h3: ({ children }) => <h3 style={{ fontSize: 13, fontWeight: 600, margin: '8px 0 4px' }}>{children}</h3>,
                      code: ({ children, className }) => {
                        const isBlock = className || String(children).includes('\n');
                        if (isBlock) {
                          return (
                            <pre style={{ margin: '8px 0', padding: '12px', background: 'var(--bg-base)', borderRadius: 6, border: '1px solid var(--border-subtle)', fontSize: 11, fontFamily: 'var(--font-mono)', overflow: 'auto', whiteSpace: 'pre' }}>
                              <code className={className}>{children}</code>
                            </pre>
                          );
                        }
                        return <code style={{ background: 'var(--surface-elevated)', padding: '1px 5px', borderRadius: 3, fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--cyan-400)' }}>{children}</code>;
                      },
                      p: ({ children }) => <p style={{ margin: '4px 0' }}>{children}</p>,
                      ul: ({ children }) => <ul style={{ paddingLeft: 20, margin: '4px 0' }}>{children}</ul>,
                      ol: ({ children }) => <ol style={{ paddingLeft: 20, margin: '4px 0' }}>{children}</ol>,
                      li: ({ children }) => <li style={{ margin: '2px 0' }}>{children}</li>,
                      strong: ({ children }) => <strong style={{ fontWeight: 600 }}>{children}</strong>,
                      blockquote: ({ children }) => <blockquote style={{ borderLeft: '3px solid var(--gold-border)', paddingLeft: 10, margin: '6px 0', color: 'var(--text-muted)' }}>{children}</blockquote>,
                      hr: () => <hr style={{ border: 'none', borderTop: '1px solid var(--border-subtle)', margin: '10px 0' }} />,
                    }}
                  >
                    {previewContent || ''}
                  </ReactMarkdown>
                </div>
              ) : (
                <pre style={{
                  margin: 0, fontSize: 12, lineHeight: 1.6,
                  fontFamily: 'var(--font-mono)', color: 'var(--text-primary)',
                  whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                }}>
                  {previewContent}
                </pre>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function StatusBadge({ status }: { status: ArtifactFile['status'] }) {
  const c = status === 'created' ? 'var(--green-400)' : status === 'modified' ? 'var(--gold-400)' : 'var(--red-400)';
  const label = status === 'created' ? '+' : status === 'modified' ? '✎' : '-';
  return (
    <span style={{
      fontSize: 9, color: c, padding: '1px 4px', border: `1px solid ${c}33`,
      borderRadius: 2, fontFamily: 'var(--font-mono)', minWidth: 14, textAlign: 'center',
    }}>
      {label}
    </span>
  );
}

function formatSize(bytes: number): string {
  if (bytes === 0) return '—';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/** 代码块渲染器：从文本中提取 ``` 代码块并渲染为带语法高亮和复制按钮的卡片 */

import { useState, useCallback, type CSSProperties } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface CodeBlock {
  lang: string;
  code: string;
  path?: string;  // 如 ```python backend/main.py
  startIndex: number;
  endIndex: number;
}

const LANG_COLORS: Record<string, string> = {
  python: 'var(--blue-400)',
  typescript: 'var(--cyan-400)',
  javascript: 'var(--gold-400)',
  tsx: 'var(--cyan-400)',
  jsx: 'var(--gold-400)',
  html: 'var(--orange-400)',
  css: 'var(--purple-400)',
  json: 'var(--green-400)',
  yaml: 'var(--red-400)',
  sql: 'var(--indigo-400)',
  sh: 'var(--text-muted)',
  bash: 'var(--text-muted)',
  dockerfile: 'var(--blue-400)',
};

const codeBlockStyle: CSSProperties = {
  margin: '8px 0',
  borderRadius: 8,
  border: '1px solid var(--border-subtle)',
  overflow: 'hidden',
  background: 'var(--bg-base)',
};

const headerStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  padding: '6px 12px',
  background: 'var(--surface-elevated)',
  borderBottom: '1px solid var(--border-subtle)',
  fontSize: 11,
  fontFamily: 'var(--font-mono)',
};

/** 解析文本中的代码块 */
function parseCodeBlocks(content: string): CodeBlock[] {
  const blocks: CodeBlock[] = [];
  const regex = /```(\w+)(?:\s+([^\n]*?))?\n([\s\S]*?)```/g;
  let m;
  while ((m = regex.exec(content)) !== null) {
    blocks.push({
      lang: m[1].toLowerCase(),
      code: m[3].replace(/\n$/, ''),
      path: m[2]?.trim() || undefined,
      startIndex: m.index,
      endIndex: m.index + m[0].length,
    });
  }
  return blocks;
}

/** 渲染文本内容，将代码块替换为格式化卡片，文本部分用 Markdown 渲染 */
export function renderContentWithCodeBlocks(
  content: string,
  onCopy: (text: string) => void,
): React.ReactNode {
  const blocks = parseCodeBlocks(content);
  if (blocks.length === 0) {
    // 纯文本：Markdown 渲染
    return <MarkdownContent text={content} />;
  }

  const nodes: React.ReactNode[] = [];
  let lastEnd = 0;

  blocks.forEach((block, i) => {
    // 代码块前的文本 — Markdown 渲染
    if (block.startIndex > lastEnd) {
      const text = content.slice(lastEnd, block.startIndex);
      nodes.push(<MarkdownContent key={`md-${i}`} text={text} />);
    }

    // 代码块 — 自定义卡片
    nodes.push(
      <CodeBlockCard key={`code-${i}`} block={block} onCopy={onCopy} />,
    );

    lastEnd = block.endIndex;
  });

  // 剩余文本 — Markdown 渲染
  if (lastEnd < content.length) {
    nodes.push(
      <MarkdownContent key="md-end" text={content.slice(lastEnd)} />,
    );
  }

  return <>{nodes}</>;
}

/** Markdown 文本渲染器（含表格、标题、列表、粗体等） */
function MarkdownContent({ text }: { text: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        // 表格样式
        table: ({ children }) => (
          <div style={{ overflowX: 'auto', margin: '8px 0' }}>
            <table style={{
              borderCollapse: 'collapse', width: '100%', fontSize: 12,
              border: '1px solid var(--border-subtle)',
            }}>
              {children}
            </table>
          </div>
        ),
        thead: ({ children }) => (
          <thead style={{ background: 'var(--surface-elevated)' }}>{children}</thead>
        ),
        th: ({ children }) => (
          <th style={{
            padding: '6px 10px', textAlign: 'left', fontWeight: 600,
            border: '1px solid var(--border-subtle)', color: 'var(--text-primary)',
            fontSize: 11,
          }}>
            {children}
          </th>
        ),
        td: ({ children }) => (
          <td style={{
            padding: '5px 10px', border: '1px solid var(--border-subtle)',
            color: 'var(--text-secondary)',
          }}>
            {children}
          </td>
        ),
        // 标题样式
        h1: ({ children }) => <h1 style={{ fontSize: 16, fontWeight: 700, margin: '10px 0 6px', color: 'var(--text-primary)' }}>{children}</h1>,
        h2: ({ children }) => <h2 style={{ fontSize: 14, fontWeight: 600, margin: '8px 0 4px', color: 'var(--text-primary)' }}>{children}</h2>,
        h3: ({ children }) => <h3 style={{ fontSize: 13, fontWeight: 600, margin: '6px 0 3px', color: 'var(--text-primary)' }}>{children}</h3>,
        // 列表样式
        ul: ({ children }) => <ul style={{ paddingLeft: 20, margin: '4px 0' }}>{children}</ul>,
        ol: ({ children }) => <ol style={{ paddingLeft: 20, margin: '4px 0' }}>{children}</ol>,
        li: ({ children }) => <li style={{ margin: '2px 0', lineHeight: 1.6 }}>{children}</li>,
        // 代码（内联）
        code: ({ children, className }) => {
          // 判断是否是内联代码（无 lang 前缀）
          const isInline = !className;
          if (isInline) {
            return (
              <code style={{
                background: 'var(--surface-elevated)',
                padding: '1px 5px',
                borderRadius: 3,
                fontSize: 11,
                fontFamily: 'var(--font-mono)',
                color: 'var(--cyan-400)',
              }}>
                {children}
              </code>
            );
          }
          return <code>{children}</code>;
        },
        // 粗体/斜体
        strong: ({ children }) => <strong style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{children}</strong>,
        // 段落
        p: ({ children }) => <p style={{ margin: '4px 0', lineHeight: 1.65 }}>{children}</p>,
        // 水平线
        hr: () => <hr style={{ border: 'none', borderTop: '1px solid var(--border-subtle)', margin: '10px 0' }} />,
        // 引用块
        blockquote: ({ children }) => (
          <blockquote style={{
            borderLeft: '3px solid var(--gold-border)',
            paddingLeft: 10,
            margin: '6px 0',
            color: 'var(--text-muted)',
          }}>
            {children}
          </blockquote>
        ),
      }}
    >
      {text}
    </ReactMarkdown>
  );
}

/** 单个代码块卡片 */
function CodeBlockCard({ block, onCopy }: { block: CodeBlock; onCopy: (t: string) => void }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(block.code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
    onCopy(block.code);
  }, [block.code, onCopy]);

  const langColor = LANG_COLORS[block.lang] || 'var(--text-muted)';
  const displayLang = block.lang === 'sh' ? 'bash' : block.lang;

  return (
    <div style={codeBlockStyle}>
      <div style={headerStyle}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ color: langColor, fontWeight: 600 }}>{displayLang}</span>
          {block.path && (
            <span style={{ color: 'var(--text-dim)' }} title={block.path}>
              📄 {block.path}
            </span>
          )}
        </div>
        <button
          onClick={handleCopy}
          style={{
            background: copied ? 'var(--green-bg)' : 'transparent',
            border: `1px solid ${copied ? 'var(--green-border)' : 'var(--border-subtle)'}`,
            borderRadius: 4,
            padding: '2px 8px',
            cursor: 'pointer',
            fontSize: 10,
            color: copied ? 'var(--green-400)' : 'var(--text-muted)',
            fontFamily: 'var(--font-mono)',
            transition: 'all 0.15s',
          }}
        >
          {copied ? '✓ 已复制' : '📋 复制'}
        </button>
      </div>
      <pre style={{
        margin: 0,
        padding: '12px',
        fontSize: 12,
        lineHeight: 1.5,
        overflowX: 'auto',
        fontFamily: 'var(--font-mono)',
        color: 'var(--text-primary)',
        whiteSpace: 'pre',
        tabSize: 2,
      }}>
        <code>{block.code}</code>
      </pre>
    </div>
  );
}

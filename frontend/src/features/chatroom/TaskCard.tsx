/** 聊天中的任务列表：支持 DAG 树形展示 */
import React, { useState } from 'react';

export interface TaskItem {
  id: string;
  seq: number;
  title: string;
  status: 'pending' | 'claimed' | 'in_progress' | 'done' | 'blocked';
  assigned_agent_name?: string;
  dependencies?: string[];  // 依赖的任务 ID 列表
}

interface TaskCardProps {
  tasks: TaskItem[];
  stats: { total: number; done: number; inProgress: number };
}

const STATUS_ICON: Record<string, string> = {
  pending: '○', claimed: '◐', in_progress: '◉', done: '✓', blocked: '✗',
};
const STATUS_COLOR: Record<string, string> = {
  pending: '#64748b', claimed: '#f59e0b', in_progress: '#3b82f6', done: '#10b981', blocked: '#ef4444',
};
const STATUS_LABEL: Record<string, string> = {
  pending: '等待', claimed: '认领', in_progress: '执行中', done: '完成', blocked: '阻塞',
};

/** 判断是否有 DAG（存在依赖关系） */
function hasDependencies(tasks: TaskItem[]): boolean {
  return tasks.some(t => t.dependencies && t.dependencies.length > 0);
}

/** 构建依赖树：返回顶层任务 + 子任务映射 */
function buildDAGTree(tasks: TaskItem[]): { roots: TaskItem[]; children: Map<string, TaskItem[]> } {
  const children = new Map<string, TaskItem[]>();
  const hasParent = new Set<string>();
  for (const t of tasks) {
    if (t.dependencies) {
      for (const depId of t.dependencies) {
        if (!children.has(depId)) children.set(depId, []);
        children.get(depId)!.push(t);
        hasParent.add(t.id);
      }
    }
  }
  const roots = tasks.filter(t => !hasParent.has(t.id));
  return { roots, children };
}

function TaskRow({ task, depth, children, onToggle }: { task: TaskItem; depth: number; children?: TaskItem[]; onToggle?: (id: string) => void }) {
  const [collapsed, setCollapsed] = useState(false);
  const icon = STATUS_ICON[task.status] || '○';
  const color = STATUS_COLOR[task.status] || '#64748b';
  const isDone = task.status === 'done';
  const hasKids = children && children.length > 0;

  return (
    <>
      <div
        onClick={() => onToggle?.(task.id)}
        style={{
          display: 'flex', alignItems: 'baseline', gap: 6,
          padding: '3px 0', paddingLeft: depth * 20,
          opacity: isDone ? 0.55 : 1,
          transition: 'opacity 0.2s',
          borderLeft: depth > 0 ? '2px solid var(--border-subtle)' : 'none',
          marginLeft: depth > 0 ? 6 : 0,
          cursor: 'pointer', borderRadius: 3,
        }}
        onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(255,255,255,0.03)'}
        onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
        title="点击切换完成状态"
      >
        {hasKids && (
          <span onClick={(e) => { e.stopPropagation(); setCollapsed(!collapsed); }} style={{
            cursor: 'pointer', fontSize: 10, width: 12, flexShrink: 0,
            color: 'var(--text-dim)',
          }}>
            {collapsed ? '▶' : '▼'}
          </span>
        )}
        {!hasKids && depth > 0 && <span style={{ width: 12, flexShrink: 0 }} />}

        <span style={{ color, fontWeight: 600, flexShrink: 0, fontFamily: 'var(--font-mono)', fontSize: 11 }}>
          {task.seq}. {icon}
        </span>

        <span style={{
          flex: 1, fontSize: 12,
          color: isDone ? 'var(--text-dim)' : 'var(--text-primary)',
          textDecoration: isDone ? 'line-through' : 'none',
          fontFamily: 'var(--font-body)',
        }}>
          {task.title}
        </span>

        <span style={{
          fontSize: 9, padding: '1px 4px', borderRadius: 3,
          background: `${color}18`, color, flexShrink: 0,
        }}>
          {STATUS_LABEL[task.status] || task.status}
        </span>

        {task.assigned_agent_name && (
          <span style={{ fontSize: 10, color: 'var(--text-dim)', fontFamily: 'var(--font-body)' }}>
            {task.assigned_agent_name}
          </span>
        )}
      </div>

      {/* 子任务 */}
      {hasKids && !collapsed && children!.map(child => (
        <TaskRow
          key={child.id}
          task={child}
          depth={depth + 1}
          children={childrenMap.get(child.id)}
          onToggle={onToggle}
        />
      ))}
    </>
  );
}

// 模块级变量用于递归（避免 prop drilling 过深）
let childrenMap: Map<string, TaskItem[]> = new Map();
let toggleHandler: ((id: string) => void) | undefined;

export function TaskCard({ tasks, stats, onTaskToggle }: TaskCardProps & { onTaskToggle?: (taskId: string) => void }) {
  const progressPct = stats.total > 0 ? Math.round((stats.done / stats.total) * 100) : 0;
  const isDAG = hasDependencies(tasks);

  toggleHandler = onTaskToggle;

  if (isDAG) {
    const { roots, children } = buildDAGTree(tasks);
    childrenMap = children;

    return (
      <div style={{ fontSize: 12, lineHeight: 1.8 }}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10,
          color: 'var(--text-muted)', fontSize: 11,
        }}>
          <span>📋 任务计划 (DAG)</span>
          <span style={{ fontWeight: 600, color: progressPct === 100 ? '#10b981' : '#f59e0b' }}>
            {stats.done}/{stats.total}
          </span>
          <div style={{ flex: 1, height: 3, borderRadius: 1.5, background: 'var(--bg-elevated)', overflow: 'hidden' }}>
            <div style={{
              height: '100%', width: `${progressPct}%`,
              background: progressPct === 100
                ? 'linear-gradient(90deg, #10b981, #34d399)'
                : 'linear-gradient(90deg, #f59e0b, #fbbf24)',
              borderRadius: 1.5, transition: 'width 0.3s ease',
            }} />
          </div>
        </div>
        {roots.map(root => (
          <TaskRow key={root.id} task={root} depth={0}
            children={children.get(root.id)} onToggle={onTaskToggle} />
        ))}
      </div>
    );
  }

  // 平铺列表模式（无依赖关系）
  return (
    <div style={{ fontSize: 12, lineHeight: 1.8 }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10,
        color: 'var(--text-muted)', fontSize: 11,
      }}>
        <span>📋 任务</span>
        <span style={{ fontWeight: 600, color: progressPct === 100 ? '#10b981' : '#f59e0b' }}>
          {stats.done}/{stats.total}
        </span>
        <div style={{ flex: 1, height: 3, borderRadius: 1.5, background: 'var(--bg-elevated)', overflow: 'hidden' }}>
          <div style={{
            height: '100%', width: `${progressPct}%`,
            background: progressPct === 100
              ? 'linear-gradient(90deg, #10b981, #34d399)'
              : 'linear-gradient(90deg, #f59e0b, #fbbf24)',
            borderRadius: 1.5, transition: 'width 0.3s ease',
          }} />
        </div>
      </div>
      {tasks.map((task) => {
        const icon = STATUS_ICON[task.status] || '○';
        const color = STATUS_COLOR[task.status] || '#64748b';
        const isDone = task.status === 'done';
        return (
          <div key={task.id}
            onClick={() => onTaskToggle?.(task.id)}
            style={{
              display: 'flex', alignItems: 'baseline', gap: 8,
              padding: '2px 0', opacity: isDone ? 0.55 : 1, transition: 'opacity 0.2s',
              cursor: 'pointer', borderRadius: 3,
            }}
            onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(255,255,255,0.03)'}
            onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
            title="点击切换完成状态"
          >
            <span style={{ color, fontWeight: 600, flexShrink: 0, minWidth: 28, fontFamily: 'var(--font-mono)' }}>
              {task.seq}. {icon}
            </span>
            <span style={{
              flex: 1, color: isDone ? 'var(--text-dim)' : 'var(--text-primary)',
              textDecoration: isDone ? 'line-through' : 'none', fontFamily: 'var(--font-body)',
            }}>
              {task.title}
            </span>
            {task.assigned_agent_name && (
              <span style={{ fontSize: 10, color: 'var(--text-dim)', fontFamily: 'var(--font-body)' }}>
                — {task.assigned_agent_name}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}

/** 判断消息是否应该渲染为 TaskCard */
export function isTaskCardMsg(msg: { type?: string }): boolean {
  return msg.type === 'task_card';
}

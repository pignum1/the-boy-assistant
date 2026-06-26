/** useWorkspaceEvents — WebSocket 事件驱动委托树状态

监听编排事件（agent_status、delegation、thinking 等），
将它们转换为 WorkspaceState 的委托树更新。

同时提供 mock 数据生成，便于前端独立调试。
*/
import { useRef, useCallback, useEffect, useState } from 'react';
import type {
  DelegationNode,
  DelegationStatus,
  DelegationRole,
  WorkspaceState,
} from '../../../shared/types/session';

/** 初始空白工作区状态 */
const INITIAL_WORKSPACE: WorkspaceState = {
  active: false,
  completed: false,
  nodes: {},
  rootId: null,
  selectedNodeId: null,
  hitlPending: false,
  hitlData: null,
};

/** 内部辅助：创建委托节点 */
function makeNode(p: {
  id: string; agentName: string; agentEmoji: string; color: string;
  role: DelegationRole; task: string; status: DelegationStatus;
  parentId: string | null;
}): DelegationNode {
  return {
    id: p.id,
    agentName: p.agentName,
    agentEmoji: p.agentEmoji,
    color: p.color,
    role: p.role,
    task: p.task,
    status: p.status,
    parentId: p.parentId,
    childIds: [],
    thinking: null,
    outputs: [],
  };
}

/** 调色板 */
const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#ef4444', '#06b6d4', '#ec4899'];

export function useWorkspaceEvents() {
  const [workspace, setWorkspace] = useState<WorkspaceState>(INITIAL_WORKSPACE);
  const nodesRef = useRef<Record<string, DelegationNode>>({});

  /** 更新单个节点 */
  const updateNode = useCallback((id: string, patch: Partial<DelegationNode>) => {
    nodesRef.current = {
      ...nodesRef.current,
      [id]: { ...nodesRef.current[id], ...patch },
    };
    setWorkspace(prev => ({ ...prev, nodes: { ...nodesRef.current } }));
  }, []);

  /** 设置整个 workspace */
  const setWs = useCallback((patch: Partial<WorkspaceState>) => {
    setWorkspace(prev => {
      const next = { ...prev, ...patch };
      if (patch.nodes) nodesRef.current = patch.nodes;
      return next;
    });
  }, []);

  // ── 监听自定义事件（由 useSessionEvents 分发） ──

  useEffect(() => {
    const handlers: Record<string, (e: Event) => void> = {
      // 编排开始 → 激活工作区，创建顶层主管节点
      'workspace:init': (e) => {
        const d = (e as CustomEvent).detail;
        const nodes: Record<string, DelegationNode> = {};
        const rootId = d.supervisorId || 'supervisor-0';

        // 创建顶层主管
        nodes[rootId] = makeNode({
          id: rootId,
          agentName: d.supervisorName || '架构师-Agent',
          agentEmoji: d.supervisorEmoji || '👑',
          color: COLORS[0],
          role: 'supervisor',
          task: d.task || '分析需求...',
          status: 'analyzing',
          parentId: null,
        });

        // 创建团队成员（idle）
        const members: Array<{ id: string; name: string; emoji: string }> = d.members || [];
        members.forEach((m, i) => {
          nodes[m.id] = makeNode({
            id: m.id,
            agentName: m.name,
            agentEmoji: m.emoji,
            color: COLORS[(i + 1) % COLORS.length],
            role: 'executor',
            task: '',
            status: 'idle',
            parentId: null,
          });
        });

        nodesRef.current = nodes;
        setWorkspace({ ...INITIAL_WORKSPACE, active: true, nodes, rootId });
      },

      // 主管分析完成，展示委托计划
      'workspace:delegation-plan': (e) => {
        const d = (e as CustomEvent).detail;
        const nodes = { ...nodesRef.current };
        const rootId = d.rootId || Object.keys(nodes).find(id => nodes[id].role === 'supervisor') || null;
        if (!rootId || !nodes[rootId]) return;

        // 更新主管节点
        nodes[rootId] = {
          ...nodes[rootId],
          status: 'working',
          task: d.plan || nodes[rootId].task,
          thinking: { summary: '委托计划已生成', elapsed: 0, toolCalls: [] },
        };

        // 创建子节点
        const children: Array<{ id: string; name: string; emoji: string; task: string; role: DelegationRole }> = d.children || [];
        const childIds: string[] = [];
        children.forEach((c, i) => {
          if (nodes[c.id]) {
            // 已有 idle 节点，更新
            nodes[c.id] = {
              ...nodes[c.id],
              role: c.role,
              task: c.task,
              status: 'waiting',
              parentId: rootId,
            };
          } else {
            nodes[c.id] = makeNode({
              id: c.id,
              agentName: c.name,
              agentEmoji: c.emoji,
              color: COLORS[(i + 1) % COLORS.length],
              role: c.role,
              task: c.task,
              status: 'waiting',
              parentId: rootId,
            });
          }
          childIds.push(c.id);
        });

        nodes[rootId] = { ...nodes[rootId], childIds };
        nodesRef.current = nodes;
        setWorkspace(prev => ({ ...prev, nodes: { ...nodes }, hitlPending: !!d.hitl, hitlData: d.hitlData || null }));
      },

      // HITL 确认后开始执行
      'workspace:confirm': () => {
        const nodes = { ...nodesRef.current };
        // 所有 waiting 节点开始工作
        Object.keys(nodes).forEach(id => {
          if (nodes[id].status === 'waiting') {
            nodes[id] = { ...nodes[id], status: 'working' };
          }
        });
        nodesRef.current = nodes;
        setWorkspace(prev => ({ ...prev, nodes: { ...nodes }, hitlPending: false }));
      },

      // Agent 状态变更
      'workspace:agent-status': (e) => {
        const d = (e as CustomEvent).detail;
        if (!nodesRef.current[d.agentId]) return;
        updateNode(d.agentId, { status: d.status as DelegationStatus });
      },

      // Agent 实时思考
      'workspace:agent-thinking': (e) => {
        const d = (e as CustomEvent).detail;
        if (!nodesRef.current[d.agentId]) return;
        updateNode(d.agentId, {
          thinking: {
            summary: d.summary || '',
            model: d.model,
            elapsed: d.elapsed || 0,
            toolCalls: d.toolCalls || [],
          },
        });
      },

      // Agent 完成
      'workspace:agent-done': (e) => {
        const d = (e as CustomEvent).detail;
        if (!nodesRef.current[d.agentId]) return;
        updateNode(d.agentId, {
          status: 'done',
          duration: d.duration,
          outputs: d.outputs || [],
          thinking: null,
        });
      },

      // 子主管进一步委托
      'workspace:sub-delegation': (e) => {
        const d = (e as CustomEvent).detail;
        const nodes = { ...nodesRef.current };
        const parentId = d.parentId;
        if (!parentId || !nodes[parentId]) return;

        // 标记为子主管
        nodes[parentId] = { ...nodes[parentId], role: 'sub_supervisor' };

        const childIds = [...(nodes[parentId].childIds || [])];
        const children: Array<{ id: string; name: string; emoji: string; task: string }> = d.children || [];

        children.forEach((c, i) => {
          if (nodes[c.id]) {
            nodes[c.id] = {
              ...nodes[c.id],
              role: 'executor',
              task: c.task,
              status: 'waiting',
              parentId,
            };
          } else {
            nodes[c.id] = makeNode({
              id: c.id,
              agentName: c.name,
              agentEmoji: c.emoji,
              color: COLORS[(i + 3) % COLORS.length],
              role: 'executor',
              task: c.task,
              status: 'waiting',
              parentId,
            });
          }
          childIds.push(c.id);
        });

        nodes[parentId] = { ...nodes[parentId], childIds };
        nodesRef.current = nodes;
        setWorkspace(prev => ({ ...prev, nodes: { ...nodes } }));
      },

      // 全部完成
      'workspace:complete': (e) => {
        const d = (e as CustomEvent).detail;
        const nodes = { ...nodesRef.current };
        // 标记所有 working/waiting 为 done
        Object.keys(nodes).forEach(id => {
          if (nodes[id].status === 'working' || nodes[id].status === 'analyzing') {
            nodes[id] = { ...nodes[id], status: 'done' };
          }
        });
        nodesRef.current = nodes;
        setWorkspace(prev => ({
          ...prev,
          nodes: { ...nodes },
          completed: true,
          completionSummary: d?.summary,
        }));
      },
    };

    Object.entries(handlers).forEach(([name, handler]) => {
      window.addEventListener(name, handler);
    });
    return () => {
      Object.entries(handlers).forEach(([name, handler]) => {
        window.removeEventListener(name, handler);
      });
    };
  }, [updateNode]);

  // ── 选中节点 ──
  const selectNode = useCallback((id: string | null) => {
    setWorkspace(prev => ({ ...prev, selectedNodeId: id }));
  }, []);

  // ── Mock 数据生成（用于前端独立调试） ──
  const loadMockData = useCallback(() => {
    const nodes: Record<string, DelegationNode> = {};

    // 顶层主管
    nodes['arch-0'] = makeNode({
      id: 'arch-0', agentName: '架构师-Agent', agentEmoji: '👑',
      color: '#f59e0b', role: 'supervisor', task: '分析需求并设计整体方案',
      status: 'done', parentId: null,
    });
    nodes['arch-0'].duration = 28;
    nodes['arch-0'].outputs = [{ name: 'schema.sql', size: '1.2KB', type: 'file' }];
    nodes['arch-0'].childIds = ['be-1', 'test-2'];

    // 后端工程师（子主管）
    nodes['be-1'] = makeNode({
      id: 'be-1', agentName: '后端工程师', agentEmoji: '💻',
      color: '#3b82f6', role: 'sub_supervisor', task: '实现 REST API',
      status: 'done', parentId: 'arch-0',
    });
    nodes['be-1'].duration = 95;
    nodes['be-1'].outputs = [{ name: 'register.ts', size: '3.8KB', type: 'file' }];
    nodes['be-1'].childIds = ['fe-3'];

    // 测试员
    nodes['test-2'] = makeNode({
      id: 'test-2', agentName: '测试员', agentEmoji: '🧪',
      color: '#10b981', role: 'executor', task: '接口验证',
      status: 'done', parentId: 'arch-0',
    });
    nodes['test-2'].duration = 42;
    nodes['test-2'].outputs = [{ name: 'validation-report.md', size: '0.8KB', type: 'file' }];

    // 前端工程师（第二层委托）
    nodes['fe-3'] = makeNode({
      id: 'fe-3', agentName: '前端工程师', agentEmoji: '🎨',
      color: '#8b5cf6', role: 'executor', task: '对接 API 页面开发',
      status: 'working', parentId: 'be-1',
    });
    nodes['fe-3'].thinking = {
      summary: '正在对接注册/登录 API...\n已完成注册表单组件',
      model: 'glm-5.1',
      elapsed: 32,
      toolCalls: [
        { tool: 'file-ops.write', status: 'done', detail: 'RegisterForm.tsx' },
        { tool: 'file-ops.read', status: 'running', detail: 'api-spec.md' },
      ],
    };

    nodesRef.current = nodes;
    setWorkspace({
      active: true,
      completed: false,
      nodes,
      rootId: 'arch-0',
      selectedNodeId: null,
      hitlPending: false,
      hitlData: null,
    });
  }, []);

  return { workspace, selectNode, loadMockData };
}

import dagre from 'dagre';
import type { Node, Edge } from '@xyflow/react';

/** 节点尺寸映射 */
const NODE_SIZES: Record<string, { w: number; h: number }> = {
  start:          { w: 120, h: 40 },
  end:            { w: 120, h: 40 },
  agent_action:   { w: 180, h: 64 },
  hitl:           { w: 180, h: 64 },
  validation:     { w: 160, h: 50 },
  condition:      { w: 120, h: 80 },
};

/**
 * 分层自动布局
 *
 * 核心策略：
 * 1. 只用 forward 边（和无条件边）计算 dagre 层级 → 保证主流程纵向整齐
 * 2. reject/escalate 回环边不参与布局 → 由自定义边组件用 bezier + 偏移绕行
 * 3. 同层节点横向均匀分布
 */
export function autoLayout(nodes: Node[], edges: Edge[]): Node[] {
  if (nodes.length === 0) return nodes;

  // 区分主流程边和回环边
  const mainEdges = edges.filter((e) => {
    const t = (e.data as { edgeType?: string })?.edgeType || e.type;
    return t !== 'reject' && t !== 'escalate';
  });

  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({
    rankdir: 'TB',
    nodesep: 70,
    ranksep: 90,
    marginx: 60,
    marginy: 60,
    align: 'UL',         // 同层节点左对齐，更整齐
  });

  for (const node of nodes) {
    const size = NODE_SIZES[node.type || ''] || { w: 180, h: 60 };
    g.setNode(node.id, { width: size.w, height: size.h });
  }

  // 只用主流程边布局（避免回环边导致层级错乱）
  for (const edge of mainEdges) {
    g.setEdge(edge.source, edge.target, { weight: 1 });
  }

  // 孤立节点也要添加
  for (const node of nodes) {
    try {
      g.node(node.id);
    } catch {
      g.setNode(node.id, { width: 180, height: 60 });
    }
  }

  dagre.layout(g);

  return nodes.map((node) => {
    const pos = g.node(node.id);
    if (!pos) return node;
    const size = NODE_SIZES[node.type || ''] || { w: 180, h: 60 };
    return {
      ...node,
      position: { x: pos.x - size.w / 2, y: pos.y - size.h / 2 },
    };
  });
}

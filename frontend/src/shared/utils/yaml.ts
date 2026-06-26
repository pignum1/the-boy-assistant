import yaml from 'js-yaml';
import type { SOPNode, SOPEdge, SOPDefinition } from '../types/sop';

/** SOP Definition → YAML 字符串 */
export function sopToYaml(sop: SOPDefinition): string {
  const obj = {
    name: sop.name,
    description: sop.description || '',
    version: sop.version || '1.0',
    nodes: sop.nodes.map(({ id, type, ...rest }) => ({ id, type, ...rest })),
    edges: sop.edges.map(({ from, to, condition }) =>
      condition ? { from, to, condition } : { from, to }
    ),
  };
  return yaml.dump(obj, { indent: 2, lineWidth: 120 });
}

/** YAML 字符串 → SOP Definition */
export function yamlToSop(yamlStr: string): SOPDefinition {
  const parsed = yaml.load(yamlStr) as Record<string, unknown>;
  return {
    name: (parsed.name as string) || 'Untitled',
    description: (parsed.description as string) || '',
    version: (parsed.version as string) || '1.0',
    nodes: (parsed.nodes as SOPNode[]) || [],
    edges: (parsed.edges as SOPEdge[]) || [],
  };
}

/** 检查 nodes/edges 格式有效性 */
export function validateSopData(data: unknown): string[] {
  const errors: string[] = [];
  if (!data || typeof data !== 'object') {
    errors.push('Invalid data format');
    return errors;
  }
  const d = data as Record<string, unknown>;
  if (!Array.isArray(d.nodes) || d.nodes.length === 0) {
    errors.push('Nodes array is empty');
  }
  if (!Array.isArray(d.edges)) {
    errors.push('Edges must be an array');
  }
  const nodeIds = new Set((d.nodes as SOPNode[]).map((n) => n.id));
  for (const e of (d.edges as SOPEdge[])) {
    if (!nodeIds.has(e.from)) errors.push(`Edge references unknown node: ${e.from}`);
    if (!nodeIds.has(e.to)) errors.push(`Edge references unknown node: ${e.to}`);
  }
  // 孤立节点检测
  const connectedNodes = new Set<string>();
  for (const e of (d.edges as SOPEdge[])) {
    connectedNodes.add(e.from);
    connectedNodes.add(e.to);
  }
  for (const n of (d.nodes as SOPNode[])) {
    if ((d.nodes as SOPNode[]).length > 1 && !connectedNodes.has(n.id) && n.type !== 'start') {
      errors.push(`Orphan node: ${n.id}`);
    }
  }
  return errors;
}

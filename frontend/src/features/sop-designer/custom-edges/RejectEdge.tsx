import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  type EdgeProps,
  type InternalNode,
  useInternalNode,
} from '@xyflow/react';

/**
 * Reject 边（打回）
 *
 * 关键设计：
 * - 如果目标是上方的节点（回环），从 source 的 Left/Right Handle 绕到节点外侧
 * - 偏移量根据回跳的层级数动态计算，层级越多绕得越远
 * - 虚线 + 红色
 */
export function RejectEdge({
  id,
  source,
  target,
  sourceX,
  sourceY,
  targetX,
  targetY,
  data,
  selected,
}: EdgeProps) {
  const sourceNode = useInternalNode(source);
  const targetNode = useInternalNode(target);
  const label = (data as { label?: string })?.label;

  const isBackEdge = sourceY >= targetY;

  let path: string;
  let labelX: number;
  let labelY: number;

  if (isBackEdge && sourceNode && targetNode) {
    // 回环边：从 source 左侧出发，绕到画布外侧，回到 target 左侧
    const srcBounds = getNodeBounds(sourceNode);
    const tgtBounds = getNodeBounds(targetNode);

    // 跳了多少层 → 决定偏移距离
    const layerGap = Math.abs(sourceY - targetY);
    const offset = Math.max(60, layerGap * 0.4);

    // 起点：source 左侧中点
    const sx = srcBounds.left - 4;
    const sy = srcBounds.centerY;

    // 终点：target 左侧中点
    const tx = tgtBounds.left - 4;
    const ty = tgtBounds.centerY;

    // 控制点：向左偏移 (orthogonal routing)
    const cx = Math.min(sx, tx) - offset;
    const r = 12; // corner radius

    // Orthogonal path with rounded corners
    path = [
      `M ${sx} ${sy}`,
      `L ${cx + r} ${sy}`,
      `Q ${cx} ${sy} ${cx} ${sy + (ty > sy ? r : -r)}`,
      `L ${cx} ${ty + (ty > sy ? -r : r)}`,
      `Q ${cx} ${ty} ${cx + r} ${ty}`,
      `L ${tx} ${ty}`,
    ].join(' ');
    labelX = cx - 10;
    labelY = (sy + ty) / 2;
  } else {
    // 非回环的 reject 边（少见）：正常 bezier
    [path, labelX, labelY] = getBezierPath({
      sourceX, sourceY, targetX, targetY,
      sourcePosition: isBackEdge ? 'left' as const : undefined,
      targetPosition: isBackEdge ? 'left' as const : undefined,
    });
  }

  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        style={{
          stroke: selected ? 'var(--red-400)' : 'rgba(239,68,68,0.45)',
          strokeWidth: selected ? 2 : 1.5,
          strokeDasharray: '5 3',
        }}
      />
      {label && (
        <EdgeLabelRenderer>
          <div style={{
            ...labelBaseStyle,
            transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
            color: 'var(--red-400)',
            background: 'rgba(239,68,68,0.08)',
            borderColor: 'rgba(239,68,68,0.25)',
          }}>
            {label}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}

const labelBaseStyle: React.CSSProperties = {
  position: 'absolute',
  fontSize: 9,
  fontWeight: 600,
  padding: '2px 7px',
  borderRadius: 4,
  border: '1px solid',
  pointerEvents: 'all',
  whiteSpace: 'nowrap',
};

function getNodeBounds(node: InternalNode) {
  const w = (node.measured?.width || node.width || 180);
  const h = (node.measured?.height || node.height || 60);
  return {
    left: node.internals.positionAbsolute.x,
    right: node.internals.positionAbsolute.x + w,
    top: node.internals.positionAbsolute.y,
    bottom: node.internals.positionAbsolute.y + h,
    width: w,
    height: h,
    centerX: node.internals.positionAbsolute.x + w / 2,
    centerY: node.internals.positionAbsolute.y + h / 2,
  };
}

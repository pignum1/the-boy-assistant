import {
  BaseEdge,
  EdgeLabelRenderer,
  type EdgeProps,
  type InternalNode,
  useInternalNode,
} from '@xyflow/react';

/**
 * Escalate 边（升级）
 *
 * 与 Reject 边类似，但从右侧绕行，避免重叠。
 * 实线 + 橙色。
 */
export function EscalateEdge({
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
    const srcBounds = getNodeBounds(sourceNode);
    const tgtBounds = getNodeBounds(targetNode);

    const layerGap = Math.abs(sourceY - targetY);
    const offset = Math.max(60, layerGap * 0.4);

    // 从 source 右侧出发，绕到画布右侧，回到 target 右侧
    const sx = srcBounds.right + 4;
    const sy = srcBounds.centerY;

    const tx = tgtBounds.right + 4;
    const ty = tgtBounds.centerY;

    const cx = Math.max(sx, tx) + offset;
    const r = 12; // corner radius

    // Orthogonal path with rounded corners (mirror of reject's left side)
    path = [
      `M ${sx} ${sy}`,
      `L ${cx - r} ${sy}`,
      `Q ${cx} ${sy} ${cx} ${sy + (ty > sy ? r : -r)}`,
      `L ${cx} ${ty + (ty > sy ? -r : r)}`,
      `Q ${cx} ${ty} ${cx - r} ${ty}`,
      `L ${tx} ${ty}`,
    ].join(' ');
    labelX = cx + 10;
    labelY = (sy + ty) / 2;
  } else {
    // 非回环：直线 bezier
    const midX = (sourceX + targetX) / 2;
    const midY = (sourceY + targetY) / 2;
    const cx = midX + 30;
    const cy = midY;
    path = `M ${sourceX} ${sourceY} Q ${cx} ${cy} ${targetX} ${targetY}`;
    labelX = cx;
    labelY = cy;
  }

  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        style={{
          stroke: selected ? 'var(--amber-400)' : 'rgba(245,158,11,0.5)',
          strokeWidth: selected ? 2.5 : 1.5,
        }}
      />
      {label && (
        <EdgeLabelRenderer>
          <div style={{
            ...labelBaseStyle,
            transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
            color: 'var(--amber-400)',
            background: 'rgba(245,158,11,0.08)',
            borderColor: 'rgba(245,158,11,0.25)',
            fontWeight: 700,
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

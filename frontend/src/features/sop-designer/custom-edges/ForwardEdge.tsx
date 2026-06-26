import { BaseEdge, EdgeLabelRenderer, getSmoothStepPath, type EdgeProps } from '@xyflow/react';

export function ForwardEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  selected,
}: EdgeProps) {
  const [edgePath, labelX, labelY] = getSmoothStepPath({
    sourceX, sourceY, targetX, targetY,
    sourcePosition, targetPosition,
    borderRadius: 8,
  });

  const label = (data as { label?: string })?.label;

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        style={{
          stroke: selected ? 'var(--green-400)' : 'rgba(52,211,153,0.45)',
          strokeWidth: selected ? 2 : 1.5,
        }}
      />
      {label && (
        <EdgeLabelRenderer>
          <div style={{
            ...labelBaseStyle,
            transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
            color: 'var(--green-400)',
            background: 'rgba(52,211,153,0.06)',
            borderColor: 'rgba(52,211,153,0.2)',
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

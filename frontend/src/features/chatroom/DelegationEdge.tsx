/** DelegationEdge — xyflow 自定义边，展示委托关系

- 实线：已委托（父节点工作中/完成）
- 虚线：等待中（父节点还没到这一步）
- 标注：任务描述 + 子主管标签
*/
import { memo } from 'react';
import { BaseEdge, EdgeLabelRenderer, getBezierPath, type EdgeProps } from '@xyflow/react';

interface DelegationEdgeData {
  task: string;
  isPending: boolean;
  isSubSupervisor: boolean;
}

function DelegationEdgeRaw({
  id, sourceX, sourceY, targetX, targetY,
  sourcePosition, targetPosition, data,
}: EdgeProps & { data: DelegationEdgeData }) {
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX, sourceY, targetX, targetY,
    sourcePosition, targetPosition,
  });

  const isPending = data?.isPending ?? false;
  const isSubSupervisor = data?.isSubSupervisor ?? false;
  const task = data?.task ?? '';

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        style={{
          stroke: isPending ? '#334155' : '#3b82f6',
          strokeWidth: isPending ? 1 : 2,
          strokeDasharray: isPending ? '6 4' : 'none',
          animation: isPending ? 'none' : 'none',
        }}
      />
      {/* 边标签：任务描述 */}
      {task && (
        <EdgeLabelRenderer>
          <div
            style={{
              position: 'absolute',
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
              fontSize: 9,
              background: '#0a0f1e',
              padding: '2px 8px',
              borderRadius: 4,
              border: `1px solid ${isPending ? '#1e293b' : '#3b82f644'}`,
              color: isPending ? '#475569' : '#94a3b8',
              whiteSpace: 'nowrap',
              pointerEvents: 'all',
            }}
            className="nodrag nopan"
          >
            {isSubSupervisor && (
              <span style={{ color: '#8b5cf6', fontWeight: 600, marginRight: 4 }}>子主管</span>
            )}
            {task}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}

export const DelegationEdge = memo(DelegationEdgeRaw);

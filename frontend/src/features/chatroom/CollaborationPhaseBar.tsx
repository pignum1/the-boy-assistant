/** Dynamic phase progress bar — phases are determined by Supervisor LLM at runtime */
import type { PhaseInfo } from '../../shared/types/collaboration';

interface Props {
  phases: PhaseInfo[];
  currentPhase: number; // -1 = not started, 0..n-1 = in progress, n = all done
}

export function CollaborationPhaseBar({ phases, currentPhase }: Props) {
  if (phases.length === 0) return null;

  return (
    <div style={containerStyle}>
      {phases.map((phase, i) => (
        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 0 }}>
          <div
            style={{
              ...itemStyle,
              opacity: i === currentPhase ? 1 : i < currentPhase ? 0.55 : 0.2,
            }}
          >
            <div
              style={{
                ...dotStyle,
                borderColor:
                  i < currentPhase
                    ? 'var(--green-400)'
                    : i === currentPhase
                      ? 'var(--gold-400)'
                      : '#1e293b',
                background:
                  i < currentPhase
                    ? 'rgba(16,185,129,0.1)'
                    : i === currentPhase
                      ? 'rgba(245,158,11,0.1)'
                      : 'transparent',
                color:
                  i < currentPhase
                    ? 'var(--green-400)'
                    : i === currentPhase
                      ? 'var(--gold-400)'
                      : '#475569',
              }}
            >
              {i < currentPhase ? '✓' : i + 1}
            </div>
            <span style={{ fontSize: 9 }}>{phase.name}</span>
            {phase.role && (
              <span style={{ fontSize: 7, color: '#475569', marginLeft: 2 }}>
                ({phase.role})
              </span>
            )}
          </div>
          {i < phases.length - 1 && (
            <div
              style={{
                ...connectorStyle,
                background:
                  i < currentPhase ? 'rgba(16,185,129,0.2)' : '#1e293b',
              }}
            />
          )}
        </div>
      ))}
    </div>
  );
}

const containerStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  padding: '6px 14px',
  background: '#0a0f1e',
  borderBottom: '1px solid rgba(148,163,184,0.04)',
  gap: 0,
  overflowX: 'auto',
  minHeight: 28,
};

const itemStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 3,
  whiteSpace: 'nowrap',
  transition: 'opacity 0.4s',
};

const dotStyle: React.CSSProperties = {
  width: 14,
  height: 14,
  borderRadius: '50%',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  fontSize: 8,
  border: '1.5px solid',
  flexShrink: 0,
  fontWeight: 700,
};

const connectorStyle: React.CSSProperties = {
  width: 16,
  height: 1,
  margin: '0 2px',
  flexShrink: 0,
};

/** HITL interaction cards — clarification, confirmation, agent invite, review */
import type { HitlRequest, HitlOption } from '../../shared/types/collaboration';
import { HITLOptions } from './components/shared/HITLOptions';

interface Props {
  request: HitlRequest;
  onRespond: (value: string) => void;
}

export function HITLInteractionCard({ request, onRespond }: Props) {
  const color = getCardColor(request.type);

  return (
    <div style={containerStyle(color)}>
      <h4 style={titleStyle(color)}>{getTitle(request.type)}</h4>
      {request.message && (
        <div
          style={messageStyle}
          dangerouslySetInnerHTML={{
            __html: request.message
              .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
              .replace(/\n/g, '<br>')
          }}
        />
      )}
      <HITLOptions
        mode="interactive"
        options={request.options.map((opt: HitlOption) => ({
          label: opt.label,
          value: opt.value,
          description: (opt as any).description,
        }))}
        onSelect={onRespond}
      />
    </div>
  );
}

function getTitle(type: string): string {
  switch (type) {
    case 'clarification':
      return '🤔 需要确认以下信息';
    case 'confirmation':
      return '✅ 请确认';
    case 'agent_invite':
      return '⚠️ 缺少 Agent';
    case 'review':
      return '🔍 审核结果';
    default:
      return '确认';
  }
}

function getCardColor(type: string): string {
  switch (type) {
    case 'clarification':
      return '#f59e0b';
    case 'confirmation':
      return '#10b981';
    case 'agent_invite':
      return '#a78bfa';
    case 'review':
      return '#60a5fa';
    default:
      return '#f59e0b';
  }
}

function containerStyle(color: string): React.CSSProperties {
  return {
    borderRadius: 6,
    padding: '10px 14px',
    margin: '6px 0',
    background: `${color}08`,
    border: `1px solid ${color}22`,
  };
}

function titleStyle(color: string): React.CSSProperties {
  return {
    fontSize: 12,
    color,
    marginBottom: 6,
    fontWeight: 600,
  };
}

const messageStyle: React.CSSProperties = {
  fontSize: 11,
  color: '#94a3b8',
  lineHeight: 1.6,
  marginBottom: 8,
};

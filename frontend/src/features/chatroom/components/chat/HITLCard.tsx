/** HITL 状态机卡片：pending / answering / answered
 *
 * 关键行为：
 * - 「我来回答」按钮 → 不发任何消息，仅切到 answering，让输入框拿焦
 * - 「✅ 直接确认」/「❌ 取消」按钮 → 立即 hitl_resume("确认"/"取消")
 * - answering 时输入框接管，输入文本 + Enter → hitl_resume(text)
 * - answered 时卡片定格历史，显示 Q + A + 原选项（只读回看）
 */
import type { HitlCardItem } from '../../types/state';
import { HITLOptions } from '../shared/HITLOptions';

interface Props {
  item: HitlCardItem;
  /** 用户点了主操作按钮（approve / reject / skip / 等普通 value） */
  onPrimaryAction: (value: string) => void;
  /** 用户点了「我来回答」/「修改」 → 进入 answering 模式 */
  onEnterAnswering: () => void;
}

const TITLES: Record<HitlCardItem['hitlKind'], string> = {
  clarification: '🤔 需要确认信息',
  confirmation:  '✅ 请确认',
  agent_invite:  '⚠️ 缺少 Agent',
  review:        '🔍 审核结果',
  delta_plan:    '🔄 介入修改方案',
};

const COLOR: Record<HitlCardItem['hitlKind'], string> = {
  clarification: 'var(--gold-400)',
  confirmation:  'var(--green-400)',
  agent_invite:  'var(--purple-400)',
  review:        'var(--blue-400)',
  delta_plan:    'var(--gold-400)',
};

const BG: Record<HitlCardItem['hitlKind'], string> = {
  clarification: 'var(--gold-bg)',
  confirmation:  'var(--green-bg)',
  agent_invite:  'var(--purple-bg)',
  review:        'var(--blue-bg)',
  delta_plan:    'var(--gold-bg)',
};

const BORDER: Record<HitlCardItem['hitlKind'], string> = {
  clarification: 'var(--gold-border)',
  confirmation:  'var(--green-border)',
  agent_invite:  'var(--purple-border)',
  review:        'var(--blue-border)',
  delta_plan:    'var(--gold-border)',
};

/** 自由输入型选项的值 → 点击后进入 answering 模式，发消息前可输入反馈 */
const ANSWER_ENTRY_VALUES = ['answer', 'modify', 'edit', 'reject', 'reject_all'];

export function HITLCard({ item, onPrimaryAction, onEnterAnswering }: Props) {
  const color = COLOR[item.hitlKind];
  const bg = BG[item.hitlKind];
  const border = BORDER[item.hitlKind];

  // 确保 options 至少有一个 fallback
  const options = item.options && item.options.length > 0
    ? item.options
    : [{ label: '💬 自由输入', value: 'answer', description: '输入你的想法' }];

  return (
    <div
      data-hitl-card={item.hitlId}
      data-message-id={item.id}
      style={{
        margin: '10px 0',
        padding: '12px 14px',
        background: bg,
        border: `1px solid ${border}`,
        borderRadius: 8,
      }}
    >
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        marginBottom: 8,
      }}>
        <span style={{
          fontSize: 12,
          fontWeight: 600,
          color: item.cardState === 'answered'
            ? (item.selectedValue === 'approve' ? 'var(--green-500)' :
               item.selectedValue === 'reject' ? '#ef4444' :
               item.selectedValue === 'skip' || item.selectedValue === 'cancel' || item.selectedValue === 'abort' ? 'var(--text-muted)' :
               color)
            : color,
        }}>
          {item.cardState === 'answered'
            ? (item.selectedValue === 'approve' ? '✅ 已通过' :
               item.selectedValue === 'reject' ? '❌ 已打回' :
               item.selectedValue === 'skip' || item.selectedValue === 'cancel' ? '⏹ 已取消' :
               item.selectedValue === 'abort' ? '⏹ 已终止' :
               '📝 已回复')
            : (TITLES[item.hitlKind] ?? '确认')}
        </span>
        <StateBadge state={item.cardState} color={color} />
      </div>

      {/* 问题 / 内容 */}
      <div
        style={{
          fontSize: 12,
          color: 'var(--text-secondary)',
          lineHeight: 1.65,
          marginBottom: item.cardState === 'answered' ? 6 : 10,
          whiteSpace: 'pre-wrap',
        }}
        dangerouslySetInnerHTML={{ __html: renderMessage(item.message) }}
      />

      {/* delta_plan 专属：展示 keep/modify/add/cancel 摘要 */}
      {item.deltaPlan && item.cardState !== 'answered' && (
        <DeltaPlanSummary plan={item.deltaPlan} />
      )}

      {/* ── 选项区域 ── */}

      {/* pending 态：可点击按钮 */}
      {item.cardState === 'pending' && (
        <div style={{ marginTop: 4 }}>
          <HITLOptions
            mode="interactive"
            options={options}
            onSelect={(value) => onPrimaryAction(value)}
            answerEntryValues={ANSWER_ENTRY_VALUES}
            onAnswerEntry={onEnterAnswering}
          />
        </div>
      )}

      {/* answered 态：只读回看原选项 + 高亮用户选择 */}
      {item.cardState === 'answered' && (
        <div style={{ marginTop: 6 }}>
          <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 4, fontFamily: 'var(--font-mono)' }}>
            可选方案
          </div>
          <HITLOptions
            mode="readonly"
            options={options}
            selectedValue={item.answer ? findOptionValueByLabel(options, item.answer) : undefined}
          />
        </div>
      )}

      {/* answering 态：提示用户去输入框 */}
      {item.cardState === 'answering' && (
        <div style={{
          marginTop: 6,
          fontSize: 11,
          color,
          fontFamily: 'var(--font-mono)',
        }}>
          💬 请在下方输入框作答，按 Enter 发送
        </div>
      )}

      {/* answered 态：显示用户的回答 */}
      {item.cardState === 'answered' && item.answer && (
        <div style={{
          marginTop: 8,
          padding: '6px 10px',
          background: 'rgba(148,163,184,0.06)',
          borderLeft: `2px solid ${color}`,
          borderRadius: 3,
          fontSize: 12,
          color: 'var(--text-primary)',
          lineHeight: 1.6,
          whiteSpace: 'pre-wrap',
        }}>
          <span style={{ color: 'var(--text-muted)', marginRight: 6 }}>你的回答:</span>
          {item.answer}
        </div>
      )}
    </div>
  );
}

function StateBadge({ state, color }: { state: 'pending' | 'answering' | 'answered'; color: string }) {
  const label = state === 'pending' ? 'pending' : state === 'answering' ? 'answering' : 'answered';
  return (
    <span style={{
      fontSize: 10,
      padding: '1px 6px',
      borderRadius: 3,
      color,
      border: `1px solid ${color}33`,
      background: `${color}11`,
      fontFamily: 'var(--font-mono)',
    }}>
      {label}
    </span>
  );
}

function DeltaPlanSummary({ plan }: { plan: NonNullable<HitlCardItem['deltaPlan']> }) {
  return (
    <div style={{
      display: 'flex',
      gap: 8,
      flexWrap: 'wrap',
      marginBottom: 10,
      fontSize: 11,
      fontFamily: 'var(--font-mono)',
    }}>
      {plan.keep.length > 0 && (
        <span style={{ color: 'var(--green-400)' }}>✓ 保留 {plan.keep.length}</span>
      )}
      {plan.modify.length > 0 && (
        <span style={{ color: 'var(--gold-400)' }}>🔄 重做 {plan.modify.length}</span>
      )}
      {plan.add.length > 0 && (
        <span style={{ color: 'var(--cyan-400)' }}>🆕 新增 {plan.add.length}</span>
      )}
      {plan.cancel.length > 0 && (
        <span style={{ color: 'var(--red-400)' }}>❌ 取消 {plan.cancel.length}</span>
      )}
    </div>
  );
}

/** 简单 markdown-ish 渲染（**bold** + 换行） */
function renderMessage(text: string): string {
  const safe = typeof text === 'string' ? text : String(text || '');
  return safe
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>');
}

/** 根据用户回答文本反查匹配的 option value（用于高亮选中项） */
function findOptionValueByLabel(
  options: Array<{ label: string; value: string }>,
  answer: string,
): string | undefined {
  // 精确匹配 label
  const exact = options.find(o => o.label === answer || o.label.replace(/^[^\s]+\s*/, '') === answer);
  if (exact) return exact.value;
  // 模糊匹配：answer 包含 label 的核心文本
  for (const o of options) {
    const core = o.label.replace(/^[^\w]*\s*/, ''); // 去掉 emoji 前缀
    if (core && answer.includes(core)) return o.value;
  }
  return undefined;
}

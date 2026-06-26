/** HITL 选项按钮公共组件
 *
 * 三模式（Swarm / Supervisor / LangGraph）共用。避免多处重复 option → button 的渲染逻辑。
 *
 * 五种模式：
 * - interactive:  可点击按钮（pending 态，Swarm select / Supervisor confirmation / ChatRoomView HITL）
 *                 → 支持 selectedValue 实现 Supervisor 的"选中高亮 + 其他变暗"效果
 * - readonly:     只读标签（answered 后回看）
 * - selectable:   单选列表（choice 类型卡片，可描述文本）
 * - multiSelect:  多选复选框 + 确认按钮（Swarm multi_select）
 * - answerInput:  文本输入 + 发送（Swarm answer 类型）
 *
 * 语义色映射统一管理：approve=绿, reject/取消=红, modify/编辑=黄, answer=蓝, invite=紫
 */

import { useState } from 'react';
import type { HitlOption } from '../../types/state';

// ═══════════════════════════════════════════
// 语义色映射
// ═══════════════════════════════════════════

const SEMANTIC_COLORS: Record<string, { bg: string; border: string; text: string }> = {
  approve:       { bg: 'rgba(16,185,129,0.08)',  border: 'rgba(16,185,129,0.25)',  text: '#10b981' },
  force_confirm: { bg: 'rgba(16,185,129,0.08)',  border: 'rgba(16,185,129,0.25)',  text: '#10b981' },
  confirm:       { bg: 'rgba(16,185,129,0.08)',  border: 'rgba(16,185,129,0.25)',  text: '#10b981' },
  reject:        { bg: 'rgba(239,68,68,0.08)',   border: 'rgba(239,68,68,0.25)',   text: '#ef4444' },
  cancel:        { bg: 'rgba(239,68,68,0.08)',   border: 'rgba(239,68,68,0.25)',   text: '#ef4444' },
  skip:          { bg: 'rgba(239,68,68,0.08)',   border: 'rgba(239,68,68,0.25)',   text: '#ef4444' },
  modify:        { bg: 'rgba(245,158,11,0.08)',  border: 'rgba(245,158,11,0.25)',  text: '#f59e0b' },
  edit:          { bg: 'rgba(245,158,11,0.08)',  border: 'rgba(245,158,11,0.25)',  text: '#f59e0b' },
  answer:        { bg: 'rgba(59,130,246,0.08)',  border: 'rgba(59,130,246,0.25)',  text: '#3b82f6' },
  invite:        { bg: 'rgba(168,85,247,0.08)',  border: 'rgba(168,85,247,0.25)',  text: '#a855f7' },
};

const DEFAULT_COLOR = { bg: 'transparent', border: 'var(--border-subtle)', text: 'var(--text-secondary)' };

function getColor(value: string) {
  return SEMANTIC_COLORS[value] || DEFAULT_COLOR;
}

// ═══════════════════════════════════════════
// Props 类型（判别联合）
// ═══════════════════════════════════════════

interface InteractiveProps {
  mode: 'interactive';
  options: HitlOption[];
  onSelect: (value: string) => void;
  /** 进入自由输入模式的值列表（如 'answer'/'modify'/'edit'） */
  answerEntryValues?: string[];
  onAnswerEntry?: () => void;
  /** Supervisor 模式：已选中但尚未发送的值（高亮选中项，dim 其余） */
  selectedValue?: string | null;
  /** 是否禁用所有按钮 */
  disabled?: boolean;
}

interface ReadonlyProps {
  mode: 'readonly';
  options: HitlOption[];
  /** 用户选中的值（高亮标记） */
  selectedValue?: string;
}

interface SelectableProps {
  mode: 'selectable';
  options: HitlOption[];
  selected: string | null;
  onSelect: (value: string) => void;
  disabled?: boolean;
}

interface MultiSelectProps {
  mode: 'multiSelect';
  options: HitlOption[];
  selectedValues: string[];
  onToggle: (value: string) => void;
  onConfirm: () => void;
  disabled?: boolean;
  /** 确认按钮文字 */
  confirmLabel?: string;
}

interface AnswerInputProps {
  mode: 'answerInput';
  placeholder?: string;
  /** 外部控制输入值（可选，不传则内部 state） */
  value?: string;
  onChange?: (value: string) => void;
  onSubmit: () => void;
  disabled?: boolean;
  /** 发送按钮文字 */
  submitLabel?: string;
}

type Props = InteractiveProps | ReadonlyProps | SelectableProps | MultiSelectProps | AnswerInputProps;

// ═══════════════════════════════════════════
// 组件
// ═══════════════════════════════════════════

export function HITLOptions(props: Props) {
  switch (props.mode) {
    case 'readonly':
      return <ReadonlyOptions {...props} />;
    case 'selectable':
      return <SelectableOptions {...props} />;
    case 'multiSelect':
      return <MultiSelectOptions {...props} />;
    case 'answerInput':
      return <AnswerInputOptions {...props} />;
    case 'interactive':
    default:
      return <InteractiveOptions {...props} />;
  }
}

// ═══════════════════════════════════════════
// Readonly — 只读标签
// ═══════════════════════════════════════════

function ReadonlyOptions({ options, selectedValue }: ReadonlyProps) {
  return (
    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
      {options.map(opt => {
        const isSelected = selectedValue === opt.value;
        const colors = getColor(opt.value);
        return (
          <span
            key={opt.value}
            title={opt.description}
            style={{
              padding: '4px 10px',
              borderRadius: 4,
              border: `1px solid ${isSelected ? colors.border : 'var(--border-subtle)'}`,
              background: isSelected ? colors.bg : 'transparent',
              color: isSelected ? colors.text : 'var(--text-muted)',
              fontSize: 11,
              fontFamily: 'var(--font-body)',
              opacity: isSelected ? 1 : 0.55,
              fontWeight: isSelected ? 500 : 400,
            }}
          >
            {isSelected ? '▸ ' : ''}{opt.label}
          </span>
        );
      })}
    </div>
  );
}

// ═══════════════════════════════════════════
// Interactive — 可点击按钮
// ═══════════════════════════════════════════

function InteractiveOptions({
  options,
  onSelect,
  answerEntryValues,
  onAnswerEntry,
  selectedValue,
  disabled,
}: InteractiveProps) {
  const answerSet = new Set(answerEntryValues || ['answer', 'modify', 'edit']);

  return (
    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
      {options.map(opt => {
        const isAnswerEntry = answerSet.has(opt.value);
        const colors = getColor(opt.value);
        const isDanger = opt.value === 'reject' || opt.value === 'skip' || opt.value === 'cancel';
        const isPrimary = opt.value === 'approve' || opt.value === 'invite' || opt.value === 'confirm';

        // Supervisor 模式选中效果：非选中项 dim
        const isSelected = selectedValue === opt.value;
        const hasSelection = selectedValue != null;
        const dimmed = hasSelection && !isSelected;

        return (
          <button
            key={opt.value}
            onClick={() => (isAnswerEntry && onAnswerEntry ? onAnswerEntry() : onSelect(opt.value))}
            disabled={disabled}
            title={opt.description || ''}
            style={{
              padding: '6px 12px',
              borderRadius: 4,
              border: `1px solid ${isSelected ? colors.border : (hasSelection ? 'var(--border-subtle)' : colors.border)}`,
              background: isPrimary
                ? (isSelected ? colors.bg : dimmed ? 'transparent' : colors.bg)
                : isDanger
                  ? (isSelected ? 'rgba(248,113,113,0.06)' : dimmed ? 'transparent' : 'rgba(248,113,113,0.06)')
                  : (isSelected ? colors.bg : dimmed ? 'transparent' : colors.bg),
              color: isSelected
                ? colors.text
                : dimmed
                  ? 'var(--text-muted)'
                  : isPrimary
                    ? colors.text
                    : isDanger
                      ? 'var(--red-400)'
                      : colors.text || 'var(--text-secondary)',
              fontSize: 11,
              cursor: disabled || dimmed ? 'default' : 'pointer',
              fontFamily: 'var(--font-body)',
              fontWeight: isSelected ? 600 : isPrimary ? 500 : 400,
              opacity: dimmed ? 0.4 : 1,
              transition: 'all 0.15s',
            }}
          >
            {isSelected ? '▸ ' : ''}{opt.label}
          </button>
        );
      })}
    </div>
  );
}

// ═══════════════════════════════════════════
// Selectable — 单选列表（可描述）
// ═══════════════════════════════════════════

function SelectableOptions({ options, selected, onSelect, disabled }: SelectableProps) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {options.map(opt => {
        const isSelected = selected === opt.value;
        return (
          <button
            key={opt.value}
            onClick={() => onSelect(opt.value)}
            disabled={disabled}
            title={opt.description}
            style={{
              width: '100%',
              padding: '10px 12px',
              background: isSelected ? 'var(--gold-bg)' : 'var(--bg-elevated)',
              border: `1px solid ${isSelected ? 'var(--gold-border)' : 'var(--border-subtle)'}`,
              borderRadius: 8,
              textAlign: 'left',
              cursor: disabled ? 'not-allowed' : 'pointer',
              opacity: disabled ? 0.5 : 1,
              transition: 'all 0.15s',
            }}
          >
            <div style={{ fontSize: 12, fontWeight: 500, color: isSelected ? 'var(--gold-400)' : 'var(--text-primary)' }}>
              {opt.label}
            </div>
            {opt.description && (
              <div style={{ fontSize: 10, color: 'var(--text-dim)', marginTop: 2 }}>
                {opt.description}
              </div>
            )}
          </button>
        );
      })}
    </div>
  );
}

// ═══════════════════════════════════════════
// MultiSelect — 多选复选框
// ═══════════════════════════════════════════

function MultiSelectOptions({
  options,
  selectedValues,
  onToggle,
  onConfirm,
  disabled,
  confirmLabel,
}: MultiSelectProps) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--gold-400)', marginBottom: 2 }}>
        ☑️ 可多选 · 选后点确认
      </div>
      {options.map(opt => {
        const isSelected = selectedValues.includes(opt.value);
        return (
          <button
            key={opt.value}
            onClick={() => onToggle(opt.value)}
            disabled={disabled}
            style={{
              width: '100%',
              padding: '5px 10px',
              borderRadius: 6,
              border: isSelected ? '1.2px solid var(--gold-400)' : '1.2px solid var(--border-subtle)',
              background: isSelected ? 'rgba(245,158,11,0.12)' : 'rgba(245,158,11,0.04)',
              color: 'var(--text-primary)',
              fontSize: 12,
              fontWeight: isSelected ? 550 : 400,
              cursor: disabled ? 'not-allowed' : 'pointer',
              textAlign: 'left',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              opacity: disabled ? 0.5 : 1,
            }}
          >
            {/* 复选框 */}
            <span style={{
              minWidth: 16, height: 16, borderRadius: 3,
              border: `1.5px solid ${isSelected ? 'var(--gold-400)' : 'var(--border-medium)'}`,
              background: isSelected ? 'var(--gold-400)' : 'transparent',
              color: '#fff',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 10, fontWeight: 700, flexShrink: 0,
            }}>
              {isSelected ? '✓' : ''}
            </span>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 12, lineHeight: 1.3 }}>{opt.label}</div>
              {opt.description && (
                <div style={{ fontSize: 10, color: 'var(--text-dim)', marginTop: 1, lineHeight: 1.2 }}>
                  {opt.description}
                </div>
              )}
            </div>
          </button>
        );
      })}
      <button
        onClick={onConfirm}
        disabled={disabled || selectedValues.length === 0}
        style={{
          padding: '6px 12px', borderRadius: 6, border: 'none',
          background: selectedValues.length > 0 ? 'var(--gold-400)' : 'rgba(245,158,11,0.15)',
          color: selectedValues.length > 0 ? '#fff' : 'rgba(245,158,11,0.4)',
          fontSize: 12, fontWeight: 600,
          cursor: selectedValues.length > 0 ? 'pointer' : 'not-allowed',
          marginTop: 2, alignSelf: 'flex-start',
        }}
      >
        {confirmLabel || `确认${selectedValues.length > 0 ? ` (${selectedValues.length})` : ''}`}
      </button>
    </div>
  );
}

// ═══════════════════════════════════════════
// AnswerInput — 文本输入
// ═══════════════════════════════════════════

function AnswerInputOptions({
  placeholder,
  value: externalValue,
  onChange: externalOnChange,
  onSubmit,
  disabled,
  submitLabel,
}: AnswerInputProps) {
  const [internalValue, setInternalValue] = useState('');
  const value = externalValue !== undefined ? externalValue : internalValue;
  const handleChange = externalOnChange || setInternalValue;

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && value.trim()) {
      onSubmit();
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--gold-400)' }}>
        ✏️ 请回答 · Enter 发送
      </div>
      <div style={{ display: 'flex', gap: 6 }}>
        <input
          type="text"
          value={value}
          onChange={(e) => handleChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder || '输入你的回答...'}
          disabled={disabled}
          autoFocus
          style={{
            flex: 1, padding: '5px 10px', borderRadius: 6,
            border: '1.2px solid rgba(245, 158, 11, 0.25)',
            background: 'var(--bg-card-hover)', color: 'var(--text-primary)',
            fontSize: 12, outline: 'none',
          }}
        />
        <button
          onClick={onSubmit}
          disabled={disabled || !value.trim()}
          style={{
            padding: '5px 12px', borderRadius: 6, border: 'none',
            background: value.trim() ? 'var(--gold-400)' : 'rgba(245,158,11,0.12)',
            color: value.trim() ? '#fff' : 'rgba(245,158,11,0.4)',
            fontSize: 12, fontWeight: 600,
            cursor: value.trim() ? 'pointer' : 'not-allowed',
          }}
        >
          {submitLabel || '发送'}
        </button>
      </div>
    </div>
  );
}

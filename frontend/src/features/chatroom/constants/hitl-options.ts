/** HITL 卡片按钮文案常量
 *
 * 抽到独立文件以便：
 * 1. 国际化时只改一处
 * 2. 文案微调不需动 reducer
 * 3. UI 测试稳定（断言 label 字面值时有单一来源）
 */

import type { HitlOption } from '../types/state';

/** delta_plan HITL 默认按钮（PR5 介入闭环） */
export const DELTA_PLAN_OPTIONS: HitlOption[] = [
  { label: '✅ 应用修改', value: 'approve' },
  { label: '✍️ 我再补充', value: 'modify' },
  { label: '❌ 撤回介入', value: 'reject' },
];

/** 澄清/确认场景的通用 fallback（后端通常会自带 options） */
export const CLARIFICATION_FALLBACK_OPTIONS: HitlOption[] = [
  { label: '我来回答', value: 'answer' },
  { label: '取消', value: 'skip' },
];

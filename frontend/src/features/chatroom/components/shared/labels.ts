/** Meta phase id → 显示文案映射 */

import type { MetaPhaseId } from '../../types/state';
import { META_PHASES_STATIC } from '../../types/state';

const LABEL_MAP: Record<MetaPhaseId, { full: string; short: string }> = (() => {
  const m: Record<string, { full: string; short: string }> = {};
  META_PHASES_STATIC.forEach(p => {
    m[p.id] = { full: p.label, short: p.shortLabel };
  });
  return m as Record<MetaPhaseId, { full: string; short: string }>;
})();

/** "M1·需求分析" 全名 */
export function metaPhaseLabel(id: MetaPhaseId): string {
  return LABEL_MAP[id]?.full ?? id;
}

/** "分析" 短名 */
export function metaPhaseShortLabel(id: MetaPhaseId): string {
  return LABEL_MAP[id]?.short ?? id;
}

/** chip 显示："M1 需求分析" */
export function metaPhaseChipText(id: MetaPhaseId, iteration?: number): string {
  const label = LABEL_MAP[id]?.full ?? id;
  // 去除 · 分隔符，更紧凑
  const compact = label.replace('·', ' ');
  const suffix = iteration && iteration > 0 ? `'`.repeat(iteration) : '';
  return `${compact}${suffix}`;
}

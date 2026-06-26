/** useTeamMode — 获取当前团队的协作模式
 *
 * ChatRoomIndex 用 mode 切换不同的视图：
 *   - supervisor → SupervisorView（Leader 分析任务，委派成员执行）
 *   - swarm      → SwarmView（多 Agent 自由讨论）
 *   - langgraph  → LangGraphView（工作流节点执行）
 *
 * 返回 null 表示仍在加载中，避免在模式未确定时挂载错误的视图组件。
 */
import { useEffect, useState } from 'react';

const API_BASE = (import.meta as unknown as { env: Record<string, string> }).env?.VITE_API_URL || '';

export type CollabMode = 'swarm' | 'supervisor' | 'langgraph';

export function useTeamMode(teamId: string | null): CollabMode | null {
  const [mode, setMode] = useState<CollabMode | null>(null);

  useEffect(() => {
    if (!teamId) {
      setMode('supervisor');
      return;
    }
    let cancelled = false;
    fetch(`${API_BASE}/api/v1/teams/${teamId}`)
      .then(r => r.ok ? r.json() : null)
      .then((data: { collaboration_mode?: string } | null) => {
        if (cancelled || !data) return;
        const raw = (data.collaboration_mode || 'supervisor').toLowerCase();
        if (raw === 'swarm' || raw === 'supervisor' || raw === 'langgraph') {
          setMode(raw as CollabMode);
        } else {
          setMode('supervisor');
        }
      })
      .catch(() => { if (!cancelled) setMode('supervisor'); });
    return () => { cancelled = true; };
  }, [teamId]);

  return mode;
}

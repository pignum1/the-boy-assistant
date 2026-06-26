/** useTeamMembers — 加载团队完整 Agent 名单
 *
 * TeamDrawer 之前只能从对话流派生 Agent，会漏掉还没说话的 idle 成员。
 * 这个 hook 在 ChatRoom 挂载时 fetch /api/v1/teams/{id}，提供完整 roster。
 */
import { useEffect, useState } from 'react';

const API_BASE = (import.meta as unknown as { env: Record<string, string> }).env?.VITE_API_URL || 'http://localhost:8000';

export interface TeamMember {
  agentId: string;
  agentName: string;
  roleName: string;
  roleIcon: string;
  capabilities: string[];
}

interface RawMember {
  agent_id: string;
  agent_name: string;
  role_name: string;
  role_icon: string;
  capabilities: string[] | null;
}

/** role_name → emoji 推断（覆盖后端可能没设 role_icon 的情况） */
const ROLE_EMOJI: Record<string, string> = {
  pm: '📋',
  product_manager: '📋',
  architect: '🏗',
  frontend_dev: '🎨',
  backend_dev: '💻',
  fullstack_dev: '💻',
  ui_designer: '🎨',
  qa: '🧪',
  tester: '🧪',
  devops: '🚀',
  supervisor: '👑',
};

function inferEmoji(roleName: string, rawIcon: string): string {
  if (rawIcon && rawIcon !== '🤖') return rawIcon;
  return ROLE_EMOJI[roleName.toLowerCase()] || '🤖';
}

export function useTeamMembers(teamId: string | null): TeamMember[] {
  const [members, setMembers] = useState<TeamMember[]>([]);

  useEffect(() => {
    if (!teamId) return;
    let cancelled = false;
    fetch(`${API_BASE}/api/v1/teams/${teamId}`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (cancelled || !data) return;
        const list: RawMember[] = data.members || [];
        setMembers(list.map(m => ({
          agentId: m.agent_id,
          agentName: m.agent_name,
          roleName: m.role_name,
          roleIcon: inferEmoji(m.role_name, m.role_icon),
          capabilities: m.capabilities || [],
        })));
      })
      .catch(() => {
        // 静默失败，TeamDrawer 会 fallback 到对话流派生
      });
    return () => { cancelled = true; };
  }, [teamId]);

  return members;
}

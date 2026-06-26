/** Collaboration system types — synced with backend CollabState */

export interface PhaseInfo {
  name: string;
  role: string;
  goal: string;
}

export interface HitlRequest {
  type: 'clarification' | 'confirmation' | 'agent_invite' | 'review';
  message: string;
  options: HitlOption[];
}

export interface HitlOption {
  label: string;
  value: string;
}

export interface FileChange {
  name: string;
  status: 'created' | 'modified';
  meta: string;
}

export interface VerificationResult {
  passed: boolean;
  feedback: string;
  severity: 'none' | 'minor' | 'major' | 'critical';
  drift_detected: boolean;
  suggestions: string[];
}

export interface CollabPhase {
  id: string;
  name: string;
  assigned_role: string;
  tasks: CollabTask[];
}

export interface CollabTask {
  id: string;
  title: string;
  description: string;
  assigned_role: string;
  depends_on: string[];
  expected_output: string;
  status: 'pending' | 'claimed' | 'in_progress' | 'done' | 'failed';
}

/** WebSocket event types from LangGraph stream */
export type CollabEvent =
  | { type: 'node_start'; node: string }
  | { type: 'agent_status'; agent: string; status: string }
  | { type: 'hitl_request' } & HitlRequest
  | { type: 'verification_complete'; verification: VerificationResult }
  | { type: 'files_changed'; files: FileChange[] }
  | { type: 'artifacts'; artifacts: Record<string, string> }
  | { type: 'message_complete'; message: string }
  | { type: 'phase_update'; phases: string[]; current: number }
  | { type: 'plan_created'; phases: CollabPhase[] };

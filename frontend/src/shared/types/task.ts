/** 用户任务相关类型 */

export interface UserTask {
  id: string;
  team_id?: string;
  session_id?: string;
  title: string;
  description?: string;
  requirement: string;
  workflow_id?: string;
  workflow_instance_id?: string;
  status: 'planning' | 'generated' | 'running' | 'paused' | 'completed' | 'failed' | 'cancelled';
  priority: 'low' | 'medium' | 'high' | 'critical';
  current_step?: string;
  progress_percentage: number;
  planned_at?: string;
  started_at?: string;
  completed_at?: string;
  ai_plan_summary?: Record<string, unknown>;
  iteration_count: number;
  previous_task_id?: string;
  created_at: string;
  updated_at: string;
}

export interface TaskIssue {
  id: string;
  user_task_id: string;
  workflow_instance_id?: string;
  node_execution_id?: string;
  title: string;
  description?: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  status: 'open' | 'in_progress' | 'resolved' | 'ignored';
  category?: 'bug' | 'performance' | 'requirement' | 'ux' | 'security' | 'other';
  resolution?: string;
  resolved_at?: string;
  created_by?: string;
  created_at: string;
  updated_at: string;
}

export interface TaskProgress {
  task_id: string;
  task_title: string;
  status: string;
  progress_percentage: number;
  current_step?: {
    status: string;
    node_id?: string;
    node_type?: string;
    node_label?: string;
  };
  steps: Array<{
    node_id: string;
    node_type: string;
    node_label: string;
    status: string;
    started_at?: string;
    completed_at?: string;
  }>;
  issues_count: number;
  started_at?: string;
  estimated_completion?: string;
}

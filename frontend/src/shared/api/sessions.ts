/** Sessions API 客户端 */

import { api } from './client';
import type {
  SessionInfo,
  SessionCreateParams,
  SessionUpdateParams,
  SessionMessage,
  WorkspaceInfo,
} from '../types/session';

/** API base URL for direct fetch calls (file download/upload) */
export const API_BASE = (import.meta as unknown as { env: Record<string, string> }).env?.VITE_API_URL || '';

/** Encode path for URL, preserving / separators (for subdirectory paths) */
function encodePath(path: string): string {
  return path.split('/').map(part => encodeURIComponent(part)).join('/');
}

export const sessionsApi = {
  /** 列出会话（支持 ?team_id=&status= 过滤） */
  list: (params?: { team_id?: string; status?: string; limit?: number }) =>
    api.get<{ sessions: SessionInfo[]; total: number }>('/api/v1/sessions', params as Record<string, string | number | boolean>),

  /** 获取单个会话 */
  get: (id: string) =>
    api.get<SessionInfo>(`/api/v1/sessions/${id}`),

  /** 创建新会话 */
  create: (data: SessionCreateParams) =>
    api.post<SessionInfo>('/api/v1/sessions', data),

  /** 更新会话 */
  update: (id: string, data: SessionUpdateParams) =>
    api.put<SessionInfo>(`/api/v1/sessions/${id}`, data),

  /** 删除会话（完全删除，包括对话记录和记忆数据） */
  delete: (id: string) =>
    api.del<{ status: string; session_id: string }>(`/api/v1/sessions/${id}`),

  /** 获取会话历史消息 */
  getMessages: (id: string, limit?: number) =>
    api.get<{ messages: SessionMessage[]; total: number }>(`/api/v1/sessions/${id}/messages`, { limit: limit || 100 }),

  /** 获取会话工作空间信息 */
  getWorkspace: (id: string) =>
    api.get<WorkspaceInfo>(`/api/v1/sessions/${id}/workspace`),

  /** 修改工作空间路径 */
  updateWorkspace: (id: string, path: string) =>
    api.put<WorkspaceInfo>(`/api/v1/sessions/${id}/workspace`, { path }),

  /** 列出工作空间文件/目录 */
  listFiles: (id: string, subPath?: string) =>
    api.get<{ items: Array<{ name: string; path: string; size: number; modified: string; is_dir: boolean; children: null }>; total: number }>(
      `/api/v1/sessions/${id}/workspace/files${subPath ? `?path=${encodeURIComponent(subPath)}` : ''}`
    ),

  /** 递归列出所有工作空间文件（用于产物抽屉） */
  listAllFiles: (id: string) =>
    api.get<{ items: Array<{ name: string; path: string; size: number; modified: string; is_dir: boolean }>; total: number }>(
      `/api/v1/sessions/${id}/workspace/files?recursive=true`
    ),

  /** 获取文件内容（预览） */
  getFileContent: (sessionId: string, filename: string) =>
    api.get<{ filename: string; size: number; content: string | null; mime_type: string; download?: boolean; local_path?: string }>(
      `/api/v1/sessions/${sessionId}/workspace/files/${encodePath(filename)}`
    ),

  /** 上传文件到工作空间 */
  uploadFile: async (id: string, file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    const API_BASE_LOCAL = (import.meta as unknown as { env: Record<string, string> }).env?.VITE_API_URL || '';
    const res = await fetch(`${API_BASE_LOCAL}/api/v1/sessions/${id}/workspace/upload`, {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
    return res.json() as Promise<{ filename: string; path: string; size: number }>;
  },

  /** 删除工作空间文件/目录 */
  deleteFile: (sessionId: string, filePath: string) =>
    api.del(`/api/v1/sessions/${sessionId}/workspace/files?path=${encodeURIComponent(filePath)}`),

  /** 发送聊天消息（REST） */
  chat: (id: string, message: string) =>
    api.post<{ events: unknown[]; message: { agent: string; content: string } | null }>(
      `/api/v1/sessions/${id}/chat`,
      { message }
    ),
};

const API_BASE = import.meta.env.VITE_API_URL || '';
const API_KEY = import.meta.env.VITE_API_KEY || '';

interface RequestOptions extends Omit<RequestInit, 'body'> {
  body?: unknown;
  params?: Record<string, string | number | boolean | undefined>;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, params, ...init } = options;

  let url = `${API_BASE}${path}`;
  if (params) {
    const qs = new URLSearchParams(
      Object.entries(params)
        .filter(([, v]) => v !== undefined)
        .map(([k, v]) => [k, String(v)])
    ).toString();
    if (qs) url += `?${qs}`;
  }

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...((init.headers as Record<string, string>) || {}),
  };

  // 注入 API Key（如果配置了）
  if (API_KEY) {
    headers['X-API-Key'] = API_KEY;
  }

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 30000);  // 30s timeout
  const res = await fetch(url, {
    ...init,
    headers,
    body: body ? JSON.stringify(body) : undefined,
    signal: controller.signal,
  }).finally(() => clearTimeout(timeoutId));

  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`API ${res.status}: ${detail}`);
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

/** 为 WebSocket URL 附加 token 参数 */
export function getWsUrl(basePath: string, extraParams?: Record<string, string>): string {
  // 构建 WS URL：有 API_BASE 时直连，否则走当前 host（Vite proxy）
  let url: string;
  if (API_BASE) {
    const wsBase = API_BASE.replace(/^http/, 'ws');
    const parsed = new URL(basePath, wsBase);
    url = parsed.toString();
  } else {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    url = `${protocol}//${location.host}${basePath}`;
  }
  const parsed = new URL(url);
  if (API_KEY) {
    parsed.searchParams.set('token', API_KEY);
  }
  if (extraParams) {
    Object.entries(extraParams).forEach(([k, v]) => parsed.searchParams.set(k, v));
  }
  return parsed.toString();
}

export const api = {
  get: <T>(path: string, params?: Record<string, string | number | boolean | undefined>) =>
    request<T>(path, { method: 'GET', params }),

  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body }),

  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'PUT', body }),

  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'PATCH', body }),

  del: <T>(path: string) =>
    request<T>(path, { method: 'DELETE' }),
};

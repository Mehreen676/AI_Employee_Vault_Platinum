import type {
  HealthResponse,
  VaultStatus,
  QueueResponse,
  TaskDetail,
  LogsResponse,
  EvidenceListResponse,
  GenerateEvidenceResponse,
  ApprovalResponse,
} from './types';

// ── Base fetch ────────────────────────────────────────────────────────────────

const BASE_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL?.replace(/\/$/, '') || 'http://localhost:7860';

export function getBackendUrl() {
  return BASE_URL;
}

async function apiFetch<T>(
  path: string,
  init?: RequestInit,
  expectText = false,
): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15_000);

  try {
    const res = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers: { Accept: 'application/json', ...init?.headers },
      signal: controller.signal,
    });

    if (!res.ok) {
      let detail = res.statusText;
      try {
        const body = await res.json();
        detail = body?.detail ?? detail;
      } catch {
        detail = await res.text().catch(() => detail);
      }
      throw new Error(`${res.status}: ${detail}`);
    }

    if (expectText) return (await res.text()) as unknown as T;
    const ct = res.headers.get('content-type') ?? '';
    if (ct.includes('text/plain')) return (await res.text()) as unknown as T;
    return res.json() as Promise<T>;
  } finally {
    clearTimeout(timeout);
  }
}

// ── API surface ───────────────────────────────────────────────────────────────

export const api = {
  // System
  health: () => apiFetch<HealthResponse>('/health'),
  status: () => apiFetch<VaultStatus>('/status'),

  // Queues
  queue: (name: string, limit = 50) =>
    apiFetch<QueueResponse>(`/queue/${name}?limit=${limit}`),
  task: (queue: string, filename: string) =>
    apiFetch<TaskDetail>(`/task/${encodeURIComponent(queue)}/${encodeURIComponent(filename)}`),

  // Logs
  logsExecution: (tail = 50) =>
    apiFetch<LogsResponse>(`/logs/execution?tail=${tail}`),
  logsHealth: (tail = 50) =>
    apiFetch<LogsResponse>(`/logs/health?tail=${tail}`),
  logsPrompt: (tail = 20) =>
    apiFetch<LogsResponse>(`/logs/prompt?tail=${tail}`),

  // Evidence
  evidenceList: () => apiFetch<EvidenceListResponse>('/evidence/list'),
  evidenceJudgeProof: () =>
    apiFetch<string>('/evidence/judge-proof', undefined, true),
  evidenceGenerate: (n = 20) =>
    apiFetch<GenerateEvidenceResponse>(`/evidence/generate?n=${n}`, {
      method: 'POST',
    }),

  // HITL
  approve: (filename: string) =>
    apiFetch<ApprovalResponse>(`/approve/${encodeURIComponent(filename)}`, {
      method: 'POST',
    }),
  reject: (filename: string) =>
    apiFetch<ApprovalResponse>(`/reject/${encodeURIComponent(filename)}`, {
      method: 'POST',
    }),
};

// ── Polling hook helper (pure util — used by client components) ───────────────

export type PollingState<T> = {
  data: T | null;
  loading: boolean;
  error: string | null;
};

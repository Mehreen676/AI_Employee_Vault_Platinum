// ── Vault API types ──────────────────────────────────────────────────────────

export interface HealthResponse {
  status: string;
  time: string;
  version: string;
}

export interface ProcessHealth {
  alive: boolean;
  pid?: number;
  restarts?: number;
}

export interface HealthEntry {
  timestamp?: string;
  cycle?: number;
  cloud_agent?: ProcessHealth;
  gmail_watcher?: ProcessHealth;
  local_executor?: ProcessHealth;
  [key: string]: unknown;
}

export interface ExecutionEntry {
  id?: string;
  task_type?: string;
  action?: string;
  timestamp?: string;
  from?: string;
  via?: string;
  to?: string;
  result?: string;
  source?: string;
  _raw?: string;
  [key: string]: unknown;
}

export interface WatchdogComponent {
  status: string;       // "online" | "offline"
  last_seen: string | null;
}

export interface VaultStatus {
  vault_root: string;
  queues: Record<string, number>;
  cloud_updates: string[];
  last_executions: ExecutionEntry[];
  last_health: HealthEntry | null;
  agent_status?: string;
  last_heartbeat?: string | null;
  watchdog?: Record<string, WatchdogComponent>;
  time: string;
}

export interface QueueTask {
  filename: string;
  size_bytes: number;
  id?: string;
  task_type?: string;
  action?: string;
  timestamp?: string;
  status?: string;
  result?: string;
}

export type TaskDetail = Record<string, unknown> & {
  filename?: string;
  content?: string;
};

export interface QueueResponse {
  queue: string;
  count: number;
  tasks: QueueTask[];
}

export interface LogsResponse {
  count: number;
  entries: (ExecutionEntry | HealthEntry | Record<string, unknown>)[];
}

export interface EvidenceFile {
  filename: string;
  size_bytes: number;
  suffix: string;
}

export interface EvidenceListResponse {
  count: number;
  files: EvidenceFile[];
}

export interface GenerateEvidenceResponse {
  status: string;
  path: string;
  exists: boolean;
  snippet: string;
  stdout: string;
}

export interface ApprovalResponse {
  status: string;
  action: string;
  filename: string;
  moved_to?: string;
}

// ── UI helper types ──────────────────────────────────────────────────────────

export type QueueName =
  | 'needs_action'
  | 'waiting_approval'
  | 'pending_approval'
  | 'approved'
  | 'done'
  | 'retry_queue';

export interface QueueMeta {
  key: QueueName;
  label: string;
  color: string;          // Tailwind text colour class
  borderColor: string;    // Tailwind border colour class
  bgGlow: string;         // Tailwind shadow class
  icon: string;
  description: string;
}

export const QUEUE_META: QueueMeta[] = [
  {
    key: 'needs_action',
    label: 'Needs Action',
    color: 'text-vault-blue',
    borderColor: 'border-vault-blue/40',
    bgGlow: 'shadow-neon-cyan',
    icon: '📥',
    description: 'New inputs awaiting Cloud Agent',
  },
  {
    key: 'waiting_approval',
    label: 'Waiting Approval',
    color: 'text-vault-gold',
    borderColor: 'border-vault-gold/40',
    bgGlow: 'shadow-neon-gold',
    icon: '⏳',
    description: 'Tasks pending HITL gate decision',
  },
  {
    key: 'pending_approval',
    label: 'Pending Approval',
    color: 'text-vault-purple',
    borderColor: 'border-vault-purple/40',
    bgGlow: 'shadow-neon-purple',
    icon: '📬',
    description: 'Cloud Agent output awaiting executor',
  },
  {
    key: 'done',
    label: 'Done',
    color: 'text-vault-green',
    borderColor: 'border-vault-green/40',
    bgGlow: 'shadow-neon-green',
    icon: '✅',
    description: 'Successfully completed tasks',
  },
  {
    key: 'retry_queue',
    label: 'Retry Queue',
    color: 'text-vault-red',
    borderColor: 'border-vault-red/40',
    bgGlow: 'shadow-neon-red',
    icon: '🔄',
    description: 'Failed tasks awaiting review',
  },
];

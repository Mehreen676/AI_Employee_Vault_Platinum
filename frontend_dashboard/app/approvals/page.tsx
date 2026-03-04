'use client';

import { useCallback, useEffect, useState } from 'react';
import { api } from '@/lib/api';
import type { QueueTask, TaskDetail } from '@/lib/types';

type ActionState = 'idle' | 'approving' | 'rejecting' | 'done';

function ts(iso?: string) {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleString(); } catch { return iso; }
}

function typeBadge(type?: string) {
  if (!type) return null;
  const map: Record<string, string> = {
    email: 'badge-info', odoo: 'badge-purple', social: 'badge-warning',
    calendar: 'badge-success', file: 'badge-default',
  };
  return <span className={map[type] ?? 'badge-default'}>{type}</span>;
}

export default function ApprovalsPage() {
  const [tasks, setTasks]           = useState<QueueTask[]>([]);
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState<string | null>(null);
  const [search, setSearch]         = useState('');
  const [filterType, setFilterType] = useState('');

  const [selected, setSelected]     = useState<QueueTask | null>(null);
  const [detail, setDetail]         = useState<TaskDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const [actionState, setActionState]   = useState<ActionState>('idle');
  const [actionMsg, setActionMsg]       = useState('');
  const [lastUpdated, setLastUpdated]   = useState<Date | null>(null);

  // Fetch both waiting_approval and pending_approval queues
  const fetchTasks = useCallback(async () => {
    try {
      const [wa, pa] = await Promise.allSettled([
        api.queue('waiting_approval', 100),
        api.queue('pending_approval', 100),
      ]);
      const all: QueueTask[] = [];
      if (wa.status === 'fulfilled') all.push(...wa.value.tasks);
      if (pa.status === 'fulfilled') all.push(...pa.value.tasks);
      // Deduplicate by filename
      const seen = new Set<string>();
      const unique = all.filter((t) => {
        if (seen.has(t.filename)) return false;
        seen.add(t.filename);
        return true;
      });
      setTasks(unique);
      setError(null);
      setLastUpdated(new Date());
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load tasks');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTasks();
    const id = setInterval(fetchTasks, 10_000);
    return () => clearInterval(id);
  }, [fetchTasks]);

  // Load task detail on selection
  useEffect(() => {
    if (!selected) { setDetail(null); return; }
    setDetailLoading(true);
    // Try waiting_approval first, then pending_approval
    const tryQueues = async () => {
      for (const q of ['waiting_approval', 'pending_approval']) {
        try {
          const d = await api.task(q, selected.filename);
          setDetail(d);
          setDetailLoading(false);
          return;
        } catch { /* try next */ }
      }
      setDetail({ filename: selected.filename, _error: 'Could not load details' });
      setDetailLoading(false);
    };
    tryQueues();
  }, [selected]);

  const handleAction = async (action: 'approve' | 'reject') => {
    if (!selected) return;
    setActionState(action === 'approve' ? 'approving' : 'rejecting');
    setActionMsg('');
    try {
      const res = action === 'approve'
        ? await api.approve(selected.filename)
        : await api.reject(selected.filename);
      setActionMsg(`✓ ${res.action}: ${selected.filename}`);
      setActionState('done');
      setSelected(null);
      await fetchTasks();
    } catch (e) {
      setActionMsg('✗ ' + (e instanceof Error ? e.message : 'Action failed'));
      setActionState('idle');
    }
  };

  // Filtered list
  const filtered = tasks.filter((t) => {
    const matchSearch =
      !search ||
      t.filename.toLowerCase().includes(search.toLowerCase()) ||
      (t.task_type ?? '').toLowerCase().includes(search.toLowerCase()) ||
      (t.id ?? '').toLowerCase().includes(search.toLowerCase());
    const matchType = !filterType || t.task_type === filterType;
    return matchSearch && matchType;
  });

  const taskTypes = [...new Set(tasks.map((t) => t.task_type).filter(Boolean))] as string[];

  return (
    <main className="flex-1 px-8 py-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-vault-text">HITL Approvals</h1>
          <p className="text-sm text-vault-muted mt-1">
            Human-in-the-Loop review queue
            {lastUpdated && (
              <span className="ml-2 font-mono text-xs text-vault-dim">
                · {lastUpdated.toLocaleTimeString()}
              </span>
            )}
          </p>
        </div>
        <button onClick={fetchTasks} className="btn-ghost text-xs">↺ Refresh</button>
      </div>

      {error && (
        <div className="mb-4 p-3 rounded-xl bg-vault-red/10 border border-vault-red/30 text-vault-red text-sm">
          ⚠ {error}
        </div>
      )}

      {actionMsg && (
        <div className={`mb-4 p-3 rounded-xl text-sm font-mono border ${
          actionMsg.startsWith('✓')
            ? 'bg-vault-green/10 border-vault-green/30 text-vault-green'
            : 'bg-vault-red/10 border-vault-red/30 text-vault-red'
        }`}>
          {actionMsg}
        </div>
      )}

      <div className="flex gap-6 h-[calc(100vh-180px)]">
        {/* Task list panel */}
        <div className="w-80 shrink-0 flex flex-col gap-3">
          {/* Search + filter */}
          <div className="flex gap-2">
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search tasks…"
              className="flex-1 bg-vault-surface border border-vault-border rounded-lg px-3 py-2
                         text-sm text-vault-text placeholder-vault-dim
                         focus:outline-none focus:border-vault-cyan/50"
            />
            <select
              value={filterType}
              onChange={(e) => setFilterType(e.target.value)}
              className="bg-vault-surface border border-vault-border rounded-lg px-2 py-2
                         text-sm text-vault-muted focus:outline-none focus:border-vault-cyan/50"
            >
              <option value="">All types</option>
              {taskTypes.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>

          {/* Count */}
          <p className="text-xs text-vault-dim font-mono">
            {filtered.length} task{filtered.length !== 1 ? 's' : ''} in queue
          </p>

          {/* List */}
          <div className="flex-1 overflow-y-auto space-y-2 pr-1">
            {loading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="h-16 bg-vault-surface border border-vault-border animate-pulse rounded-xl" />
              ))
            ) : filtered.length === 0 ? (
              <div className="vault-card p-6 text-center">
                <p className="text-3xl mb-2">✓</p>
                <p className="text-sm text-vault-muted">No tasks pending review</p>
              </div>
            ) : (
              filtered.map((task) => (
                <button
                  key={task.filename}
                  onClick={() => { setSelected(task); setActionState('idle'); setActionMsg(''); }}
                  className={`w-full text-left p-3.5 rounded-xl border transition-all duration-150
                              ${selected?.filename === task.filename
                                ? 'bg-vault-purple/10 border-vault-purple/40'
                                : 'vault-card hover:border-vault-purple/30'}`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <p className="font-mono text-xs text-vault-text truncate flex-1">
                      {task.filename}
                    </p>
                    {typeBadge(task.task_type)}
                  </div>
                  <div className="mt-1.5 flex items-center gap-2 text-[10px] text-vault-dim font-mono">
                    <span>{ts(task.timestamp).split(',')[0]}</span>
                    {task.size_bytes && <span>· {task.size_bytes}B</span>}
                  </div>
                </button>
              ))
            )}
          </div>
        </div>

        {/* Detail panel */}
        <div className="flex-1 min-w-0 vault-card p-6 flex flex-col">
          {!selected ? (
            <div className="flex-1 flex flex-col items-center justify-center text-center">
              <p className="text-4xl mb-3 opacity-30">⊕</p>
              <p className="text-vault-muted">Select a task to review</p>
              <p className="text-xs text-vault-dim mt-1">Click a task from the left panel</p>
            </div>
          ) : (
            <>
              {/* Task header */}
              <div className="flex items-start justify-between mb-5 pb-4 border-b border-vault-border">
                <div className="min-w-0">
                  <p className="font-mono text-sm text-vault-text break-all">{selected.filename}</p>
                  <div className="flex items-center gap-2 mt-1.5">
                    {typeBadge(selected.task_type)}
                    <span className="text-xs text-vault-dim">{ts(selected.timestamp)}</span>
                  </div>
                </div>
              </div>

              {/* Action buttons */}
              <div className="flex gap-3 mb-5">
                <button
                  onClick={() => handleAction('approve')}
                  disabled={actionState === 'approving' || actionState === 'rejecting'}
                  className="btn-green"
                >
                  {actionState === 'approving' ? '⟳ Approving…' : '✓ Approve'}
                </button>
                <button
                  onClick={() => handleAction('reject')}
                  disabled={actionState === 'approving' || actionState === 'rejecting'}
                  className="btn-red"
                >
                  {actionState === 'rejecting' ? '⟳ Rejecting…' : '✕ Reject'}
                </button>
              </div>

              {/* Task detail JSON */}
              <div className="flex-1 overflow-auto">
                <p className="text-xs font-semibold uppercase tracking-widest text-vault-dim mb-2">
                  Task Manifest
                </p>
                {detailLoading ? (
                  <div className="space-y-2">
                    {[1, 2, 3, 4, 5].map((i) => (
                      <div key={i} className="h-3 bg-vault-border animate-pulse rounded" style={{ width: `${90 - i * 5}%` }} />
                    ))}
                  </div>
                ) : detail ? (
                  <pre className="log-line text-vault-muted bg-vault-bg rounded-xl p-4 overflow-auto text-[11px]">
                    {JSON.stringify(detail, null, 2)}
                  </pre>
                ) : null}
              </div>
            </>
          )}
        </div>
      </div>
    </main>
  );
}

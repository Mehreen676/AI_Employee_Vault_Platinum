'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import type { ExecutionEntry, HealthEntry } from '@/lib/types';

type Tab = 'execution' | 'health' | 'prompt';

const TABS: { key: Tab; label: string; icon: string; color: string }[] = [
  { key: 'execution', label: 'Execution Log', icon: '≡', color: 'text-vault-cyan' },
  { key: 'health',    label: 'Health Log',    icon: '♡', color: 'text-vault-green' },
  { key: 'prompt',    label: 'Prompt Chain',  icon: '◈', color: 'text-vault-purple' },
];

function resultColor(result?: string) {
  if (result === 'success') return 'text-vault-green';
  if (result?.startsWith('error')) return 'text-vault-red';
  return 'text-vault-muted';
}

function aliveColor(alive?: boolean) {
  return alive ? 'text-vault-green' : 'text-vault-red';
}

function renderExecutionEntry(entry: ExecutionEntry, i: number) {
  const id = String(entry.id ?? entry.task_type ?? '').slice(0, 32);
  return (
    <div
      key={i}
      className="p-3 rounded-lg bg-vault-bg border border-vault-border/50 space-y-1 animate-fade-in"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-xs text-vault-text truncate">{id || '—'}</span>
        <span className={`font-mono text-xs shrink-0 ${resultColor(String(entry.result ?? ''))}`}>
          {String(entry.result ?? '')}
        </span>
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-0.5 text-[10px] font-mono text-vault-dim">
        {entry.task_type && <span>type: <span className="text-vault-cyan">{entry.task_type}</span></span>}
        {entry.action    && <span>action: <span className="text-vault-text">{entry.action}</span></span>}
        {entry.from      && <span>from→to: <span className="text-vault-text">{entry.from} → {entry.to}</span></span>}
        {entry.timestamp && <span>time: {new Date(String(entry.timestamp)).toLocaleTimeString()}</span>}
        {entry.source    && <span>src: {entry.source}</span>}
      </div>
    </div>
  );
}

function renderHealthEntry(entry: HealthEntry, i: number) {
  const procs = ['cloud_agent', 'gmail_watcher', 'local_executor'] as const;
  return (
    <div
      key={i}
      className="p-3 rounded-lg bg-vault-bg border border-vault-border/50 space-y-1.5 animate-fade-in"
    >
      <div className="flex items-center justify-between text-[10px] font-mono text-vault-dim">
        <span>Cycle #{String(entry.cycle ?? '?')}</span>
        <span>{entry.timestamp ? new Date(String(entry.timestamp)).toLocaleTimeString() : '—'}</span>
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-0.5">
        {procs.map((key) => {
          const p = entry[key as keyof HealthEntry] as { alive?: boolean; pid?: number; restarts?: number } | undefined;
          if (!p) return null;
          return (
            <span key={key} className="text-[10px] font-mono">
              <span className={aliveColor(p?.alive)}>{p?.alive ? '●' : '○'}</span>
              <span className="text-vault-dim ml-1 capitalize">{key.replace(/_/g, ' ')}</span>
              {p?.pid && <span className="text-vault-muted ml-1">pid:{p.pid}</span>}
              {(p?.restarts ?? 0) > 0 && <span className="text-vault-gold ml-1">↺{p?.restarts}</span>}
            </span>
          );
        })}
      </div>
    </div>
  );
}

function renderGenericEntry(entry: Record<string, unknown>, i: number) {
  return (
    <div key={i} className="p-3 rounded-lg bg-vault-bg border border-vault-border/50 animate-fade-in">
      <pre className="log-line text-vault-muted text-[10px] overflow-auto">
        {JSON.stringify(entry, null, 2)}
      </pre>
    </div>
  );
}

export default function LogsPage() {
  const [tab, setTab]       = useState<Tab>('execution');
  const [tail, setTail]     = useState(50);
  const [entries, setEntries] = useState<unknown[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError]   = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    try {
      let data;
      if (tab === 'execution') data = await api.logsExecution(tail);
      else if (tab === 'health') data = await api.logsHealth(tail);
      else data = await api.logsPrompt(tail);
      setEntries(data.entries);
      setError(null);
      setLastUpdated(new Date());
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load logs');
    } finally {
      setLoading(false);
    }
  }, [tab, tail]);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  useEffect(() => {
    if (!autoRefresh) return;
    const id = setInterval(fetchLogs, 8_000);
    return () => clearInterval(id);
  }, [fetchLogs, autoRefresh]);

  useEffect(() => {
    // Auto-scroll to bottom when new entries arrive
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [entries.length]);

  const tabMeta = TABS.find((t) => t.key === tab)!;

  return (
    <main className="flex-1 px-8 py-8 flex flex-col max-h-screen">
      {/* Header */}
      <div className="flex items-center justify-between mb-6 shrink-0">
        <div>
          <h1 className="text-2xl font-bold text-vault-text">System Logs</h1>
          <p className="text-sm text-vault-muted mt-1">
            Live log stream from vault/Logs/
            {lastUpdated && (
              <span className="ml-2 font-mono text-xs text-vault-dim">
                · {lastUpdated.toLocaleTimeString()}
              </span>
            )}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {/* Auto-refresh toggle */}
          <label className="flex items-center gap-2 cursor-pointer select-none text-sm text-vault-muted">
            <div
              onClick={() => setAutoRefresh((v) => !v)}
              className={`relative w-8 h-4 rounded-full transition-colors ${autoRefresh ? 'bg-vault-cyan' : 'bg-vault-border'}`}
            >
              <span className={`absolute top-0.5 w-3 h-3 rounded-full bg-white transition-transform ${autoRefresh ? 'translate-x-4' : 'translate-x-0.5'}`} />
            </div>
            Auto-refresh
          </label>
          <button onClick={fetchLogs} className="btn-ghost text-xs">↺ Refresh</button>
        </div>
      </div>

      {/* Tabs + tail control */}
      <div className="flex items-center justify-between mb-4 shrink-0">
        <div className="flex gap-1 bg-vault-surface border border-vault-border rounded-xl p-1">
          {TABS.map(({ key, label, icon, color }) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-all duration-150 flex items-center gap-2
                          ${tab === key
                            ? `bg-vault-bg ${color} border border-vault-border`
                            : 'text-vault-muted hover:text-vault-text'}`}
            >
              <span>{icon}</span> {label}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2 text-sm text-vault-muted">
          <span>Tail:</span>
          {[20, 50, 100, 200].map((n) => (
            <button
              key={n}
              onClick={() => setTail(n)}
              className={`px-2.5 py-1 rounded-lg font-mono text-xs border transition-all
                          ${tail === n
                            ? 'bg-vault-cyan/10 text-vault-cyan border-vault-cyan/30'
                            : 'border-vault-border text-vault-dim hover:text-vault-text'}`}
            >
              {n}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="mb-4 p-3 rounded-xl bg-vault-red/10 border border-vault-red/30 text-vault-red text-sm shrink-0">
          ⚠ {error}
        </div>
      )}

      {/* Log entries */}
      <div className="flex-1 overflow-y-auto vault-card p-4">
        {/* Terminal header bar */}
        <div className="flex items-center gap-2 mb-3 pb-3 border-b border-vault-border">
          <div className="flex gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-vault-red/60" />
            <span className="w-2.5 h-2.5 rounded-full bg-vault-gold/60" />
            <span className="w-2.5 h-2.5 rounded-full bg-vault-green/60" />
          </div>
          <span className={`font-mono text-xs ml-2 ${tabMeta.color}`}>
            vault/Logs/{tab === 'prompt' ? 'history/prompt_log.json' : `${tab}_log.json`}
          </span>
          <span className="ml-auto text-xs text-vault-dim font-mono">
            {entries.length} entries
          </span>
        </div>

        {loading ? (
          <div className="space-y-2">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="h-14 bg-vault-border animate-pulse rounded-lg" />
            ))}
          </div>
        ) : entries.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <p className="text-3xl mb-2 opacity-30">≡</p>
            <p className="text-sm text-vault-muted">No log entries yet.</p>
            <p className="text-xs text-vault-dim mt-1">
              Run the system to generate logs.
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {entries.map((entry, i) => {
              if (tab === 'execution') return renderExecutionEntry(entry as ExecutionEntry, i);
              if (tab === 'health')    return renderHealthEntry(entry as HealthEntry, i);
              return renderGenericEntry(entry as Record<string, unknown>, i);
            })}
            <div ref={bottomRef} />
          </div>
        )}
      </div>
    </main>
  );
}

'use client';

import { useCallback, useEffect, useState } from 'react';
import { api, getBackendUrl } from '@/lib/api';
import { QUEUE_META, type VaultStatus, type GenerateEvidenceResponse } from '@/lib/types';

// ── Helpers ───────────────────────────────────────────────────────────────────

function ts(iso?: string) {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleTimeString(); } catch { return iso; }
}

function resultBadge(result?: string) {
  if (!result) return null;
  const ok = result === 'success';
  return (
    <span className={ok ? 'badge-success' : 'badge-error'}>
      {result}
    </span>
  );
}

// ── Status card ───────────────────────────────────────────────────────────────

function StatusCard({
  icon, label, count, color, borderColor, description, loading,
}: {
  icon: string; label: string; count: number | undefined;
  color: string; borderColor: string; description: string; loading: boolean;
}) {
  return (
    <div className={`vault-card p-5 border ${borderColor} flex flex-col gap-3`}>
      <div className="flex items-start justify-between">
        <span className="text-2xl">{icon}</span>
        <span className={`text-xs font-mono px-2 py-0.5 rounded-full border ${borderColor} ${color} opacity-70`}>
          queue
        </span>
      </div>
      <div>
        {loading ? (
          <div className="h-8 w-16 bg-vault-border animate-pulse rounded" />
        ) : (
          <p className={`text-3xl font-bold font-mono ${color}`}>
            {count ?? '—'}
          </p>
        )}
        <p className="text-sm font-semibold text-vault-text mt-1">{label}</p>
        <p className="text-xs text-vault-muted mt-0.5">{description}</p>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function OverviewPage() {
  const [status, setStatus]     = useState<VaultStatus | null>(null);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const [genLoading, setGenLoading]   = useState(false);
  const [genResult, setGenResult]     = useState<GenerateEvidenceResponse | null>(null);
  const [genError, setGenError]       = useState<string | null>(null);

  const [proofOpen, setProofOpen]     = useState(false);
  const [proofText, setProofText]     = useState('');
  const [proofLoading, setProofLoading] = useState(false);

  const fetchStatus = useCallback(async () => {
    try {
      const s = await api.status();
      setStatus(s);
      setError(null);
      setLastUpdated(new Date());
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to reach backend');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    const id = setInterval(fetchStatus, 8_000);
    return () => clearInterval(id);
  }, [fetchStatus]);

  const handleGenerate = async () => {
    setGenLoading(true);
    setGenError(null);
    setGenResult(null);
    try {
      const r = await api.evidenceGenerate(20);
      setGenResult(r);
    } catch (e) {
      setGenError(e instanceof Error ? e.message : 'Generation failed');
    } finally {
      setGenLoading(false);
    }
  };

  const handleOpenProof = async () => {
    setProofOpen(true);
    if (proofText) return;
    setProofLoading(true);
    try {
      const txt = await api.evidenceJudgeProof();
      setProofText(txt);
    } catch (e) {
      setProofText('Error: ' + (e instanceof Error ? e.message : 'Could not load proof'));
    } finally {
      setProofLoading(false);
    }
  };

  const q = status?.queues ?? {};

  return (
    <main className="flex-1 px-8 py-8 max-w-7xl">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-vault-text">
            System Overview
          </h1>
          <p className="text-sm text-vault-muted mt-1">
            AI Employee Vault — Platinum Tier
            <span className="ml-2 font-mono text-xs text-vault-cyan">v1.4.0</span>
          </p>
        </div>
        <div className="flex items-center gap-3">
          {lastUpdated && (
            <span className="text-xs text-vault-dim font-mono">
              Updated {lastUpdated.toLocaleTimeString()}
            </span>
          )}
          <button onClick={fetchStatus} className="btn-ghost text-xs">
            ↺ Refresh
          </button>
        </div>
      </div>

      {/* Backend offline banner */}
      {error && (
        <div className="mb-6 p-4 rounded-xl bg-vault-red/10 border border-vault-red/30 text-vault-red text-sm flex items-center gap-3">
          <span className="text-lg">⚠</span>
          <div>
            <p className="font-semibold">Backend Offline</p>
            <p className="text-xs mt-0.5 font-mono opacity-80">{error}</p>
          </div>
        </div>
      )}

      {/* Queue status cards */}
      <section className="mb-8">
        <p className="text-xs font-semibold uppercase tracking-widest text-vault-dim mb-3">
          Vault Queue Counts
        </p>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
          {QUEUE_META.map((m) => (
            <StatusCard
              key={m.key}
              icon={m.icon}
              label={m.label}
              count={q[m.key]}
              color={m.color}
              borderColor={m.borderColor}
              description={m.description}
              loading={loading}
            />
          ))}
        </div>
      </section>

      {/* Action buttons */}
      <section className="mb-8">
        <p className="text-xs font-semibold uppercase tracking-widest text-vault-dim mb-3">
          Actions
        </p>
        <div className="flex flex-wrap gap-3">
          <button onClick={handleGenerate} disabled={genLoading} className="btn-cyan">
            {genLoading ? '⟳ Generating…' : '⊕ Generate Evidence Pack'}
          </button>
          <button onClick={handleOpenProof} className="btn-purple">
            ◉ Open Judge Proof
          </button>
          <a
            href={`${process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'}/docs`}
            target="_blank"
            rel="noopener noreferrer"
            className="btn-ghost"
          >
            ↗ API Docs
          </a>
        </div>

        {genError && (
          <p className="mt-3 text-sm text-vault-red font-mono">✗ {genError}</p>
        )}
        {genResult && (
          <div className="mt-3 p-4 rounded-xl bg-vault-green/5 border border-vault-green/20 text-sm">
            <p className="text-vault-green font-semibold">✓ Evidence pack generated</p>
            <p className="font-mono text-xs text-vault-muted mt-1">{genResult.path}</p>
            {genResult.snippet && (
              <pre className="mt-2 log-line text-vault-muted bg-vault-bg p-3 rounded-lg overflow-auto max-h-32">
                {genResult.snippet}
              </pre>
            )}
          </div>
        )}
      </section>

      {/* Two-column bottom section */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Cloud Agent heartbeat */}
        <div className="vault-card p-5">
          <div className="flex items-center justify-between mb-4">
            <p className="text-sm font-semibold text-vault-text flex items-center gap-2">
              <span className="text-vault-green text-base">☁</span>
              Cloud Agent Heartbeat
            </p>
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-vault-green opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-vault-green" />
            </span>
          </div>
          {loading ? (
            <div className="space-y-2">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-3 bg-vault-border animate-pulse rounded" style={{ width: `${80 - i * 10}%` }} />
              ))}
            </div>
          ) : status?.cloud_updates?.length ? (
            <div className="space-y-1 font-mono text-xs text-vault-muted">
              {status.cloud_updates.slice(-6).map((line, i) => (
                <p key={i} className="log-line text-vault-muted/80">{line}</p>
              ))}
            </div>
          ) : (
            <p className="text-xs text-vault-dim font-mono">No heartbeat data yet.</p>
          )}
        </div>

        {/* Last executions */}
        <div className="vault-card p-5">
          <p className="text-sm font-semibold text-vault-text flex items-center gap-2 mb-4">
            <span className="text-vault-cyan text-base">≡</span>
            Last Executions
          </p>
          {loading ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-10 bg-vault-border animate-pulse rounded-lg" />
              ))}
            </div>
          ) : status?.last_executions?.length ? (
            <div className="space-y-2">
              {status.last_executions.slice(-5).map((entry, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between p-2.5 rounded-lg bg-vault-bg border border-vault-border/60 text-xs"
                >
                  <div className="min-w-0 mr-3">
                    <p className="font-mono text-vault-text truncate">
                      {String(entry.id ?? entry.task_type ?? '—').slice(0, 28)}
                    </p>
                    <p className="text-vault-dim mt-0.5">
                      {String(entry.task_type ?? '')} · {ts(String(entry.timestamp ?? ''))}
                    </p>
                  </div>
                  {resultBadge(String(entry.result ?? ''))}
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-vault-dim font-mono">No executions yet.</p>
          )}
        </div>
      </div>

      {/* Watchdog health */}
      {(status?.last_health || status?.watchdog) && (
        <section className="mt-6">
          <p className="text-xs font-semibold uppercase tracking-widest text-vault-dim mb-3">
            Watchdog Health
          </p>
          <div className="vault-card p-5">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
              {(['cloud_agent', 'gmail_watcher', 'local_executor'] as const).map((key) => {
                // 1st choice: status.watchdog[key] (backend-computed, 30 s window)
                const wd   = status?.watchdog?.[key];
                // 2nd choice (cloud_agent only): last_heartbeat freshness vs status.time
                const heartbeatAlive =
                  key === 'cloud_agent' &&
                  !wd &&
                  !!status?.last_heartbeat &&
                  !!status?.time &&
                  (new Date(status.time).getTime() - new Date(status.last_heartbeat).getTime()) < 15_000;
                // 3rd choice: legacy last_health process entry
                const proc = status?.last_health?.[key as keyof typeof status.last_health] as
                  | { alive?: boolean; pid?: number; restarts?: number }
                  | undefined;
                const alive = wd ? wd.status === 'online' : (heartbeatAlive || !!proc?.alive);
                const sub = wd
                  ? (alive ? ts(wd.last_seen ?? undefined) : 'offline')
                  : heartbeatAlive
                    ? ts(status?.last_heartbeat ?? undefined)
                    : (alive ? `PID ${proc?.pid ?? '?'}` : 'offline');
                return (
                  <div key={key} className="flex items-center gap-2.5">
                    <span className={`w-2 h-2 rounded-full shrink-0 ${alive ? 'bg-vault-green' : 'bg-vault-red'}`} />
                    <div>
                      <p className="font-medium text-vault-text capitalize">
                        {key.replace(/_/g, ' ')}
                      </p>
                      <p className="text-vault-dim font-mono">
                        {sub}
                        {!wd && !heartbeatAlive && (proc?.restarts ?? 0) > 0 && ` · ${proc?.restarts}↺`}
                      </p>
                    </div>
                  </div>
                );
              })}
              <div className="flex items-center gap-2.5">
                <span className="w-2 h-2 rounded-full shrink-0 bg-vault-cyan" />
                <div>
                  <p className="font-medium text-vault-text">Cycle</p>
                  <p className="text-vault-dim font-mono">
                    #{(status?.last_health as Record<string, unknown> | null | undefined)?.['cycle'] as number ?? '—'}
                  </p>
                </div>
              </div>
            </div>
          </div>
        </section>
      )}

      {/* Debug info bar — shows API base URL + key status fields for dev/judges */}
      <div className="mt-6 p-3 rounded-lg bg-vault-bg border border-vault-border/30 font-mono text-xs text-vault-dim space-y-0.5">
        <p><span className="text-vault-muted">api_base:</span> {getBackendUrl()}</p>
        <p><span className="text-vault-muted">status_time:</span> {status?.time ?? '—'}</p>
        <p><span className="text-vault-muted">agent_status:</span> {status?.agent_status ?? '—'}</p>
        <p><span className="text-vault-muted">last_heartbeat:</span> {status?.last_heartbeat ?? '—'}</p>
        <p><span className="text-vault-muted">watchdog.cloud_agent:</span> {status?.watchdog?.cloud_agent?.status ?? '—'}</p>
      </div>

      {/* Judge Proof modal */}
      {proofOpen && (
        <div
          className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-6"
          onClick={(e) => { if (e.target === e.currentTarget) setProofOpen(false); }}
        >
          <div className="bg-vault-surface border border-vault-border rounded-2xl w-full max-w-3xl max-h-[80vh] flex flex-col animate-fade-in">
            <div className="flex items-center justify-between px-6 py-4 border-b border-vault-border">
              <p className="font-semibold text-vault-text">◉ Evidence/JUDGE_PROOF.md</p>
              <button onClick={() => setProofOpen(false)} className="text-vault-muted hover:text-vault-text text-xl">✕</button>
            </div>
            <div className="flex-1 overflow-auto p-6">
              {proofLoading ? (
                <div className="space-y-2">
                  {[1, 2, 3, 4, 5].map((i) => (
                    <div key={i} className="h-3 bg-vault-border animate-pulse rounded" />
                  ))}
                </div>
              ) : (
                <pre className="log-line text-vault-muted whitespace-pre-wrap">{proofText}</pre>
              )}
            </div>
          </div>
        </div>
      )}
    </main>
  );
}

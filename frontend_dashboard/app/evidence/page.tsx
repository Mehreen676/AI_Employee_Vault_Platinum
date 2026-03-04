'use client';

import { useCallback, useEffect, useState } from 'react';
import { api, getBackendUrl } from '@/lib/api';
import type { EvidenceFile, GenerateEvidenceResponse } from '@/lib/types';

function fmtBytes(b: number) {
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / 1024 / 1024).toFixed(2)} MB`;
}

function fileIcon(suffix: string) {
  switch (suffix) {
    case '.md':  return '◈';
    case '.png': return '◉';
    case '.gif': return '▶';
    case '.json': return '{ }';
    default:      return '◻';
  }
}

function fileColor(suffix: string) {
  switch (suffix) {
    case '.md':   return 'text-vault-cyan   border-vault-cyan/30   bg-vault-cyan/5';
    case '.png':  return 'text-vault-purple  border-vault-purple/30 bg-vault-purple/5';
    case '.gif':  return 'text-vault-gold    border-vault-gold/30   bg-vault-gold/5';
    case '.json': return 'text-vault-green   border-vault-green/30  bg-vault-green/5';
    default:      return 'text-vault-muted   border-vault-border    bg-vault-surface';
  }
}

export default function EvidencePage() {
  const [files, setFiles]           = useState<EvidenceFile[]>([]);
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState<string | null>(null);

  const [genLoading, setGenLoading] = useState(false);
  const [genResult, setGenResult]   = useState<GenerateEvidenceResponse | null>(null);
  const [genError, setGenError]     = useState<string | null>(null);

  const [previewFile, setPreviewFile] = useState<EvidenceFile | null>(null);
  const [previewContent, setPreviewContent] = useState('');
  const [previewLoading, setPreviewLoading] = useState(false);

  const fetchFiles = useCallback(async () => {
    try {
      const r = await api.evidenceList();
      setFiles(r.files);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to list evidence files');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchFiles();
  }, [fetchFiles]);

  const handleGenerate = async () => {
    setGenLoading(true);
    setGenError(null);
    setGenResult(null);
    try {
      const r = await api.evidenceGenerate(20);
      setGenResult(r);
      await fetchFiles();
    } catch (e) {
      setGenError(e instanceof Error ? e.message : 'Generation failed');
    } finally {
      setGenLoading(false);
    }
  };

  const handlePreview = async (file: EvidenceFile) => {
    if (file.suffix === '.png' || file.suffix === '.gif') {
      setPreviewFile(file);
      setPreviewContent('');
      return;
    }
    if (file.suffix === '.md' || file.suffix === '.json' || file.suffix === '.txt') {
      setPreviewFile(file);
      setPreviewLoading(true);
      try {
        if (file.filename === 'JUDGE_PROOF.md') {
          const txt = await api.evidenceJudgeProof();
          setPreviewContent(txt);
        } else {
          setPreviewContent(`Preview not available for ${file.filename}.\n\nDownload to view.`);
        }
      } catch {
        setPreviewContent('Failed to load preview.');
      } finally {
        setPreviewLoading(false);
      }
      return;
    }
    setPreviewFile(file);
    setPreviewContent('');
  };

  const BASE = getBackendUrl();

  return (
    <main className="flex-1 px-8 py-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-vault-text">Evidence Artifacts</h1>
          <p className="text-sm text-vault-muted mt-1">
            Judge-ready proof files from Evidence/
          </p>
        </div>
        <div className="flex gap-3">
          <button onClick={handleGenerate} disabled={genLoading} className="btn-cyan">
            {genLoading ? '⟳ Generating…' : '⊕ Generate Evidence Pack'}
          </button>
          <button onClick={fetchFiles} className="btn-ghost text-xs">↺ Refresh</button>
        </div>
      </div>

      {error && (
        <div className="mb-4 p-3 rounded-xl bg-vault-red/10 border border-vault-red/30 text-vault-red text-sm">
          ⚠ {error}
        </div>
      )}

      {genError && (
        <div className="mb-4 p-3 rounded-xl bg-vault-red/10 border border-vault-red/30 text-vault-red text-sm font-mono">
          ✗ {genError}
        </div>
      )}

      {genResult && (
        <div className="mb-6 p-4 rounded-xl bg-vault-green/5 border border-vault-green/20 text-sm">
          <p className="text-vault-green font-semibold">✓ Evidence pack generated</p>
          <p className="font-mono text-xs text-vault-muted mt-1">{genResult.path}</p>
          {genResult.snippet && (
            <pre className="mt-2 log-line text-vault-muted bg-vault-bg p-3 rounded-lg overflow-auto max-h-28 text-[11px]">
              {genResult.snippet}
            </pre>
          )}
        </div>
      )}

      {/* File grid */}
      {loading ? (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-32 bg-vault-surface border border-vault-border animate-pulse rounded-xl" />
          ))}
        </div>
      ) : files.length === 0 ? (
        <div className="vault-card p-12 text-center">
          <p className="text-4xl mb-3 opacity-30">◻</p>
          <p className="text-vault-muted">No evidence files found.</p>
          <p className="text-xs text-vault-dim mt-1">
            Run: <code className="font-mono bg-vault-bg px-1.5 py-0.5 rounded">python scripts/generate_evidence_pack.py --n 20</code>
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
          {files.map((file) => {
            const cls = fileColor(file.suffix);
            return (
              <div
                key={file.filename}
                className={`vault-card p-4 border cursor-pointer transition-all duration-150
                             hover:scale-[1.02] ${cls}`}
                onClick={() => handlePreview(file)}
              >
                <div className="flex items-start justify-between mb-3">
                  <span className="text-xl font-mono">{fileIcon(file.suffix)}</span>
                  <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-black/20">
                    {file.suffix}
                  </span>
                </div>
                <p className="font-mono text-xs font-medium break-all leading-relaxed mb-2">
                  {file.filename}
                </p>
                <p className="text-[10px] opacity-60">{fmtBytes(file.size_bytes)}</p>

                {/* Quick-access links for judge-proof */}
                {file.filename === 'JUDGE_PROOF.md' && (
                  <div className="mt-3 pt-3 border-t border-current/10 flex gap-2">
                    <button
                      onClick={(e) => { e.stopPropagation(); handlePreview(file); }}
                      className="text-[10px] font-medium hover:underline"
                    >
                      Preview
                    </button>
                    <a
                      href={`${BASE}/evidence/judge-proof`}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={(e) => e.stopPropagation()}
                      className="text-[10px] font-medium hover:underline ml-auto"
                    >
                      Raw ↗
                    </a>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Preview modal */}
      {previewFile && (
        <div
          className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-6"
          onClick={(e) => { if (e.target === e.currentTarget) setPreviewFile(null); }}
        >
          <div className="bg-vault-surface border border-vault-border rounded-2xl w-full max-w-4xl max-h-[85vh] flex flex-col animate-fade-in">
            {/* Modal header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-vault-border">
              <div className="flex items-center gap-3">
                <span className="text-lg font-mono">{fileIcon(previewFile.suffix)}</span>
                <div>
                  <p className="font-mono text-sm font-medium text-vault-text">{previewFile.filename}</p>
                  <p className="text-xs text-vault-dim">{fmtBytes(previewFile.size_bytes)}</p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                {(previewFile.suffix === '.md' || previewFile.suffix === '.json') && (
                  <a
                    href={`${BASE}/evidence/judge-proof`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="btn-ghost text-xs"
                  >
                    Open Raw ↗
                  </a>
                )}
                <button
                  onClick={() => setPreviewFile(null)}
                  className="text-vault-muted hover:text-vault-text text-xl leading-none"
                >
                  ✕
                </button>
              </div>
            </div>

            {/* Modal body */}
            <div className="flex-1 overflow-auto p-6">
              {previewLoading ? (
                <div className="space-y-2">
                  {Array.from({ length: 6 }).map((_, i) => (
                    <div key={i} className="h-3 bg-vault-border animate-pulse rounded" />
                  ))}
                </div>
              ) : previewFile.suffix === '.png' ? (
                /* PNG rendered from backend URL */
                <div className="flex items-center justify-center">
                  <img
                    src={`${BASE}/evidence/list`}
                    alt={previewFile.filename}
                    className="max-w-full rounded-xl border border-vault-border"
                    onError={(e) => {
                      (e.target as HTMLImageElement).style.display = 'none';
                    }}
                  />
                  <p className="text-vault-muted text-sm text-center">
                    PNG preview — download to view full resolution<br />
                    <span className="font-mono text-xs">{previewFile.filename}</span>
                  </p>
                </div>
              ) : previewContent ? (
                <pre className="log-line text-vault-muted whitespace-pre-wrap text-[11px]">
                  {previewContent}
                </pre>
              ) : (
                <p className="text-vault-muted text-sm text-center py-8">
                  No preview available for this file type.
                </p>
              )}
            </div>
          </div>
        </div>
      )}
    </main>
  );
}

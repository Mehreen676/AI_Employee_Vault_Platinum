'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';
import { api } from '@/lib/api';

const NAV = [
  { href: '/',          icon: '◈', label: 'Overview',   desc: 'System status' },
  { href: '/approvals', icon: '⊕', label: 'Approvals',  desc: 'HITL queue' },
  { href: '/logs',      icon: '≡', label: 'Logs',       desc: 'Execution & health' },
  { href: '/evidence',  icon: '◉', label: 'Evidence',   desc: 'Proofs & artifacts' },
];

export function Sidebar() {
  const pathname = usePathname();
  const [online, setOnline] = useState<boolean | null>(null);
  const [version, setVersion] = useState('');

  useEffect(() => {
    const check = async () => {
      try {
        const h = await api.health();
        setOnline(true);
        setVersion(h.version);
      } catch {
        setOnline(false);
      }
    };
    check();
    const id = setInterval(check, 10_000);
    return () => clearInterval(id);
  }, []);

  return (
    <aside className="fixed inset-y-0 left-0 z-40 w-60 flex flex-col
                      bg-vault-surface border-r border-vault-border
                      select-none shrink-0">
      {/* Logo */}
      <div className="px-5 py-5 border-b border-vault-border">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-vault-cyan/10 border border-vault-cyan/30
                          flex items-center justify-center text-vault-cyan text-lg">
            ◈
          </div>
          <div>
            <p className="text-sm font-semibold text-vault-text leading-tight">AI Vault</p>
            <p className="text-xs text-vault-cyan font-mono leading-tight">Platinum Tier</p>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        <p className="px-2 pb-2 text-[10px] font-semibold uppercase tracking-widest text-vault-dim">
          Navigation
        </p>
        {NAV.map(({ href, icon, label, desc }) => {
          const active = href === '/' ? pathname === '/' : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={`group flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm
                          transition-all duration-150
                          ${active
                            ? 'bg-vault-cyan/10 text-vault-cyan border border-vault-cyan/25'
                            : 'text-vault-muted hover:text-vault-text hover:bg-white/5 border border-transparent'
                          }`}
            >
              <span className={`text-base w-5 text-center shrink-0 ${active ? 'text-vault-cyan' : ''}`}>
                {icon}
              </span>
              <div className="min-w-0">
                <p className="font-medium leading-tight">{label}</p>
                <p className={`text-[10px] leading-tight mt-0.5 ${active ? 'text-vault-cyan/70' : 'text-vault-dim'}`}>
                  {desc}
                </p>
              </div>
              {active && (
                <div className="ml-auto w-1 h-4 rounded-full bg-vault-cyan shrink-0" />
              )}
            </Link>
          );
        })}
      </nav>

      {/* Backend status */}
      <div className="px-4 py-4 border-t border-vault-border">
        <div className="flex items-center gap-2.5">
          <span className="relative flex h-2 w-2 shrink-0">
            <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75
                             ${online === true ? 'bg-vault-green' : online === false ? 'bg-vault-red' : 'bg-vault-gold'}`} />
            <span className={`relative inline-flex rounded-full h-2 w-2
                             ${online === true ? 'bg-vault-green' : online === false ? 'bg-vault-red' : 'bg-vault-gold'}`} />
          </span>
          <div className="min-w-0">
            <p className="text-xs font-medium text-vault-text truncate">
              {online === null ? 'Connecting…' : online ? 'Backend Online' : 'Backend Offline'}
            </p>
            {version && (
              <p className="text-[10px] text-vault-dim font-mono">v{version}</p>
            )}
          </div>
        </div>
        <p className="mt-2 text-[10px] text-vault-dim font-mono truncate">
          {process.env.NEXT_PUBLIC_BACKEND_URL || 'localhost:7860'}
        </p>
      </div>
    </aside>
  );
}

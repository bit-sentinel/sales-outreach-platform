'use client';

import Link from 'next/link';
import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { Bell, CheckCircle2, MessageSquare, Search, Sparkles, TrendingUp, UserPlus, X, Zap } from 'lucide-react';
import { useAuthStore } from '@/stores/auth-store';
import { useChatStore } from '@/stores/chat-store';
import { api } from '@/lib/api-client';
import { cn } from '@/lib/utils';

const pageMeta: Record<string, { title: string; description: string }> = {
  '/dashboard': { title: 'Revenue command center', description: 'Pipeline flow, campaign execution, and AI briefings at a glance.' },
  '/leads':     { title: 'Lead operations',         description: 'Import, qualify, and route target accounts.' },
  '/campaigns': { title: 'Campaign orchestration',  description: 'Control sequences, sending velocity, and performance.' },
  '/replies':   { title: 'Reply triage',            description: 'Triage buying signals and meeting requests before momentum fades.' },
  '/analytics': { title: 'Performance intelligence', description: 'See what is compounding and where the funnel leaks.' },
  '/settings':  { title: 'Workspace controls',      description: 'Manage people, sending systems, AI policies, and access.' },
};

export function Header() {
  const pathname = usePathname();
  const router    = useRouter();
  const { user }  = useAuthStore();
  const meta = pageMeta[pathname] ?? pageMeta['/dashboard'];

  const [searchOpen,  setSearchOpen]  = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [notifOpen,   setNotifOpen]   = useState(false);
  const [notifItems,  setNotifItems]  = useState<Array<{ id: string; type: string; title: string; time: string }>>([]);
  const { open: chatOpen, toggle: toggleChat, hasMessages } = useChatStore();

  const inputRef = useRef<HTMLInputElement>(null);
  const notifRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api<Array<{ id: string; type: string; title: string; time: string }>>({
      method: 'GET', url: '/analytics/recent-activity', params: { limit: 6 },
    }).then(setNotifItems).catch(() => setNotifItems([]));
  }, []);

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (notifRef.current && !notifRef.current.contains(e.target as Node)) setNotifOpen(false);
    }
    if (notifOpen) document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [notifOpen]);

  const notifTypeIcon: Record<string, React.ElementType> = {
    import: UserPlus, enrichment: Zap, scoring: TrendingUp, email: CheckCircle2,
  };

  function openSearch() { setSearchOpen(true); setTimeout(() => inputRef.current?.focus(), 50); }
  function commitSearch() {
    const q = searchQuery.trim();
    setSearchOpen(false); setSearchQuery('');
    if (q) router.push(`/leads?q=${encodeURIComponent(q)}`);
  }
  function handleKey(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter') commitSearch();
    if (e.key === 'Escape') { setSearchOpen(false); setSearchQuery(''); }
  }

  return (
    <header className="sticky top-0 z-10 border-b border-white/[0.06] backdrop-blur-xl" style={{ background: 'rgba(7,11,20,0.85)' }}>
      <div className="mx-auto flex w-full max-w-[1480px] items-center gap-4 px-5 py-3.5 lg:px-7">
        {/* ── Page title ──────────────────────────────── */}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2.5">
            <h2 className="text-[1.05rem] font-bold tracking-tight text-white leading-none">{meta.title}</h2>
            <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-bold text-emerald-400 border border-emerald-500/20">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
              AI online
            </span>
          </div>
          <p className="mt-0.5 text-[11px] text-white/40 hidden sm:block">{meta.description}</p>
        </div>

        {/* ── Search ──────────────────────────────────── */}
        {!['/campaigns', '/analytics', '/replies'].includes(pathname) && (
          <div className="hidden items-center gap-2 md:flex">
            {searchOpen ? (
              <div className="flex items-center gap-2 rounded-xl border border-indigo-500/40 bg-white/[0.07] px-3 py-2 ring-2 ring-indigo-500/20 w-64">
                <Search className="h-3.5 w-3.5 text-indigo-400 flex-shrink-0" />
                <input
                  ref={inputRef}
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyDown={handleKey}
                  onBlur={() => { if (!searchQuery) setSearchOpen(false); }}
                  placeholder="Search leads, companies…"
                  className="flex-1 bg-transparent text-sm text-white placeholder:text-white/30 outline-none min-w-0"
                />
                <button onClick={() => { setSearchOpen(false); setSearchQuery(''); }}>
                  <X className="h-3.5 w-3.5 text-white/30 hover:text-white/60" />
                </button>
              </div>
            ) : (
              <button
                onClick={openSearch}
                className="flex items-center gap-2 rounded-xl border border-white/[0.1] bg-white/[0.05] px-3 py-2 text-sm text-white/50 hover:bg-white/[0.08] hover:text-white/70 transition-colors"
              >
                <Search className="h-3.5 w-3.5" />
                <span className="text-xs">Search…</span>
                <kbd className="ml-1 rounded-md border border-white/[0.1] bg-white/[0.05] px-1.5 py-0.5 text-[10px] font-mono text-white/30">⌘K</kbd>
              </button>
            )}
          </div>
        )}

        {/* ── Actions ─────────────────────────────────── */}
        <div className="flex items-center gap-2">
          {/* AI copilot pill */}
          <div className="hidden items-center gap-1.5 rounded-xl border border-violet-500/20 bg-violet-500/10 px-3 py-1.5 text-xs font-semibold text-violet-400 xl:flex">
            <Sparkles className="h-3.5 w-3.5" />
            {user?.first_name ? `${user.first_name}'s copilot` : 'AI copilot'}
          </div>

          {/* AI assistant */}
          <button
            onClick={toggleChat}
            className={cn(
              'relative flex h-9 w-9 items-center justify-center rounded-xl border transition-all',
              chatOpen
                ? 'border-indigo-500/50 bg-indigo-500/15 text-indigo-400'
                : 'border-white/[0.1] bg-white/[0.05] text-white/50 hover:bg-white/[0.09] hover:text-white/80',
            )}
            aria-label="AI assistant"
          >
            <MessageSquare className="h-4 w-4" />
            {!chatOpen && hasMessages && (
              <span className="absolute right-1.5 top-1.5 h-1.5 w-1.5 rounded-full bg-indigo-400" />
            )}
          </button>

          {/* Notifications */}
          <div className="relative" ref={notifRef}>
            <button
              onClick={() => setNotifOpen((v) => !v)}
              className="relative flex h-9 w-9 items-center justify-center rounded-xl border border-white/[0.1] bg-white/[0.05] text-white/50 transition-all hover:bg-white/[0.09] hover:text-white/80"
            >
              <Bell className="h-4 w-4" />
              {notifItems.length > 0 && (
                <span className="absolute right-2 top-2 h-1.5 w-1.5 rounded-full bg-rose-500" />
              )}
            </button>

            {notifOpen && (
              <div className="absolute right-0 top-full mt-2 z-50 w-80 rounded-2xl border border-white/[0.1] overflow-hidden shadow-2xl" style={{ background: '#0d1525' }}>
                <div className="flex items-center justify-between border-b border-white/[0.07] px-4 py-3">
                  <p className="text-sm font-semibold text-white">Recent Activity</p>
                  <button onClick={() => setNotifOpen(false)} className="text-white/30 hover:text-white/70 transition-colors">
                    <X className="h-4 w-4" />
                  </button>
                </div>
                {notifItems.length === 0 ? (
                  <div className="px-4 py-8 text-center">
                    <p className="text-sm text-white/40">No recent activity</p>
                  </div>
                ) : (
                  <div className="max-h-72 overflow-y-auto divide-y divide-white/[0.05]">
                    {notifItems.map((item) => {
                      const Icon = notifTypeIcon[item.type] ?? CheckCircle2;
                      return (
                        <div key={item.id} className="flex items-start gap-3 px-4 py-3 hover:bg-white/[0.04] transition-colors">
                          <div className="mt-0.5 flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-lg bg-indigo-500/20">
                            <Icon className="h-3.5 w-3.5 text-indigo-400" />
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className="text-xs text-white/70 leading-snug">{item.title}</p>
                            <p className="mt-0.5 text-[11px] text-white/35">{item.time}</p>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
                <div className="border-t border-white/[0.07] px-4 py-2.5">
                  <Link href="/leads" onClick={() => setNotifOpen(false)} className="text-xs font-semibold text-indigo-400 hover:text-indigo-300 transition-colors">
                    View all activity →
                  </Link>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}

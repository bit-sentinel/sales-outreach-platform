'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import {
  BarChart3,
  ChevronRight,
  Inbox,
  LayoutDashboard,
  LogOut,
  Settings,
  Sparkles,
  Target,
  Users,
  Zap,
  Activity,
  Circle,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useAuthStore } from '@/stores/auth-store';
import { api } from '@/lib/api-client';

const navItems = [
  { name: 'Dashboard',  href: '/dashboard',  icon: LayoutDashboard, sub: 'Overview & briefing'      },
  { name: 'Leads',      href: '/leads',       icon: Users,           sub: 'Import, enrich, score'    },
  { name: 'Campaigns',  href: '/campaigns',   icon: Zap,             sub: 'Automated sequences'      },
  { name: 'Replies',    href: '/replies',     icon: Inbox,           sub: 'Triage & respond'         },
  { name: 'Analytics',  href: '/analytics',   icon: BarChart3,       sub: 'Signals & conversion'     },
  { name: 'Settings',   href: '/settings',    icon: Settings,        sub: 'Workspace controls'       },
];

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout } = useAuthStore();
  const [unreadReplies, setUnreadReplies] = useState(0);

  type SystemHealth = {
    score: number;
    status: 'healthy' | 'degraded' | 'unhealthy';
    components: {
      database: { online: boolean };
      redis: { online: boolean; latency_ms: number | null };
      workers: {
        online: boolean;
        worker_count: number;
        queues: Record<string, { online: boolean; workers: number; label: string }>;
      };
    };
  };
  const [health, setHealth] = useState<SystemHealth | null>(null);

  useEffect(() => {
    function fetchReplies() {
      api<{ unread: number }>({ method: 'GET', url: '/replies/count' })
        .then((res) => setUnreadReplies(res?.unread ?? 0))
        .catch(() => {});
    }
    function fetchHealth() {
      api<SystemHealth>({ method: 'GET', url: '/system/health' })
        .then(setHealth)
        .catch(() => setHealth(null));
    }
    fetchReplies();
    fetchHealth();
    const t1 = setInterval(fetchReplies, 30000);
    const t2 = setInterval(fetchHealth, 30000);
    return () => { clearInterval(t1); clearInterval(t2); };
  }, []);

  const emailPrefix = user?.email?.split('@')[0] ?? '';
  const displayName = user?.first_name && user?.last_name
    ? `${user.first_name} ${user.last_name}`
    : emailPrefix.replace(/[._-]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()) || 'Admin';
  const initials = displayName.split(' ').map((s) => s[0]).join('').toUpperCase().slice(0, 2) || 'OA';

  const handleLogout = () => { logout(); router.push('/login'); };

  return (
    <aside
      className="z-20 flex flex-col border-b border-white/5 lg:w-[248px] lg:flex-shrink-0 lg:border-b-0 lg:border-r"
      style={{ background: 'var(--sidebar-bg)' }}
    >
      {/* ── Logo ──────────────────────────────────────── */}
      <div className="flex items-center gap-3 px-5 py-5 border-b border-white/5">
        <div
          className="flex h-9 w-9 items-center justify-center rounded-xl flex-shrink-0"
          style={{ background: 'linear-gradient(135deg, #1c8ed4 0%, #0d5fa8 100%)', boxShadow: '0 6px 18px rgba(28,142,212,0.35)' }}
        >
          <Target className="h-4.5 w-4.5 text-white" style={{ width: '18px', height: '18px' }} />
        </div>
        <div className="min-w-0">
          <p className="text-[10px] font-bold tracking-[0.16em] uppercase" style={{ color: 'rgba(255,255,255,0.32)' }}>
            Outreach OS
          </p>
          <p className="text-sm font-bold text-white leading-tight tracking-tight">LaunchHouse</p>
        </div>
        <div className="ml-auto hidden lg:flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold" style={{ background: 'rgba(5,150,105,0.2)', color: '#34d399' }}>
          <Circle className="h-1.5 w-1.5 fill-current" />
          Live
        </div>
      </div>

      {/* ── Mobile nav (horizontal scroll) ─────────────── */}
      <div className="flex gap-1.5 overflow-x-auto px-3 py-2.5 border-b border-white/5 lg:hidden">
        {navItems.map((item) => {
          const isActive = pathname === item.href || pathname.startsWith(`${item.href}/`);
          return (
            <Link
              key={item.name}
              href={item.href}
              className={cn(
                'flex min-w-fit items-center gap-2 rounded-xl px-3 py-2 text-xs font-semibold transition-all whitespace-nowrap',
                isActive ? 'bg-white/12 text-white' : 'text-white/50 hover:text-white/80 hover:bg-white/6'
              )}
            >
              <item.icon className="h-3.5 w-3.5" />
              {item.name}
              {item.name === 'Replies' && unreadReplies > 0 && (
                <span className="rounded-full bg-rose-500 px-1.5 py-0.5 text-[9px] font-bold text-white leading-none">{unreadReplies}</span>
              )}
            </Link>
          );
        })}
      </div>

      {/* ── Desktop nav ─────────────────────────────────── */}
      <nav className="hidden flex-1 flex-col overflow-y-auto px-3 py-4 lg:flex">
        <p className="px-3 pb-2 text-[10px] font-bold tracking-[0.14em] uppercase" style={{ color: 'rgba(255,255,255,0.25)' }}>
          Navigate
        </p>
        <div className="space-y-0.5">
          {navItems.map((item) => {
            const isActive = pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.name}
                href={item.href}
                className={cn(
                  'group flex items-center gap-3 rounded-xl px-3 py-2.5 transition-all duration-150',
                  isActive
                    ? 'text-white'
                    : 'text-white/55 hover:text-white/85'
                )}
                style={isActive ? { background: 'rgba(255,255,255,0.09)' } : {}}
                onMouseEnter={(e) => { if (!isActive) (e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.045)'; }}
                onMouseLeave={(e) => { if (!isActive) (e.currentTarget as HTMLElement).style.background = ''; }}
              >
                <div
                  className="flex h-8 w-8 items-center justify-center rounded-lg flex-shrink-0 transition-all"
                  style={{
                    background: isActive ? 'rgba(255,255,255,0.14)' : 'rgba(255,255,255,0.06)',
                  }}
                >
                  <item.icon className="h-4 w-4" style={{ color: isActive ? '#ffffff' : 'rgba(255,255,255,0.55)' }} />
                </div>
                <div className="min-w-0 flex-1">
                  <p className={cn('text-sm font-semibold leading-none', isActive ? 'text-white' : '')}>{item.name}</p>
                  <p className="mt-0.5 text-[11px] truncate" style={{ color: isActive ? 'rgba(255,255,255,0.45)' : 'rgba(255,255,255,0.30)' }}>
                    {item.sub}
                  </p>
                </div>
                <div className="flex items-center gap-1.5 flex-shrink-0">
                  {item.name === 'Replies' && unreadReplies > 0 && (
                    <span className="rounded-full bg-rose-500 px-2 py-0.5 text-[10px] font-bold text-white leading-none">
                      {unreadReplies}
                    </span>
                  )}
                  <ChevronRight
                    className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5"
                    style={{ color: isActive ? 'rgba(255,255,255,0.35)' : 'rgba(255,255,255,0.18)' }}
                  />
                </div>
              </Link>
            );
          })}
        </div>

        {/* ── AI System Status ──────────────────────────── */}
        <div className="mt-auto pt-4">
          <div
            className="rounded-2xl p-4"
            style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.07)' }}
          >
            <div className="flex items-center gap-2 mb-3">
              <div
                className="flex h-7 w-7 items-center justify-center rounded-lg"
                style={{ background: 'rgba(124,77,204,0.25)' }}
              >
                <Sparkles className="h-3.5 w-3.5" style={{ color: '#a78bfa' }} />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-xs font-semibold text-white/80">AI System</p>
                <p className="text-[10px]" style={{ color: 'rgba(255,255,255,0.35)' }}>
                  {health === null
                    ? 'Checking…'
                    : health.status === 'healthy'
                      ? 'All systems online'
                      : health.status === 'degraded'
                        ? 'Partially degraded'
                        : 'System offline'}
                </p>
              </div>
              <Activity
                className="h-3.5 w-3.5 flex-shrink-0"
                style={{
                  color: health === null
                    ? 'rgba(255,255,255,0.25)'
                    : health.status === 'healthy'
                      ? '#34d399'
                      : health.status === 'degraded'
                        ? '#fbbf24'
                        : '#f87171',
                }}
              />
            </div>

            {/* Component dots */}
            {health && (
              <div className="flex items-center gap-2 mb-3">
                {[
                  { label: 'DB', online: health.components.database.online },
                  { label: 'Redis', online: health.components.redis.online },
                  { label: 'Workers', online: health.components.workers.online },
                ].map(({ label, online }) => (
                  <div key={label} className="flex items-center gap-1">
                    <span
                      className="h-1.5 w-1.5 rounded-full flex-shrink-0"
                      style={{ background: online ? '#34d399' : '#f87171' }}
                    />
                    <span className="text-[9px]" style={{ color: 'rgba(255,255,255,0.30)' }}>{label}</span>
                  </div>
                ))}
                {health.components.workers.online && (
                  <span className="ml-auto text-[9px]" style={{ color: 'rgba(255,255,255,0.25)' }}>
                    {health.components.workers.worker_count}w
                  </span>
                )}
              </div>
            )}

            <div className="h-1 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.08)' }}>
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{
                  width: `${health?.score ?? 0}%`,
                  background: health === null || health.score === 0
                    ? 'rgba(255,255,255,0.15)'
                    : health.status === 'healthy'
                      ? 'linear-gradient(90deg, #1c8ed4, #7c4dcc)'
                      : health.status === 'degraded'
                        ? 'linear-gradient(90deg, #f59e0b, #ef4444)'
                        : '#ef4444',
                }}
              />
            </div>
            <p className="mt-1.5 text-[10px]" style={{ color: 'rgba(255,255,255,0.30)' }}>
              {health === null ? '—' : `${health.score}% operational`}
            </p>
          </div>
        </div>
      </nav>

      {/* ── User / Logout ────────────────────────────────── */}
      <div className="px-3 pb-4 pt-2 hidden lg:block" style={{ borderTop: '1px solid rgba(255,255,255,0.06)' }}>
        <button
          onClick={handleLogout}
          className="flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left transition-all"
          style={{ color: 'rgba(255,255,255,0.55)' }}
          onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.06)'; (e.currentTarget as HTMLElement).style.color = 'rgba(255,255,255,0.85)'; }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = ''; (e.currentTarget as HTMLElement).style.color = 'rgba(255,255,255,0.55)'; }}
        >
          <div
            className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl text-sm font-bold text-white"
            style={{ background: 'linear-gradient(135deg, #c2653b 0%, #0d2540 100%)' }}
          >
            {initials}
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold text-white/80">{displayName}</p>
            <p className="truncate text-[11px]" style={{ color: 'rgba(255,255,255,0.35)' }}>{user?.email ?? ''}</p>
          </div>
          <LogOut className="h-4 w-4 flex-shrink-0" style={{ color: 'rgba(255,255,255,0.25)' }} />
        </button>
      </div>
    </aside>
  );
}

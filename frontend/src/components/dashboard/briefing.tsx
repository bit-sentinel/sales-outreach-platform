'use client';

import { useEffect, useState } from 'react';
import { Orbit, Sparkles, TrendingUp, Mail, Flame, MessagesSquare } from 'lucide-react';
import { api } from '@/lib/api-client';

interface DashboardData {
  hot_leads: number;
  total_leads: number;
  enriched_leads: number;
  active_campaigns: number;
  total_replies: number;
  emails_sent_total: number;
  open_rate: number;
}

export function DashboardBriefing() {
  const [data, setData] = useState<DashboardData | null>(null);

  useEffect(() => {
    api<DashboardData>({ method: 'GET', url: '/analytics/dashboard' })
      .then(setData)
      .catch(() => null);
  }, []);

  const stats = data
    ? [
        { value: String(data.hot_leads),                  label: 'Hot leads',     icon: Flame,           color: '#fb923c' },
        { value: String(data.total_replies),              label: 'Replies',       icon: MessagesSquare,  color: '#34d399' },
        { value: data.emails_sent_total.toLocaleString(), label: 'Sent',          icon: Mail,            color: '#60a5fa' },
        { value: `${data.open_rate}%`,                    label: 'Open rate',     icon: TrendingUp,      color: '#c4b5fd' },
      ]
    : Array(4).fill(null).map((_, i) => ({
        value: '—', label: ['Hot leads','Replies','Sent','Open rate'][i],
        icon: [Flame, MessagesSquare, Mail, TrendingUp][i], color: ['#fb923c','#34d399','#60a5fa','#c4b5fd'][i],
      }));

  return (
    <div
      className="xl:col-span-2 rounded-2xl p-5 text-white"
      style={{
        background: 'linear-gradient(135deg, #0d2540 0%, #09131f 60%, #1c4d73 100%)',
        boxShadow: '0 8px 28px rgba(13,37,64,0.20)',
      }}
    >
      <div className="flex items-center gap-2.5 mb-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-white/10 flex-shrink-0">
          <Sparkles className="h-4 w-4 text-violet-300" />
        </div>
        <div>
          <p className="text-sm font-bold text-white leading-none">AI Daily Briefing</p>
          <p className="text-[11px] mt-0.5" style={{ color: 'rgba(255,255,255,0.40)' }}>Live data · Updated just now</p>
        </div>
        <span
          className="ml-auto inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[10px] font-semibold"
          style={{ background: 'rgba(255,255,255,0.08)', color: 'rgba(255,255,255,0.65)' }}
        >
          <Orbit className="h-3 w-3" />
          System healthy
        </span>
      </div>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {stats.map((stat) => {
          const Icon = stat.icon;
          return (
            <div key={stat.label} className="flex flex-col gap-1.5">
              <div className="flex items-center gap-1.5">
                <Icon className="h-3.5 w-3.5 flex-shrink-0" style={{ color: stat.color }} />
                <p className="text-[11px]" style={{ color: 'rgba(255,255,255,0.42)' }}>{stat.label}</p>
              </div>
              <p
                className="text-2xl font-extrabold leading-none tabular-nums tracking-tight"
                style={{ color: stat.color }}
              >
                {stat.value}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

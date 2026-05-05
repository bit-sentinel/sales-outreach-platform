'use client';

import { useEffect, useState } from 'react';
import {
  AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import { TrendingUp, Mail, MessageSquare, MousePointerClick, Users, Loader2, BarChart2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { api } from '@/lib/api-client';

interface AnalyticsData {
  kpis: {
    total_sent: number;
    avg_open_rate: number;
    avg_reply_rate: number;
    total_leads: number;
  };
  campaign_performance: Array<{ name: string; openRate: number; replyRate: number; sent: number }>;
  lead_sources: Array<{ name: string; value: number; color: string }>;
  reply_intent: Array<{ intent: string; count: number; color: string }>;
  weekly_sent: Array<{ week: string; sent: number }>;
}

const CustomTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    return (
      <div className="rounded-2xl border border-white/[0.1] bg-[#111827]/95 px-3 py-2.5 shadow-xl text-xs backdrop-blur-sm">
        <p className="font-semibold text-white mb-1">{label}</p>
        {payload.map((p: any) => (
          <div key={p.dataKey} className="flex items-center gap-2 py-0.5">
            <div className="h-2 w-2 rounded-full" style={{ backgroundColor: p.color }} />
            <span className="text-white/50 capitalize">{p.name ?? p.dataKey}</span>
            <span className="ml-auto font-semibold text-white tabular-nums">
              {typeof p.value === 'number' && p.value < 100 && String(p.dataKey).includes('Rate')
                ? `${p.value}%`
                : p.value?.toLocaleString()}
            </span>
          </div>
        ))}
      </div>
    );
  }
  return null;
};

export default function AnalyticsPage() {
  const [data, setData] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api<{ data: AnalyticsData }>({ method: 'GET', url: '/analytics/page-data' })
      .then((res) => setData((res as any).data ?? res))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, []);

  const kpis = data?.kpis;
  const campaignPerf = data?.campaign_performance ?? [];
  const sourceData = data?.lead_sources ?? [];
  const intentData = data?.reply_intent ?? [];
  const weeklyData = data?.weekly_sent ?? [];

  const metricCards = [
    {
      label: 'Total Sent',
      value: loading ? '—' : (kpis?.total_sent ?? 0).toLocaleString(),
      icon: Mail,
      sub: 'emails delivered',
      accent: '#1c8ed4',
    },
    {
      label: 'Avg Open Rate',
      value: loading ? '—' : `${kpis?.avg_open_rate ?? 0}%`,
      icon: MousePointerClick,
      sub: 'across all campaigns',
      accent: '#059669',
    },
    {
      label: 'Avg Reply Rate',
      value: loading ? '—' : `${kpis?.avg_reply_rate ?? 0}%`,
      icon: MessageSquare,
      sub: 'prospects responded',
      accent: '#7c4dcc',
    },
    {
      label: 'Total Leads',
      value: loading ? '—' : (kpis?.total_leads ?? 0).toLocaleString(),
      icon: Users,
      sub: 'in pipeline',
      accent: '#d97706',
    },
  ];

  return (
    <div className="space-y-5 max-w-[1400px]">
      <section
        className="relative overflow-hidden rounded-2xl p-6 lg:p-7"
        style={{
          background: 'linear-gradient(135deg, #0d2540 0%, #09131f 55%, #1c4d73 100%)',
          boxShadow: '0 8px 32px rgba(13,37,64,0.18)',
        }}
      >
        <div className="pointer-events-none absolute -right-16 -top-16 h-56 w-56 rounded-full bg-white/3" />
        <p className="text-[10px] font-bold uppercase tracking-widest mb-2" style={{ color: 'rgba(255,255,255,0.35)' }}>Intelligence</p>
        <h1 className="text-[1.65rem] font-extrabold tracking-tight text-white leading-tight sm:text-[2rem]">Analytics</h1>
        <p className="mt-2 text-sm leading-relaxed" style={{ color: 'rgba(255,255,255,0.50)' }}>Campaign performance and engagement insights across your entire outreach motion.</p>
      </section>

      {/* KPIs */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {metricCards.map((m) => (
          <div
            key={m.label}
            className="relative overflow-hidden rounded-[24px] p-5 flex flex-col justify-between transition-all hover:-translate-y-0.5"
            style={{
              background: `linear-gradient(135deg, #0d2540 0%, #09131f 50%, ${m.accent} 100%)`,
              boxShadow: '0 6px 24px rgba(13,37,64,0.22)',
              minHeight: '140px',
            }}
          >
            <div className="pointer-events-none absolute -right-8 -top-8 h-28 w-28 rounded-full bg-white/5" />
            <div className="pointer-events-none absolute -bottom-6 right-4 h-20 w-20 rounded-full bg-white/4" />
            <div className="relative flex items-start justify-between">
              <p className="text-xs font-semibold text-white/60">{m.label}</p>
              <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-white/12">
                <m.icon className="h-4 w-4 text-white/80" />
              </div>
            </div>
            <div className="relative">
              <p className="text-3xl font-extrabold tracking-tight tabular-nums text-white">{m.value}</p>
              <p className="mt-1 text-[11px] text-white/45">{m.sub}</p>
            </div>
            <m.icon className="pointer-events-none absolute bottom-4 right-4 h-12 w-12 text-white/[0.05]" />
          </div>
        ))}
      </div>

      {/* Campaign performance */}
      <div className="glass-card rounded-[28px] p-5">
        <h3 className="text-sm font-semibold text-white mb-1">Campaign Performance</h3>
        <p className="text-xs text-white/40 mb-4">Open rate vs reply rate by campaign</p>
        {loading ? (
          <div className="flex items-center justify-center gap-2 py-16 text-white/30">
            <Loader2 className="h-4 w-4 animate-spin" />
            <span className="text-xs">Loading…</span>
          </div>
        ) : campaignPerf.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-2 py-16 text-white/20">
            <BarChart2 className="h-8 w-8" />
            <p className="text-sm text-white/30">No campaign data yet — launch a campaign to see stats here.</p>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={campaignPerf} barCategoryGap="30%">
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
              <XAxis
                dataKey="name"
                tick={{ fontSize: 10, fill: 'rgba(255,255,255,0.3)' }}
                axisLine={false}
                tickLine={false}
                interval={0}
                tickFormatter={(v) => v.length > 18 ? v.slice(0, 17) + '…' : v}
              />
              <YAxis tick={{ fontSize: 11, fill: 'rgba(255,255,255,0.3)' }} axisLine={false} tickLine={false} width={28} unit="%" />
              <Tooltip content={<CustomTooltip />} />
              <Bar dataKey="openRate" name="Open Rate" fill="#6366f1" radius={[4, 4, 0, 0]} />
              <Bar dataKey="replyRate" name="Reply Rate" fill="#f59e0b" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Bottom row */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">

        {/* Weekly sent */}
        <div className="lg:col-span-2 glass-card rounded-[28px] p-5">
          <h3 className="text-sm font-semibold text-white mb-1">Emails Sent by Week</h3>
          <p className="text-xs text-white/40 mb-4">Volume of sent emails over the last 8 weeks</p>
          {loading ? (
            <div className="flex items-center justify-center gap-2 py-16 text-white/30">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span className="text-xs">Loading…</span>
            </div>
          ) : weeklyData.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-2 py-16 text-white/20">
              <TrendingUp className="h-8 w-8" />
              <p className="text-sm text-white/30">No weekly send data yet.</p>
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={180}>
              <AreaChart data={weeklyData}>
                <defs>
                  <linearGradient id="g-sent" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#6366f1" stopOpacity={0.25} />
                    <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                <XAxis dataKey="week" tick={{ fontSize: 11, fill: 'rgba(255,255,255,0.3)' }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 11, fill: 'rgba(255,255,255,0.3)' }} axisLine={false} tickLine={false} width={32} />
                <Tooltip content={<CustomTooltip />} />
                <Area type="monotone" dataKey="sent" name="Sent" stroke="#6366f1" strokeWidth={2} fill="url(#g-sent)" dot={false} />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Lead source + reply intent */}
        <div className="space-y-4">
          <div className="glass-card rounded-[24px] p-4">
            <h3 className="text-sm font-semibold text-white mb-3">Lead Sources</h3>
            {loading ? (
              <div className="flex items-center justify-center py-8 text-white/30">
                <Loader2 className="h-4 w-4 animate-spin" />
              </div>
            ) : sourceData.length === 0 ? (
              <p className="py-6 text-center text-xs text-white/30">No leads yet</p>
            ) : (
              <div className="flex items-center gap-3">
                <ResponsiveContainer width={90} height={90}>
                  <PieChart>
                    <Pie data={sourceData} cx="50%" cy="50%" innerRadius={26} outerRadius={42} dataKey="value" labelLine={false}>
                      {sourceData.map((entry, i) => (
                        <Cell key={i} fill={entry.color} />
                      ))}
                    </Pie>
                  </PieChart>
                </ResponsiveContainer>
                <div className="space-y-1.5 flex-1">
                  {sourceData.map((d) => (
                    <div key={d.name} className="flex items-center gap-2">
                      <div className="h-2 w-2 rounded-full flex-shrink-0" style={{ backgroundColor: d.color }} />
                      <span className="text-[11px] text-white/50 flex-1 truncate">{d.name}</span>
                      <span className="text-[11px] font-semibold text-white tabular-nums">{d.value.toLocaleString()}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          <div className="glass-card rounded-[24px] p-4">
            <h3 className="text-sm font-semibold text-white mb-3">Reply Intent</h3>
            {loading ? (
              <div className="flex items-center justify-center py-8 text-white/30">
                <Loader2 className="h-4 w-4 animate-spin" />
              </div>
            ) : intentData.length === 0 ? (
              <p className="py-4 text-center text-xs text-white/30">No replies yet</p>
            ) : (
              <div className="space-y-2">
                {intentData.map((d) => {
                  const total = intentData.reduce((s, r) => s + r.count, 0);
                  const pct = Math.round((d.count / total) * 100);
                  return (
                    <div key={d.intent}>
                      <div className="flex items-center justify-between mb-0.5">
                        <span className="text-[11px] text-white/50">{d.intent}</span>
                        <span className="text-[11px] font-semibold text-white">{d.count}</span>
                      </div>
                      <div className="h-1.5 rounded-full bg-white/[0.06]">
                        <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, backgroundColor: d.color }} />
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}



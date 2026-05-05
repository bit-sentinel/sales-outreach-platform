'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Users, Zap, Mail, MessageSquare, TrendingUp } from 'lucide-react';
import { api } from '@/lib/api-client';
import { cn } from '@/lib/utils';

interface DashboardData {
  total_leads: number;
  enriched_leads: number;
  scored_leads: number;
  hot_leads: number;
  warm_leads: number;
  active_campaigns: number;
  total_campaigns: number;
  emails_sent_total: number;
  open_rate: number;
  reply_rate: number;
  bounce_rate: number;
  total_replies: number;
}

type KPI = {
  label: string;
  value: string;
  subtext: string;
  icon: React.ElementType;
  href: string;
  accentColor?: string;
};

export function DashboardKPIs() {
  const [data, setData] = useState<DashboardData | null>(null);

  useEffect(() => {
    api<DashboardData>({ method: 'GET', url: '/analytics/dashboard' })
      .then(setData)
      .catch(() => null);
  }, []);

  const kpis: KPI[] = [
    {
      label:    'Total Leads',
      value:    data ? data.total_leads.toLocaleString() : '—',
      subtext:  data ? `${data.enriched_leads.toLocaleString()} enriched · ${data.hot_leads} hot` : 'Loading…',
      icon:     Users,
      href:     '/leads',
      accentColor: '#1c8ed4',
    },
    {
      label:    'Active Campaigns',
      value:    data ? String(data.active_campaigns) : '—',
      subtext:  data ? `${data.total_campaigns} total campaigns` : 'Loading…',
      icon:     Zap,
      href:     '/campaigns',
      accentColor: '#059669',
    },
    {
      label:    'Sent',
      value:    data ? data.emails_sent_total.toLocaleString() : '—',
      subtext:  data ? `${data.open_rate}% open rate · ${data.bounce_rate}% bounce` : 'Loading…',
      icon:     Mail,
      href:     '/campaigns',
      accentColor: '#d97706',
    },
    {
      label:    'Reply Rate',
      value:    data ? `${data.reply_rate}%` : '—',
      subtext:  data ? `${data.total_replies.toLocaleString()} total replies` : 'Loading…',
      icon:     MessageSquare,
      href:     '/replies',
      accentColor: '#7c4dcc',
    },
  ];

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {kpis.map((kpi) => {
        const Icon = kpi.icon;
        const accent = kpi.accentColor ?? '#1c8ed4';
        return (
          <Link
            key={kpi.label}
            href={kpi.href}
            className="group relative overflow-hidden rounded-2xl p-5 flex flex-col justify-between transition-all hover:-translate-y-0.5 hover:shadow-[0_12px_32px_rgba(13,37,64,0.28)]"
            style={{
              background: `linear-gradient(135deg, #0d2540 0%, #09131f 50%, ${accent} 100%)`,
              boxShadow: '0 6px 24px rgba(13,37,64,0.22)',
              minHeight: '148px',
            }}
          >
            {/* orbs */}
            <div className="pointer-events-none absolute -right-8 -top-8 h-32 w-32 rounded-full bg-white/5" />
            <div className="pointer-events-none absolute -bottom-6 right-4 h-20 w-20 rounded-full bg-white/4" />
            <div className="flex items-start justify-between">
              <p className="text-xs font-semibold text-white/60">{kpi.label}</p>
              <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-white/12">
                <Icon className="h-4 w-4 text-white/80" />
              </div>
            </div>
            <div>
              <p className="text-3xl font-extrabold tracking-tight tabular-nums text-white">{kpi.value}</p>
              <p className="mt-1 text-[11px] text-white/45">{kpi.subtext}</p>
            </div>
            <TrendingUp className="absolute bottom-4 right-4 h-12 w-12 text-white/5 group-hover:text-white/8 transition-colors" />
          </Link>
        );
      })}
    </div>
  );
}

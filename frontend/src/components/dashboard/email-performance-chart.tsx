'use client';

import { useEffect, useState } from 'react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { api } from '@/lib/api-client';

interface WeekPoint { date: string; sent: number; opened: number; replied: number; }
interface PerformanceData { weekly: WeekPoint[]; total_sent: number; open_rate: number; reply_rate: number; }

const SERIES = [
  { key: 'sent',    label: 'Sent',    color: '#6366f1', gradId: 'gSent'    },
  { key: 'opened',  label: 'Opened',  color: '#22c55e', gradId: 'gOpened'  },
  { key: 'replied', label: 'Replied', color: '#f59e0b', gradId: 'gReplied' },
];

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-2xl border border-white/[0.1] bg-[#111827]/95 px-3 py-2.5 shadow-xl text-xs backdrop-blur-sm">
      <p className="font-semibold text-white mb-1.5">{label}</p>
      {payload.map((p: any) => (
        <div key={p.dataKey} className="flex items-center gap-2 py-0.5">
          <div className="h-2 w-2 rounded-full flex-shrink-0" style={{ backgroundColor: p.color }} />
          <span className="text-white/50 capitalize">{p.dataKey}</span>
          <span className="ml-auto font-semibold text-white tabular-nums pl-4">{p.value.toLocaleString()}</span>
        </div>
      ))}
    </div>
  );
};

export function EmailPerformanceChart() {
  const [perf, setPerf] = useState<PerformanceData | null>(null);

  useEffect(() => {
    api<PerformanceData>({ method: 'GET', url: '/analytics/email-performance' })
      .then(setPerf)
      .catch(() => null);
  }, []);

  const chartData = perf?.weekly ?? [];
  const totalSent = perf?.total_sent ?? 0;
  const inlineStats = [
    { label: 'Open rate',  value: perf ? `${perf.open_rate}%`  : '—', color: '#22c55e' },
    { label: 'Reply rate', value: perf ? `${perf.reply_rate}%` : '—', color: '#f59e0b' },
  ];

  return (
    <div className="glass-card rounded-[28px] p-5">
      {/* Header */}
      <div className="flex items-start justify-between mb-1">
        <div>
          <h3 className="text-sm font-semibold text-white">Email Performance</h3>
          <p className="text-xs text-white/40 mt-0.5">
            Last 8 weeks{totalSent > 0 ? ` · ${totalSent.toLocaleString()} emails sent` : ''}
          </p>
        </div>
        <div className="flex gap-5">
          {inlineStats.map(s => (
            <div key={s.label} className="text-right">
              <p className="text-sm font-bold tabular-nums" style={{ color: s.color }}>{s.value}</p>
              <p className="text-[10px] text-white/40">{s.label}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Legend */}
      <div className="flex gap-4 mb-3 mt-3">
        {SERIES.map(s => (
          <div key={s.key} className="flex items-center gap-1.5">
            <div className="h-2 w-2 rounded-full" style={{ backgroundColor: s.color }} />
            <span className="text-[11px] text-white/50">{s.label}</span>
          </div>
        ))}
      </div>

      {/* Chart */}
      <div style={{ height: '220px' }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
            <defs>
              {SERIES.map(s => (
                <linearGradient key={s.gradId} id={s.gradId} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={s.color} stopOpacity={0.18} />
                  <stop offset="95%" stopColor={s.color} stopOpacity={0} />
                </linearGradient>
              ))}
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 11, fill: 'rgba(255,255,255,0.3)' }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tick={{ fontSize: 11, fill: 'rgba(255,255,255,0.3)' }}
              axisLine={false}
              tickLine={false}
              width={38}
            />
            <Tooltip content={<CustomTooltip />} />
            {SERIES.map(s => (
              <Area
                key={s.key}
                type="monotone"
                dataKey={s.key}
                stroke={s.color}
                strokeWidth={2}
                fill={`url(#${s.gradId})`}
                dot={false}
                activeDot={{ r: 4, strokeWidth: 0 }}
              />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

